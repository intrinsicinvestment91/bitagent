import logging
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.identity_agent.store import (
    create_pending_identity,
    get_identity_by_handle,
    get_identity_by_pubkey,
    get_identity_metadata,
    init_db,
    mark_paid_and_verified,
    reclaim_expired_pending,
    search_identities,
    upsert_identity_metadata,
)
from src.agents.identity_agent.store import (
    list_verified as store_list_verified,
)
from src.agents.identity_agent.trust import calculate_trust_score
from src.payments import Quote, pricing_for, require_payment

REGISTER_SERVICE_ID = "identity.register_nip05"

#: How long a paid NIP-05 registration stays valid. The schema always had an
#: expires_at column and the resolver always honoured it, but registration never
#: set one — so every registration was perpetual.
REGISTRATION_VALIDITY_DAYS = 365

#: NIP-05 local parts are restricted to a-z0-9-_. by the spec.
_HANDLE_RE = re.compile(r"^[a-z0-9\-_.]{1,64}$")
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?"
    r"(\.[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?)+$"
)
_PUBKEY_RE = re.compile(r"^[0-9a-f]{64}$")


class IdentityAgent(BaseAgent):
    """
    Identity service agent for NIP-05 registration and trust discovery.
    """

    @staticmethod
    def _is_active_registration(expires_at: str | None) -> bool:
        if not expires_at:
            return True
        try:
            parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            return True
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed >= datetime.now(UTC)

    def __init__(self, **kwargs: Any):
        super().__init__(name="IdentityAgent", role="identity_service")
        self.version = "0.1.0"
        self.description = "Identity and verification services for BitAgent participants."
        self.db_path = kwargs.get("db_path")
        self.wallet = kwargs.get("wallet")
        self.services = {
            "identity.register_nip05": "Register and verify a NIP-05 identifier",
            "identity.get_identity": "Get identity details by pubkey",
            "identity.list_verified": "List currently verified identities",
            "identity.search": "Search identities by query",
            "identity.get_trust_signal": "Get trust signal score and evidence",
        }
        init_db(self.db_path)
        logging.info("%s v%s initialized with DID: %s", self.name, self.version, self.id)

    @property
    def price_sats(self) -> dict[str, int]:
        """Prices from the shared catalog — the single source of truth."""
        return pricing_for("identity")

    def get_info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "did": self.id,
            "services": self.services,
            "pricing": self.price_sats,
        }

    def list_services(self) -> list[str]:
        return list(self.services.keys())

    def get_price(self, service: str | None = None) -> int | dict[str, int]:
        if service:
            return self.price_sats.get(service, 0)
        return self.price_sats

    async def register_nip05(
        self,
        pubkey: str,
        handle: str,
        domain: str,
        relays: list[str] | None = None,
        payment_hash: str | None = None,
    ) -> dict[str, Any]:
        if not pubkey or not handle or not domain:
            return {"error": "Missing 'pubkey', 'handle', or 'domain'"}

        handle = handle.strip().lower()
        domain = domain.strip().lower()
        pubkey = pubkey.strip().lower()

        if not _PUBKEY_RE.match(pubkey):
            return {"error": "'pubkey' must be a 64-character lowercase hex Nostr key"}
        if not _HANDLE_RE.match(handle):
            return {"error": "'handle' may only contain a-z, 0-9, '-', '_' and '.'"}
        if not _DOMAIN_RE.match(domain):
            return {"error": "'domain' is not a valid hostname"}

        if not payment_hash:
            return await self._quote_registration(pubkey, handle, domain, relays)

        identity = get_identity_by_pubkey(pubkey, db_path=self.db_path)
        if not identity:
            return {"error": "No pending identity found for pubkey"}

        if identity.get("payment_hash") != payment_hash:
            return {"error": "Payment hash does not match pending registration"}

        outcome = await require_payment(REGISTER_SERVICE_ID, payment_hash)
        if isinstance(outcome, Quote):
            return dict(outcome.body)

        expires_at = (datetime.now(UTC) + timedelta(days=REGISTRATION_VALIDITY_DAYS)).isoformat()
        mark_paid_and_verified(
            pubkey, payment_hash=payment_hash, expires_at=expires_at, db_path=self.db_path
        )
        # Seed metadata row so trust lookups have deterministic fields.
        upsert_identity_metadata(
            pubkey=pubkey,
            category="unclassified",
            tags=[],
            trust_score=0.0,
            db_path=self.db_path,
        )
        active = get_identity_by_pubkey(pubkey, db_path=self.db_path)
        return {
            "status": "verified",
            "nip05": active["nip05"],
            "pubkey": active["pubkey"],
            "expires_at": active.get("expires_at"),
        }

    async def _quote_registration(
        self, pubkey: str, handle: str, domain: str, relays: list[str] | None
    ) -> dict[str, Any]:
        """Issue an invoice for a registration and hold the handle until it expires."""
        # A pending row is inserted before payment and UNIQUE(handle, domain)
        # then locks the handle. Without reclaiming abandoned quotes, anyone
        # could squat every handle on this node for free by asking for invoices
        # and never paying them.
        reclaim_expired_pending(handle, domain, db_path=self.db_path)

        existing = get_identity_by_handle(handle, domain, db_path=self.db_path)
        if existing:
            if existing.get("verified"):
                return {"error": f"Identity handle '{handle}@{domain}' is already registered"}
            return {
                "error": (
                    f"Identity handle '{handle}@{domain}' has a registration in progress. "
                    "Try again after the pending invoice expires."
                )
            }

        outcome = await require_payment(
            REGISTER_SERVICE_ID, memo=f"NIP-05 registration: {handle}@{domain}"
        )
        if not isinstance(outcome, Quote):
            # Free mode: register immediately, with no payment to wait for.
            return await self._register_unpaid(pubkey, handle, domain, relays)

        body = dict(outcome.body)
        created_hash = body.get("payment_hash")
        if not created_hash:
            # The gate could not issue an invoice (e.g. LNbits is down). Surface
            # that rather than recording a registration nobody can complete.
            return body

        try:
            create_pending_identity(
                pubkey=pubkey,
                handle=handle,
                domain=domain,
                payment_hash=created_hash,
                relays=relays,
                quote_expires_at=body.get("expires_at"),
                db_path=self.db_path,
            )
        except sqlite3.IntegrityError:
            return {"error": f"Identity handle '{handle}@{domain}' already exists"}

        return body

    async def _register_unpaid(
        self, pubkey: str, handle: str, domain: str, relays: list[str] | None
    ) -> dict[str, Any]:
        """Complete a registration on a node running with payments disabled."""
        expires_at = (datetime.now(UTC) + timedelta(days=REGISTRATION_VALIDITY_DAYS)).isoformat()
        try:
            create_pending_identity(
                pubkey=pubkey,
                handle=handle,
                domain=domain,
                payment_hash="",
                relays=relays,
                expires_at=expires_at,
                db_path=self.db_path,
            )
        except sqlite3.IntegrityError:
            return {"error": f"Identity handle '{handle}@{domain}' already exists"}

        mark_paid_and_verified(pubkey, payment_hash="", db_path=self.db_path)
        upsert_identity_metadata(
            pubkey=pubkey,
            category="unclassified",
            tags=[],
            trust_score=0.0,
            db_path=self.db_path,
        )
        record = get_identity_by_pubkey(pubkey, db_path=self.db_path)
        return {
            "status": "verified",
            "nip05": record["nip05"],
            "pubkey": record["pubkey"],
            "expires_at": record.get("expires_at"),
            "notice": "This node is running with payments disabled; registration was free.",
        }

    async def get_identity(self, pubkey: str) -> dict[str, Any]:
        if not pubkey:
            return {"error": "Missing 'pubkey'"}
        record = get_identity_by_pubkey(pubkey, db_path=self.db_path)
        if not record:
            return {"error": "Identity not found"}

        metadata = get_identity_metadata(pubkey, db_path=self.db_path) or {}
        trust = calculate_trust_score(
            paid_nip05=bool(record["paid"] and record["verified"]),
            active_registration=self._is_active_registration(record.get("expires_at")),
            category=metadata.get("category", ""),
            tags=metadata.get("tags", []),
        )
        return {
            "pubkey": record["pubkey"],
            "handle": record["handle"],
            "nip05": record["nip05"],
            "verified": bool(record["verified"] and record["paid"]),
            "category": metadata.get("category", "unclassified"),
            "tags": metadata.get("tags", []),
            "trust_score": trust["score"],
        }

    async def list_verified(self) -> dict[str, Any]:
        verified = store_list_verified(db_path=self.db_path)
        return {"count": len(verified), "identities": verified}

    async def search(self, query: str) -> dict[str, Any]:
        if not query:
            return {"error": "Missing 'query'"}
        matches = search_identities(query, db_path=self.db_path)
        return {"query": query, "count": len(matches), "results": matches}

    async def get_trust_signal(self, pubkey: str) -> dict[str, Any]:
        if not pubkey:
            return {"error": "Missing 'pubkey'"}

        record = get_identity_by_pubkey(pubkey, db_path=self.db_path)
        if not record:
            return {
                "pubkey": pubkey,
                "trusted": False,
                "trust_score": 0.0,
                "basis": [],
                "warning": "Trust score is heuristic and not KYC.",
            }

        metadata = get_identity_metadata(pubkey, db_path=self.db_path) or {}
        trust = calculate_trust_score(
            paid_nip05=bool(record.get("paid") and record.get("verified")),
            active_registration=self._is_active_registration(record.get("expires_at")),
            category=metadata.get("category", ""),
            tags=metadata.get("tags", []),
        )
        trust_score = trust["score"]
        return {
            "pubkey": pubkey,
            "trusted": trust_score >= 0.5,
            "trust_score": trust_score,
            "basis": trust["basis"],
            "warning": "Trust score is heuristic and not KYC.",
        }
