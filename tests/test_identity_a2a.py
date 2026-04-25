from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
import agent_logic
from src.agents.identity_agent import store
from src.agents.identity_agent.store import upsert_identity_metadata


class _MockWallet:
    def __init__(self):
        self._created = 0
        self._paid: set[str] = set()

    def create_invoice(self, amount: int, memo: str = "") -> dict:
        self._created += 1
        payment_hash = f"hash_{self._created}"
        return {"payment_hash": payment_hash, "bolt11": f"ln_invoice_{payment_hash}"}

    def check_invoice(self, checking_id: str) -> bool:
        return checking_id in self._paid

    def mark_paid(self, checking_id: str) -> None:
        self._paid.add(checking_id)


def test_a2a_identity_methods_and_register_payment_flow():
    wallet = _MockWallet()
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "identity_agent.db"
        original_db_path = store.DB_PATH
        store.DB_PATH = db_path
        try:
            agent_logic._wallet = None
            with (
                patch("src.agents.identity_agent.identity_agent.AgentWallet", return_value=wallet),
                patch("agent_wallet.AgentWallet", return_value=wallet),
                patch.dict("os.environ", {"IDENTITY_FREE_QUERIES": "true"}, clear=False),
            ):
                client = TestClient(main.app)

                unpaid = client.post(
                    "/a2a",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "identity.register_nip05",
                        "params": {
                            "pubkey": "pubkey_a2a",
                            "handle": "alice",
                            "domain": "example.com",
                            "relays": ["wss://relay.damus.io"],
                        },
                    },
                )
                unpaid_body = unpaid.json()
                assert unpaid.status_code == 200
                assert unpaid_body["result"]["payment_required"] is True
                assert unpaid_body["result"]["amount_sats"] == 1000
                assert "payment_request" in unpaid_body["result"]

                payment_hash = unpaid_body["result"]["payment_hash"]
                wallet.mark_paid(payment_hash)

                paid = client.post(
                    "/a2a",
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "identity.register_nip05",
                        "params": {
                            "pubkey": "pubkey_a2a",
                            "handle": "alice",
                            "domain": "example.com",
                            "relays": ["wss://relay.damus.io"],
                            "payment_hash": payment_hash,
                        },
                    },
                )
                paid_body = paid.json()
                assert paid.status_code == 200
                assert paid_body["result"]["status"] == "verified"

                upsert_identity_metadata(
                    pubkey="pubkey_a2a",
                    category="dev",
                    tags=["nostr", "lightning", "agent"],
                    trust_score=0.75,
                    db_path=db_path,
                )

                get_identity = client.post(
                    "/a2a",
                    json={
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "identity.get_identity",
                        "params": {"pubkey": "pubkey_a2a"},
                    },
                )
                assert get_identity.status_code == 200
                assert get_identity.json()["result"]["pubkey"] == "pubkey_a2a"

                list_verified = client.post(
                    "/a2a",
                    json={
                        "jsonrpc": "2.0",
                        "id": 4,
                        "method": "identity.list_verified",
                        "params": {},
                    },
                )
                assert list_verified.status_code == 200
                assert list_verified.json()["result"]["count"] >= 1

                search = client.post(
                    "/a2a",
                    json={
                        "jsonrpc": "2.0",
                        "id": 5,
                        "method": "identity.search",
                        "params": {"query": "alice"},
                    },
                )
                assert search.status_code == 200
                assert search.json()["result"]["count"] >= 1

                trust = client.post(
                    "/a2a",
                    json={
                        "jsonrpc": "2.0",
                        "id": 6,
                        "method": "identity.get_trust_signal",
                        "params": {"pubkey": "pubkey_a2a"},
                    },
                )
                assert trust.status_code == 200
                assert "warning" in trust.json()["result"]
        finally:
            store.DB_PATH = original_db_path


def test_a2a_identity_query_requires_payment_when_free_mode_disabled():
    wallet = _MockWallet()
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "identity_agent.db"
        original_db_path = store.DB_PATH
        store.DB_PATH = db_path
        try:
            agent_logic._wallet = None
            with (
                patch("src.agents.identity_agent.identity_agent.AgentWallet", return_value=wallet),
                patch("agent_wallet.AgentWallet", return_value=wallet),
                patch.dict("os.environ", {"IDENTITY_FREE_QUERIES": "false"}, clear=False),
            ):
                client = TestClient(main.app)
                response = client.post(
                    "/a2a",
                    json={
                        "jsonrpc": "2.0",
                        "id": 7,
                        "method": "identity.get_trust_signal",
                        "params": {"pubkey": "pubkey_any"},
                    },
                )
                body = response.json()
                assert response.status_code == 200
                assert body["result"]["payment_required"] is True
                assert "payment_request" in body["result"]
                assert "payment_hash" in body["result"]
        finally:
            store.DB_PATH = original_db_path
