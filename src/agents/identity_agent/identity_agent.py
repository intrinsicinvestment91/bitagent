import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

from agent_wallet import AgentWallet
from src.agents.base_agent import BaseAgent
from src.agents.identity_agent.store import (
    create_pending_identity,
    get_identity_metadata,
    get_identity_by_pubkey,
    init_db,
    list_verified as store_list_verified,
    mark_paid_and_verified,
    search_identities,
    upsert_identity_metadata,
)
from src.agents.identity_agent.trust import calculate_trust_score


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
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed >= datetime.now(timezone.utc)

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
        self.price_sats = {
            "identity.register_nip05": 1000,
            "identity.get_identity": 10,
            "identity.list_verified": 25,
            "identity.search": 25,
            "identity.get_trust_signal": 10,
        }
        init_db(self.db_path)
        logging.info("%s v%s initialized with DID: %s", self.name, self.version, self.id)

    def _get_wallet(self) -> AgentWallet:
        if self.wallet is None:
            self.wallet = AgentWallet()
        return self.wallet

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

        if not payment_hash:
            wallet = self._get_wallet()
            invoice = wallet.create_invoice(
                amount=self.price_sats["identity.register_nip05"],
                memo=f"NIP-05 registration: {handle}@{domain}",
            )
            created_hash = invoice.get("payment_hash")
            payment_request = invoice.get("bolt11") or invoice.get("payment_request")
            if not created_hash or not payment_request:
                return {"error": "Unable to create payment invoice"}

            try:
                create_pending_identity(
                    pubkey=pubkey,
                    handle=handle,
                    domain=domain,
                    payment_hash=created_hash,
                    relays=relays,
                    db_path=self.db_path,
                )
            except sqlite3.IntegrityError:
                return {"error": f"Identity handle '{handle}@{domain}' already exists"}

            return {
                "payment_required": True,
                "amount_sats": self.price_sats["identity.register_nip05"],
                "payment_request": payment_request,
                "payment_hash": created_hash,
            }

        identity = get_identity_by_pubkey(pubkey, db_path=self.db_path)
        if not identity:
            return {"error": "No pending identity found for pubkey"}

        if identity.get("payment_hash") != payment_hash:
            return {"error": "Payment hash does not match pending registration"}

        if not self._get_wallet().check_invoice(payment_hash):
            return {"error": "Payment not verified"}

        mark_paid_and_verified(pubkey, db_path=self.db_path)
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
