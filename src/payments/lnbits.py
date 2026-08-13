"""Async LNbits client.

Replaces the previous synchronous ``requests``-based client, which was called
from inside ``async def`` handlers with no timeouts — a single hung LNbits
instance would block the event loop and take the whole worker down with it.

The important design property here is the three-state payment lookup. The old
client collapsed "not paid" and "could not reach LNbits" into a single ``False``,
which is what allowed an outage to be reported to callers as "payment required"
(or, worse upstream, to be swallowed into free service). ``PaymentState.UNKNOWN``
keeps those cases distinct so the gate can fail closed with a 503.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum

import httpx

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 0.25

#: Status strings LNbits has used across versions to mean "settled".
_PAID_STATUSES = {"paid", "success", "settled", "complete", "completed"}
#: Status strings that positively mean "not settled yet" (as opposed to unknown).
_UNPAID_STATUSES = {"pending", "unpaid", "open", "expired", "failed"}


class LNbitsError(RuntimeError):
    """Raised when an LNbits operation cannot be completed."""


class PaymentState(str, Enum):
    PAID = "paid"
    UNPAID = "unpaid"
    #: LNbits was unreachable or returned something we could not interpret.
    #: Callers must fail closed on this — never treat it as either outcome.
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Invoice:
    payment_hash: str
    bolt11: str
    amount_sats: int


@dataclass(frozen=True)
class PaymentRecord:
    state: PaymentState
    #: Settled amount in sats, when LNbits reported one we could parse.
    amount_sats: int | None = None
    #: False when the record describes an outgoing payment from this node.
    incoming: bool | None = None


def _parse_state(data: dict) -> PaymentState:
    paid = data.get("paid")
    if paid is True:
        return PaymentState.PAID
    status = str(data.get("status", "")).strip().lower()
    if status in _PAID_STATUSES:
        return PaymentState.PAID
    # `pending: true` is LNbits' older way of saying "not settled".
    if paid is False or data.get("pending") is True or status in _UNPAID_STATUSES:
        return PaymentState.UNPAID
    logger.warning(
        "Unrecognised LNbits payment record shape (keys=%s); treating as unknown",
        sorted(data.keys()),
    )
    return PaymentState.UNKNOWN


def _parse_amount_msats(data: dict) -> int | None:
    """Pull the settled amount out of an LNbits payment record.

    LNbits has moved the field between the top level and ``details`` across
    versions and reports millisatoshis, signed by direction. Returning ``None``
    when it cannot be found is deliberate and safe: the ledger already binds each
    hash to the service and price it was issued for, so this value is a secondary
    cross-check rather than the primary control.
    """
    for source in (data, data.get("details") or {}):
        if not isinstance(source, dict):
            continue
        raw = source.get("amount")
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return int(raw)
    return None


class AsyncLNbitsClient:
    """Thin async wrapper over the LNbits payments API."""

    def __init__(self, base_url: str, api_key: str, client: httpx.AsyncClient | None = None):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self._api_key, "Content-Type": "application/json"}

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request(self, method: str, path: str, *, retry: bool, **kwargs) -> httpx.Response:
        """Issue a request, retrying only where a retry is safe and useful."""
        url = f"{self._base_url}{path}"
        last_error: Exception | None = None

        for attempt in range(1, (_MAX_ATTEMPTS if retry else 1) + 1):
            try:
                response = await self._client.request(
                    method, url, headers=self._headers, **kwargs
                )
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning(
                    "LNbits %s %s failed (attempt %d): %s", method, path, attempt, exc
                )
            else:
                # 4xx is a client-side problem; retrying cannot help.
                if response.status_code < 500:
                    return response
                last_error = LNbitsError(f"LNbits returned HTTP {response.status_code}")
                logger.warning(
                    "LNbits %s %s returned HTTP %d (attempt %d)",
                    method,
                    path,
                    response.status_code,
                    attempt,
                )

            if retry and attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))

        raise LNbitsError(f"LNbits {method} {path} failed") from last_error

    async def create_invoice(self, amount_sats: int, memo: str) -> Invoice:
        """Mint an incoming invoice.

        Deliberately not retried: a retry after an ambiguous failure can mint a
        second invoice that nobody is tracking.
        """
        if amount_sats <= 0:
            raise ValueError("amount_sats must be positive")

        response = await self._request(
            "POST",
            "/api/v1/payments",
            retry=False,
            json={"out": False, "amount": amount_sats, "memo": memo},
        )
        if response.status_code >= 400:
            raise LNbitsError(f"Invoice creation rejected with HTTP {response.status_code}")

        try:
            data = response.json()
        except ValueError as exc:
            raise LNbitsError("Invoice creation returned a non-JSON body") from exc

        payment_hash = data.get("payment_hash") or data.get("checking_id")
        bolt11 = data.get("bolt11") or data.get("payment_request")
        if not payment_hash or not bolt11:
            raise LNbitsError("Invoice creation response is missing payment_hash or bolt11")

        logger.info("Issued invoice for %d sats (hash=%s…)", amount_sats, payment_hash[:12])
        return Invoice(payment_hash=payment_hash, bolt11=bolt11, amount_sats=amount_sats)

    async def get_payment(self, payment_hash: str) -> PaymentRecord:
        """Look up a payment. Never raises — unreachable LNbits yields UNKNOWN."""
        try:
            response = await self._request(
                "GET", f"/api/v1/payments/{payment_hash}", retry=True
            )
        except LNbitsError as exc:
            logger.warning("Payment lookup unavailable for %s…: %s", payment_hash[:12], exc)
            return PaymentRecord(PaymentState.UNKNOWN)

        if response.status_code == 404:
            # LNbits does not know this hash. It was certainly not paid here.
            return PaymentRecord(PaymentState.UNPAID)
        if response.status_code >= 400:
            logger.warning(
                "Payment lookup for %s… returned HTTP %d",
                payment_hash[:12],
                response.status_code,
            )
            return PaymentRecord(PaymentState.UNKNOWN)

        try:
            data = response.json()
        except ValueError:
            logger.warning("Payment lookup for %s… returned a non-JSON body", payment_hash[:12])
            return PaymentRecord(PaymentState.UNKNOWN)
        if not isinstance(data, dict):
            return PaymentRecord(PaymentState.UNKNOWN)

        msats = _parse_amount_msats(data)
        amount_sats = abs(msats) // 1000 if msats is not None else None
        incoming = msats >= 0 if msats is not None else None
        return PaymentRecord(_parse_state(data), amount_sats=amount_sats, incoming=incoming)

    async def get_balance_sats(self) -> int:
        response = await self._request("GET", "/api/v1/wallet", retry=True)
        if response.status_code >= 400:
            raise LNbitsError(f"Wallet lookup returned HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise LNbitsError("Wallet lookup returned a non-JSON body") from exc
        # LNbits reports wallet balance in millisatoshis.
        return int(data.get("balance", 0)) // 1000
