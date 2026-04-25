import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DB_PATH = Path("data/identity_agent.db")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    target = Path(db_path) if db_path else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | Path | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS identities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pubkey TEXT NOT NULL,
                handle TEXT NOT NULL,
                domain TEXT NOT NULL,
                nip05 TEXT NOT NULL,
                paid INTEGER NOT NULL DEFAULT 0,
                verified INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                payment_hash TEXT,
                relays_json TEXT NOT NULL DEFAULT '[]',
                UNIQUE(handle, domain)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS identity_metadata (
                pubkey TEXT PRIMARY KEY,
                category TEXT,
                tags_json TEXT NOT NULL DEFAULT '[]',
                trust_score REAL NOT NULL DEFAULT 0,
                last_active TEXT,
                notes TEXT
            )
            """
        )
        conn.commit()


def create_pending_identity(
    pubkey: str,
    handle: str,
    domain: str,
    payment_hash: str,
    relays: list[str] | None = None,
    expires_at: str | None = None,
    db_path: str | Path | None = None,
) -> int:
    init_db(db_path)
    nip05 = f"{handle}@{domain}"
    relays_json = json.dumps(relays or [])

    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO identities (
                pubkey, handle, domain, nip05, paid, verified, created_at, expires_at, payment_hash, relays_json
            ) VALUES (?, ?, ?, ?, 0, 0, ?, ?, ?, ?)
            """,
            (pubkey, handle, domain, nip05, _utc_now_iso(), expires_at, payment_hash, relays_json),
        )
        conn.commit()
        return int(cursor.lastrowid)


def mark_paid_and_verified(pubkey: str, db_path: str | Path | None = None) -> bool:
    init_db(db_path)
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE identities
            SET paid = 1, verified = 1
            WHERE pubkey = ?
            """,
            (pubkey,),
        )
        conn.commit()
        return cursor.rowcount > 0


def _identity_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    data = dict(row)
    data["paid"] = bool(data["paid"])
    data["verified"] = bool(data["verified"])
    data["relays"] = json.loads(data.pop("relays_json") or "[]")
    return data


def get_identity_by_pubkey(pubkey: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM identities WHERE pubkey = ?", (pubkey,)).fetchone()
        return _identity_row_to_dict(row)


def get_identity_by_handle(handle: str, domain: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM identities WHERE handle = ? AND domain = ?",
            (handle, domain),
        ).fetchone()
        return _identity_row_to_dict(row)


def list_verified(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM identities WHERE verified = 1 ORDER BY created_at DESC"
        ).fetchall()
        return [_identity_row_to_dict(row) for row in rows]


def search_identities(query: str, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    q = f"%{query.strip()}%"
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM identities
            WHERE pubkey LIKE ? OR handle LIKE ? OR domain LIKE ? OR nip05 LIKE ?
            ORDER BY verified DESC, created_at DESC
            """,
            (q, q, q, q),
        ).fetchall()
        return [_identity_row_to_dict(row) for row in rows]


def upsert_identity_metadata(
    pubkey: str,
    category: str | None = None,
    tags: list[str] | None = None,
    trust_score: float = 0.0,
    last_active: str | None = None,
    notes: str | None = None,
    db_path: str | Path | None = None,
) -> None:
    init_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO identity_metadata (pubkey, category, tags_json, trust_score, last_active, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(pubkey) DO UPDATE SET
                category=excluded.category,
                tags_json=excluded.tags_json,
                trust_score=excluded.trust_score,
                last_active=excluded.last_active,
                notes=excluded.notes
            """,
            (
                pubkey,
                category,
                json.dumps(tags or []),
                trust_score,
                last_active,
                notes,
            ),
        )
        conn.commit()


def get_identity_metadata(pubkey: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT pubkey, category, tags_json, trust_score, last_active, notes FROM identity_metadata WHERE pubkey = ?",
            (pubkey,),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["tags"] = json.loads(data.pop("tags_json") or "[]")
        return data
