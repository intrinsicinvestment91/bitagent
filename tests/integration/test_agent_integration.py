"""End-to-end integration across the live subsystems.

This replaces a suite that mostly exercised the escrow, secure-channel and
encryption modules — all of which were unreachable from any request and have
been removed. What it covers instead is the path a real caller takes: quote a
service, pay it, get the work, and be refused on replay.

Only LNbits and the outbound service calls are faked; the app, router, gate and
ledger are real.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import main
from src.identity.enhanced_did import EnhancedDIDManager, TrustLevel
from src.monitoring.audit_logger import AuditLogger, EventType
from src.network.p2p_discovery import AgentInfo, DiscoveryQuery, P2PDiscoveryManager
from src.payments import configure_gate
from src.security.authentication import AuthenticationManager

SEARCH_RESULT = {
    "query": "bitcoin",
    "results": [{"title": "Bitcoin", "url": "https://bitcoin.org"}],
}


@pytest.fixture
def client(tmp_path, paid_gate, monkeypatch):
    from src.agents.identity_agent import store

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "identity_agent.db")
    with TestClient(main.app) as test_client:
        configure_gate(paid_gate)
        yield test_client


class TestPaidRequestLifecycle:
    def test_quote_pay_serve_then_refuse_replay(self, client, fake_lnbits):
        """The full happy path, and the replay that must not work."""
        with patch(
            "src.agents.search_agent.search_agent.SearchAgent.search",
            new=AsyncMock(return_value=SEARCH_RESULT),
        ):
            # 1. No payment -> 402 with a real invoice.
            quote = client.post("/search/query", json={"query": "bitcoin"})
            assert quote.status_code == 402
            payment_hash = quote.json()["payment_hash"]
            assert quote.json()["amount_sats"] == 10

            # 2. Submitting before paying is refused.
            early = client.post(
                "/search/query", json={"query": "bitcoin", "payment_hash": payment_hash}
            )
            assert early.status_code == 402
            assert early.json()["error"] == "payment_not_settled"

            # 3. Pay, then the work is delivered.
            fake_lnbits.settle(payment_hash)
            served = client.post(
                "/search/query", json={"query": "bitcoin", "payment_hash": payment_hash}
            )
            assert served.status_code == 200
            assert served.json() == SEARCH_RESULT

            # 4. The same payment cannot buy a second request.
            replay = client.post(
                "/search/query", json={"query": "bitcoin", "payment_hash": payment_hash}
            )
            assert replay.status_code == 402
            assert replay.json()["error"] == "already_consumed"

    def test_payment_is_returned_when_the_service_fails(self, client, fake_lnbits, ledger):
        """A caller who pays and gets nothing must be able to retry."""
        quote = client.post("/search/query", json={"query": "bitcoin"})
        payment_hash = quote.json()["payment_hash"]
        fake_lnbits.settle(payment_hash)

        with patch(
            "src.agents.search_agent.search_agent.SearchAgent.search",
            new=AsyncMock(return_value={"error": "all search backends failed"}),
        ):
            failed = client.post(
                "/search/query", json={"query": "bitcoin", "payment_hash": payment_hash}
            )
        assert failed.status_code == 502

        # The payment was released, so the retry succeeds on the same hash.
        assert ledger.get(payment_hash)["state"] == "issued"
        with patch(
            "src.agents.search_agent.search_agent.SearchAgent.search",
            new=AsyncMock(return_value=SEARCH_RESULT),
        ):
            retry = client.post(
                "/search/query", json={"query": "bitcoin", "payment_hash": payment_hash}
            )
        assert retry.status_code == 200

    def test_a_payment_for_search_cannot_buy_translation(self, client, fake_lnbits):
        quote = client.post("/search/query", json={"query": "bitcoin"})
        payment_hash = quote.json()["payment_hash"]
        fake_lnbits.settle(payment_hash)

        response = client.post(
            "/polyglot/translate",
            json={"text": "hello", "target_lang": "es", "payment_hash": payment_hash},
        )

        assert response.status_code == 402
        assert response.json()["error"] == "wrong_service"

    def test_an_lnbits_outage_never_yields_free_service(self, client, fake_lnbits):
        quote = client.post("/search/query", json={"query": "bitcoin"})
        payment_hash = quote.json()["payment_hash"]
        fake_lnbits.settle(payment_hash)
        fake_lnbits.unreachable = True

        with patch(
            "src.agents.search_agent.search_agent.SearchAgent.search",
            new=AsyncMock(return_value=SEARCH_RESULT),
        ) as search:
            response = client.post(
                "/search/query", json={"query": "bitcoin", "payment_hash": payment_hash}
            )

        assert response.status_code == 503
        search.assert_not_awaited(), "the service ran despite an unverifiable payment"


class TestSyntheticDemos:
    def test_streamfinder_is_free_and_says_so(self, client):
        body = client.post(
            "/a2a",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "streamfinder.search",
                "params": {"query": "Matrix"},
            },
        ).json()

        assert body["result"]["synthetic"] is True
        assert "demo" in body["result"]["notice"].lower()

    def test_no_priced_service_can_return_mock_output(self, client):
        """Nothing that charges may be labelled synthetic."""
        for service in client.get("/services").json()["services"]:
            if service.get("synthetic"):
                assert service["price_sats"] == 0


class TestOperationalEndpoints:
    def test_health_reports_real_state(self, client):
        body = client.get("/health").json()

        assert body["status"] == "healthy"
        assert body["ledger"] == "ok"
        assert body["payments"] == "enforced"
        assert "balance_sats" not in body, "health must not publish the wallet balance"

    def test_wallet_balance_is_not_public(self, client):
        assert client.get("/wallet/balance").status_code == 404


class TestDiscoveryAndIdentity:
    async def test_agent_registration_and_discovery(self):
        manager = P2PDiscoveryManager()
        agent = AgentInfo(
            agent_id="test-agent",
            name="TestAgent",
            description="Search services",
            endpoint="https://example.com/search",
            services=["search.query"],
            public_key="a" * 64,
            protocol="lightning+nostr",
            last_seen=0.0,
        )

        await manager.register_agent(agent)
        found = await manager.discover_agents(DiscoveryQuery(service_type="search.query"))

        assert any(a.agent_id == "test-agent" for a in found)

    def test_did_creation_and_trust_scoring(self):
        did_manager = EnhancedDIDManager()
        did = did_manager.create_did("agent-1")

        assert did.startswith("did:")

        score = did_manager.calculate_trust_score("agent-1", [{"success": True, "amount_sats": 10}])
        assert 0.0 <= score.overall_score <= 1.0
        assert score.verification_level in set(TrustLevel)
        assert score.total_interactions == 1


class TestAuthenticationAndAudit:
    def test_api_key_lifecycle(self):
        auth = AuthenticationManager()
        key = auth.generate_api_key("agent-1", ["read"])

        assert auth.verify_api_key(key) is not None
        assert auth.verify_api_key("not-a-real-key") is None

    def test_audit_events_are_recorded(self, tmp_path):
        logger = AuditLogger(log_file=str(tmp_path / "audit.log"))

        logger.log_event(
            event_type=EventType.PAYMENT,
            agent_id="agent-1",
            action="payment_settled",
            details={"amount_sats": 10},
            result="success",
        )

        assert (tmp_path / "audit.log").exists()
