"""Durable record of every invoice this node issues.

This is what makes a payment single-use. Previously the only question asked was
"does LNbits say this hash is paid?", which stays true forever — so one payment
bought unlimited service, on any endpoint, at any price.

Two properties are enforced here:

* **Binding.** A hash is only redeemable for the service and price it was issued
  for. The row is written before the 402 goes out, so an unrecognised hash — or a
  hash issued for a cheaper service — has nothing to match against.
* **Single use.** ``consume`` flips ``issued`` → ``consumed`` inside a
  ``BEGIN IMMEDIATE`` transaction. SQLite takes the write lock on the first
  statement, so concurrent redemptions of the same hash serialise and exactly one
  observes ``state='issued'``. A read-then-write would race here; the conditional
  UPDATE is the whole point.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
    payment_hash TEXT PRIMARY KEY,
    service_id   TEXT NOT NULL,
    amount_sats  INTEGER NOT NULL,
    memo         TEXT,
    state        TEXT NOT NULL DEFAULT 'issued',
    created_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    consumed_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_invoices_expires ON invoices(expires_at);
CREATE INDEX IF NOT EXISTS idx_invoices_state ON invoices(state);
"""


class ConsumeResult(str, Enum):
    OK = "ok"
    ALREADY_CONSUMED = "already_consumed"
    UNKNOWN_HASH = "unknown_payment_hash"
    WRONG_SERVICE = "wrong_service"
    AMOUNT_MISMATCH = "amount_mismatch"
    EXPIRED = "expired"

    @property
    def settled(self) -> bool:
        return self is ConsumeResult.OK

    @property
    def message(self) -> str:
        return {
            ConsumeResult.OK: "Payment accepted.",
            ConsumeResult.ALREADY_CONSUMED: (
                "This payment has already been redeemed. Each invoice is valid for "
                "exactly one request."
            ),
            ConsumeResult.UNKNOWN_HASH: (
                "This payment hash was not issued by this node. Request a new invoice."
            ),
            ConsumeResult.WRONG_SERVICE: (
                "This payment was issued for a different service. Request an invoice "
                "for the service you are calling."
            ),
            ConsumeResult.AMOUNT_MISMATCH: (
                "This payment was issued for a different amount than this service costs."
            ),
            ConsumeResult.EXPIRED: "This invoice has expired. Request a new one.",
        }[self]


@dataclass(frozen=True)
class IssuedInvoice:
    payment_hash: str
    service_id: str
    amount_sats: int
    expires_at: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat()


class PaymentLedger:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self):
        # isolation_level=None puts the driver in autocommit mode so we can issue
        # BEGIN IMMEDIATE ourselves rather than letting sqlite3 pick a deferred
        # transaction, which would not take the write lock up front.
        conn = sqlite3.connect(self.db_path, isolation_level=None, timeout=10.0)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("PRAGMA busy_timeout=10000")
            yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    # ---- writes -----------------------------------------------------------

    def record_issued(
        self,
        payment_hash: str,
        service_id: str,
        amount_sats: int,
        memo: str,
        ttl_seconds: int,
    ) -> IssuedInvoice:
        """Record an invoice at the moment it is quoted to a client."""
        now = _now()
        expires_at = now + timedelta(seconds=ttl_seconds)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO invoices
                    (payment_hash, service_id, amount_sats, memo, state, created_at, expires_at)
                VALUES (?, ?, ?, ?, 'issued', ?, ?)
                ON CONFLICT(payment_hash) DO NOTHING
                """,
                (payment_hash, service_id, amount_sats, memo, _iso(now), _iso(expires_at)),
            )
        return IssuedInvoice(payment_hash, service_id, amount_sats, _iso(expires_at))

    def consume(self, payment_hash: str, service_id: str, amount_sats: int) -> ConsumeResult:
        """Atomically redeem a payment hash exactly once.

        Returns a specific reason on failure so the caller can tell the client
        whether to pay, to stop replaying, or to request a correct invoice.
        """
        now = _iso(_now())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    """
                    UPDATE invoices
                       SET state = 'consumed', consumed_at = ?
                     WHERE payment_hash = ?
                       AND service_id = ?
                       AND amount_sats = ?
                       AND state = 'issued'
                       AND expires_at > ?
                    """,
                    (now, payment_hash, service_id, amount_sats, now),
                )
                if cursor.rowcount == 1:
                    conn.execute("COMMIT")
                    return ConsumeResult.OK

                # Nothing updated. Read the row inside the same transaction to
                # report precisely why.
                row = conn.execute(
                    "SELECT service_id, amount_sats, state, expires_at "
                    "FROM invoices WHERE payment_hash = ?",
                    (payment_hash,),
                ).fetchone()
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

        if row is None:
            return ConsumeResult.UNKNOWN_HASH
        if row["state"] == "consumed":
            return ConsumeResult.ALREADY_CONSUMED
        if row["service_id"] != service_id:
            return ConsumeResult.WRONG_SERVICE
        if row["amount_sats"] != amount_sats:
            return ConsumeResult.AMOUNT_MISMATCH
        return ConsumeResult.EXPIRED

    def release(self, payment_hash: str, service_id: str, ttl_seconds: int) -> bool:
        """Return a consumed payment to redeemable state after a failed request.

        Lightning payments cannot be refunded by the recipient, so when the work
        fails *after* settlement — an upstream API is down, the translation
        backend errors — the honest thing is to let the caller retry with the
        payment they already made. The retry window is refreshed so an expired
        deadline does not strand them.
        """
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    """
                    UPDATE invoices
                       SET state = 'issued', consumed_at = NULL, expires_at = ?
                     WHERE payment_hash = ? AND service_id = ? AND state = 'consumed'
                    """,
                    (
                        _iso(_now() + timedelta(seconds=ttl_seconds)),
                        payment_hash,
                        service_id,
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return cursor.rowcount == 1

    def purge_expired(self) -> int:
        """Drop unpaid quotes that can no longer be redeemed.

        Consumed rows are kept: they are the audit trail, and dropping them would
        turn an old replay attempt into an 'unknown hash' rather than a clear
        'already redeemed'.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM invoices WHERE state = 'issued' AND expires_at <= ?",
                (_iso(_now()),),
            )
            return cursor.rowcount

    # ---- reads ------------------------------------------------------------

    def get(self, payment_hash: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM invoices WHERE payment_hash = ?", (payment_hash,)
            ).fetchone()
        return dict(row) if row else None

    def stats(self) -> dict:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT state, COUNT(*) AS n, COALESCE(SUM(amount_sats), 0) AS sats "
                "FROM invoices GROUP BY state"
            ).fetchall()
        by_state = {r["state"]: {"count": r["n"], "sats": r["sats"]} for r in rows}
        return {
            "issued": by_state.get("issued", {"count": 0, "sats": 0}),
            "consumed": by_state.get("consumed", {"count": 0, "sats": 0}),
        }

    def healthy(self) -> bool:
        """Confirm the ledger is present and writable."""
        try:
            with self._connect() as conn:
                conn.execute("SELECT 1 FROM invoices LIMIT 1").fetchone()
            return True
        except sqlite3.Error as exc:
            logger.error("Payment ledger is not usable: %s", exc)
            return False

    # ---- async wrappers ---------------------------------------------------
    # SQLite calls are blocking. They are sub-millisecond against a local file,
    # but running them off the event loop keeps a slow disk from stalling every
    # other in-flight request.

    async def arecord_issued(self, *args, **kwargs) -> IssuedInvoice:
        return await asyncio.to_thread(self.record_issued, *args, **kwargs)

    async def aconsume(self, *args, **kwargs) -> ConsumeResult:
        return await asyncio.to_thread(self.consume, *args, **kwargs)

    async def apurge_expired(self) -> int:
        return await asyncio.to_thread(self.purge_expired)

    async def arelease(self, *args, **kwargs) -> bool:
        return await asyncio.to_thread(self.release, *args, **kwargs)

    async def aget(self, payment_hash: str) -> dict | None:
        return await asyncio.to_thread(self.get, payment_hash)
