from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

import main
from src.agents.identity_agent import store
from src.agents.identity_agent.store import create_pending_identity, mark_paid_and_verified


class TestNostrWellKnown:
    def setup_method(self):
        self.temp_dir = TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "identity_agent.db"
        self.original_db_path = store.DB_PATH
        store.DB_PATH = self.db_path
        self.client = TestClient(main.app)

    def teardown_method(self):
        store.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_paid_verified_identity_resolves(self):
        create_pending_identity(
            pubkey="pubkey_paid",
            handle="alice",
            domain="testserver",
            payment_hash="hash_paid",
            relays=["wss://relay.damus.io"],
        )
        mark_paid_and_verified("pubkey_paid")

        response = self.client.get("/.well-known/nostr.json?name=alice")
        assert response.status_code == 200
        assert response.json() == {
            "names": {"alice": "pubkey_paid"},
            "relays": {"pubkey_paid": ["wss://relay.damus.io"]},
        }

    def test_unpaid_identity_does_not_resolve(self):
        create_pending_identity(
            pubkey="pubkey_unpaid",
            handle="bob",
            domain="testserver",
            payment_hash="hash_unpaid",
            relays=["wss://relay.damus.io"],
        )

        response = self.client.get("/.well-known/nostr.json?name=bob")
        assert response.status_code == 200
        assert response.json() == {"names": {}}

    def test_expired_identity_does_not_resolve(self):
        expired_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        create_pending_identity(
            pubkey="pubkey_expired",
            handle="carol",
            domain="testserver",
            payment_hash="hash_expired",
            relays=["wss://relay.damus.io"],
            expires_at=expired_at,
        )
        mark_paid_and_verified("pubkey_expired")

        response = self.client.get("/.well-known/nostr.json?name=carol")
        assert response.status_code == 200
        assert response.json() == {"names": {}}
