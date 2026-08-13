"""Every paid surface must actually charge.

Each agent exposed an ``/a2a`` sub-router that ran the same work as its paid HTTP
route with no payment check, and the top-level ``POST /a2a`` dispatched
``oracle.*``, ``fetch.*`` and ``search.*`` for free. These tests drive the real
app and fail if any of that comes back.
"""

import pytest
from fastapi.testclient import TestClient

import main
from src.payments import SERVICES, configure_gate

#: (HTTP method, path, body) for every priced route, paired with its A2A twin.
PAID_HTTP_ROUTES = [
    ("POST", "/search/query", {"query": "bitcoin"}),
    ("POST", "/fetch/url", {"url": "https://example.com"}),
    ("GET", "/oracle/price/bitcoin", None),
    ("POST", "/oracle/prices", {"coins": ["bitcoin"]}),
    ("POST", "/oracle/convert", {"sats": 1000}),
    ("POST", "/polyglot/translate", {"text": "hello", "target_lang": "es"}),
]

AGENT_A2A_ROUTES = [
    ("/search/a2a", "search.query", {"query": "bitcoin"}),
    ("/fetch/a2a", "fetch.url", {"url": "https://example.com"}),
    ("/oracle/a2a", "oracle.price", {"coin": "bitcoin"}),
    ("/oracle/a2a", "oracle.prices", {"coins": ["bitcoin"]}),
    ("/oracle/a2a", "oracle.convert", {"sats": 1000}),
    ("/polyglot/a2a", "polyglot.translate", {"text": "hello"}),
    ("/coordinator/a2a", "coordinator.chain_tasks", {"tasks": [{"service": "x", "parameters": {}}]}),
]

TOP_LEVEL_A2A_METHODS = [
    ("search.query", {"query": "bitcoin"}),
    ("fetch.url", {"url": "https://example.com"}),
    ("oracle.price", {"coin": "bitcoin"}),
    ("oracle.prices", {"coins": ["bitcoin"]}),
    ("oracle.convert", {"sats": 1000}),
    ("identity.get_identity", {"pubkey": "a" * 64}),
    ("identity.get_trust_signal", {"pubkey": "a" * 64}),
    ("identity.search", {"query": "alice"}),
]


@pytest.fixture
def client(tmp_path, paid_gate, monkeypatch):
    from src.agents.identity_agent import store

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "identity_agent.db")
    monkeypatch.setenv("IDENTITY_FREE_QUERIES", "false")
    # Rate limiting would otherwise reject the later cases in these sweeps.
    monkeypatch.setenv("RATE_LIMIT", "false")
    with TestClient(main.app) as test_client:
        configure_gate(paid_gate)
        yield test_client


def _request(client, method, path, body):
    if method == "GET":
        return client.get(path)
    return client.post(path, json=body)


class TestPaidHttpRoutes:
    @pytest.mark.parametrize("method,path,body", PAID_HTTP_ROUTES)
    def test_route_demands_payment_before_doing_work(self, client, method, path, body):
        response = _request(client, method, path, body)

        assert response.status_code == 402, f"{path} served without payment"
        assert response.json()["payment_required"] is True
        assert response.json()["payment_request"].startswith("lnbc")


class TestAgentA2ATwins:
    @pytest.mark.parametrize("path,method,params", AGENT_A2A_ROUTES)
    def test_a2a_twin_costs_the_same_as_its_http_route(self, client, path, method, params):
        response = client.post(path, json={"method": method, "params": params})

        assert response.status_code == 402, f"{path}:{method} is a free bypass"
        body = response.json()
        assert body["payment_required"] is True
        assert body["amount_sats"] == SERVICES[method].price_sats


class TestTopLevelA2A:
    @pytest.mark.parametrize("method,params", TOP_LEVEL_A2A_METHODS)
    def test_dispatcher_demands_payment(self, client, method, params):
        body = client.post(
            "/a2a", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        ).json()

        assert "error" in body, f"/a2a {method} returned a result without payment"
        assert body["error"]["code"] == -32000
        assert body["error"]["data"]["amount_sats"] == SERVICES[method].price_sats


class TestEveryPricedServiceIsReachableAndGated:
    def test_no_priced_service_is_missing_from_the_a2a_method_map(self):
        """A new priced service must be wired into the dispatcher, not orphaned."""
        from agent_logic import METHOD_SERVICES

        unmapped = {
            sid
            for sid, svc in SERVICES.items()
            if svc.price_sats > 0 and sid not in METHOD_SERVICES and not sid.startswith("coordinator.")
        }
        assert not unmapped, f"priced services missing from the A2A map: {unmapped}"


class TestFreeModeIsLabelled:
    def test_health_reports_disabled_payments(self, tmp_path, free_gate, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT", "false")
        with TestClient(main.app) as client:
            configure_gate(free_gate)
            body = client.get("/health").json()

        assert body["payments"] == "disabled"
        assert "notice" in body

    def test_services_endpoint_lists_prices_and_synthetic_flags(self, client):
        body = client.get("/services").json()

        by_id = {s["id"]: s for s in body["services"]}
        assert by_id["search.query"]["price_sats"] == 10
        assert by_id["streamfinder.search"]["synthetic"] is True
        assert by_id["streamfinder.search"]["price_sats"] == 0
