"""End-to-end identity flows over the /a2a JSON-RPC endpoint.

These drive the real FastAPI app, the real payment gate and the real ledger, with
only LNbits faked — so they also cover the JSON-RPC envelope, which used to
answer every request with HTTP 200 and an error buried inside ``result``.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import main
from src.agents.identity_agent import store
from src.payments import configure_gate
from src.agents.identity_agent.store import upsert_identity_metadata

PUBKEY = "a" * 64
JSONRPC_PAYMENT_REQUIRED = -32000
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_PARSE_ERROR = -32700


@pytest.fixture
def client(tmp_path, paid_gate, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "identity_agent.db")
    with TestClient(main.app) as test_client:
        # The app's lifespan configures its own gate from the environment, which
        # would replace the test fixture's. Re-install it once startup is done so
        # these run against the fake LNbits with payments enforced.
        configure_gate(paid_gate)
        yield test_client


def rpc(client, method, params=None, request_id=1):
    return client.post(
        "/a2a",
        json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}},
    )


class TestRegistrationOverA2A:
    def test_full_quote_pay_verify_flow(self, client, fake_lnbits):
        params = {
            "pubkey": PUBKEY,
            "handle": "alice",
            "domain": "example.com",
            "relays": ["wss://relay.damus.io"],
        }

        unpaid = rpc(client, "identity.register_nip05", params).json()
        assert unpaid["error"]["code"] == JSONRPC_PAYMENT_REQUIRED
        quote = unpaid["error"]["data"]
        assert quote["amount_sats"] == 1000
        assert "payment_request" in quote

        fake_lnbits.settle(quote["payment_hash"])

        paid = rpc(
            client, "identity.register_nip05", {**params, "payment_hash": quote["payment_hash"]}
        ).json()
        assert paid["result"]["status"] == "verified"
        assert paid["result"]["nip05"] == "alice@example.com"

    def test_registration_payment_cannot_be_replayed(self, client, fake_lnbits):
        params = {"pubkey": PUBKEY, "handle": "alice", "domain": "example.com"}
        quote = rpc(client, "identity.register_nip05", params).json()["error"]["data"]
        fake_lnbits.settle(quote["payment_hash"])

        paid = {**params, "payment_hash": quote["payment_hash"]}
        assert rpc(client, "identity.register_nip05", paid).json()["result"]["status"] == "verified"

        replay = rpc(client, "identity.register_nip05", paid).json()
        assert replay["error"]["data"]["error"] == "already_consumed"


class TestPaidQueries:
    def test_queries_require_payment_when_free_mode_is_off(self, client):
        with patch.dict("os.environ", {"IDENTITY_FREE_QUERIES": "false"}, clear=False):
            body = rpc(client, "identity.get_trust_signal", {"pubkey": PUBKEY}).json()

        assert body["error"]["code"] == JSONRPC_PAYMENT_REQUIRED
        assert body["error"]["data"]["payment_required"] is True
        assert "payment_request" in body["error"]["data"]

    def test_queries_are_free_when_free_mode_is_on(self, client, fake_lnbits):
        params = {"pubkey": PUBKEY, "handle": "alice", "domain": "example.com"}
        quote = rpc(client, "identity.register_nip05", params).json()["error"]["data"]
        fake_lnbits.settle(quote["payment_hash"])
        rpc(client, "identity.register_nip05", {**params, "payment_hash": quote["payment_hash"]})
        upsert_identity_metadata(
            pubkey=PUBKEY,
            category="dev",
            tags=["nostr"],
            trust_score=0.75,
            db_path=store.DB_PATH,
        )

        with patch.dict("os.environ", {"IDENTITY_FREE_QUERIES": "true"}, clear=False):
            assert rpc(client, "identity.get_identity", {"pubkey": PUBKEY}).json()["result"][
                "pubkey"
            ] == PUBKEY
            assert rpc(client, "identity.list_verified").json()["result"]["count"] >= 1
            assert rpc(client, "identity.search", {"query": "alice"}).json()["result"]["count"] >= 1
            trust = rpc(client, "identity.get_trust_signal", {"pubkey": PUBKEY}).json()
            assert "warning" in trust["result"]


class TestJsonRpcEnvelope:
    def test_unknown_method_returns_a_jsonrpc_error(self, client):
        body = rpc(client, "nope.nothing").json()

        assert body["error"]["code"] == JSONRPC_METHOD_NOT_FOUND
        assert "result" not in body

    def test_malformed_json_returns_a_parse_error(self, client):
        response = client.post(
            "/a2a", content=b"{not json", headers={"Content-Type": "application/json"}
        )

        assert response.json()["error"]["code"] == JSONRPC_PARSE_ERROR

    def test_missing_method_is_an_invalid_request(self, client):
        body = client.post("/a2a", json={"jsonrpc": "2.0", "id": 1}).json()

        assert body["error"]["code"] == -32600

    def test_request_id_is_echoed_back(self, client):
        body = rpc(client, "nope.nothing", request_id=99).json()

        assert body["id"] == 99
