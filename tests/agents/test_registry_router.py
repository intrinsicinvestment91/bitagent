"""
Tests for GET /agents/registry and GET /agents/registry/{agent_id}.

Covers: response shape, pagination, service filter (valid + invalid),
        Cache-Control header, single-agent lookup, and 404 path.
"""

import time
import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport

from main import app
from src.network.p2p_discovery import AgentInfo

_GET_MGR = "src.network.registry_router.get_discovery_manager"


def _make_agent(agent_id: str, services: list[str], score: float = 0.0) -> AgentInfo:
    return AgentInfo(
        agent_id=agent_id,
        name=agent_id.title(),
        description=f"Test agent {agent_id}",
        endpoint=f"http://localhost/{agent_id}",
        services=services,
        public_key="aa" * 32,
        protocol="lightning+nostr",
        last_seen=time.time(),
        reputation_score=score,
    )


def _stub_manager(*agents: AgentInfo) -> MagicMock:
    mgr = MagicMock()
    mgr.discovered_agents = {a.agent_id: a for a in agents}
    return mgr


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# GET /agents/registry — list
# ---------------------------------------------------------------------------

class TestRegistryList:

    async def test_empty_registry_returns_zero(self, client):
        with patch(_GET_MGR, return_value=_stub_manager()):
            async with client as c:
                r = await c.get("/agents/registry")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 0
        assert body["total"] == 0
        assert body["agents"] == []
        assert body["source"] == "local"

    async def test_returns_all_agents(self, client):
        agents = [_make_agent("search", ["search.query"]), _make_agent("oracle", ["price"])]
        with patch(_GET_MGR, return_value=_stub_manager(*agents)):
            async with client as c:
                r = await c.get("/agents/registry")
        body = r.json()
        assert body["count"] == 2
        assert body["total"] == 2
        ids = {a["agent_id"] for a in body["agents"]}
        assert ids == {"search", "oracle"}

    async def test_service_filter_matches(self, client):
        agents = [
            _make_agent("search", ["search.query"]),
            _make_agent("oracle", ["price"]),
        ]
        with patch(_GET_MGR, return_value=_stub_manager(*agents)):
            async with client as c:
                r = await c.get("/agents/registry?service=search.query")
        body = r.json()
        assert body["count"] == 1
        assert body["total"] == 1
        assert body["agents"][0]["agent_id"] == "search"

    async def test_service_filter_no_match_returns_empty(self, client):
        with patch(_GET_MGR, return_value=_stub_manager(_make_agent("oracle", ["price"]))):
            async with client as c:
                r = await c.get("/agents/registry?service=translate")
        body = r.json()
        assert body["count"] == 0
        assert body["total"] == 0

    async def test_agent_fields_present(self, client):
        agent = _make_agent("fetch", ["fetch.url"], score=0.5)
        with patch(_GET_MGR, return_value=_stub_manager(agent)):
            async with client as c:
                r = await c.get("/agents/registry")
        a = r.json()["agents"][0]
        for field in ("agent_id", "name", "description", "endpoint", "services",
                      "public_key", "protocol", "last_seen", "reputation_score", "capabilities"):
            assert field in a, f"missing field: {field}"

    async def test_cache_control_header_present(self, client):
        with patch(_GET_MGR, return_value=_stub_manager()):
            async with client as c:
                r = await c.get("/agents/registry")
        assert "cache-control" in r.headers
        assert "max-age" in r.headers["cache-control"]


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class TestRegistryPagination:

    def _many_agents(self, n: int) -> list[AgentInfo]:
        return [_make_agent(f"agent-{i}", ["svc"]) for i in range(n)]

    async def test_limit_respected(self, client):
        agents = self._many_agents(20)
        with patch(_GET_MGR, return_value=_stub_manager(*agents)):
            async with client as c:
                r = await c.get("/agents/registry?limit=5")
        body = r.json()
        assert body["count"] == 5
        assert body["total"] == 20
        assert body["limit"] == 5
        assert body["offset"] == 0

    async def test_offset_respected(self, client):
        agents = self._many_agents(10)
        with patch(_GET_MGR, return_value=_stub_manager(*agents)):
            async with client as c:
                r = await c.get("/agents/registry?limit=4&offset=8")
        body = r.json()
        assert body["count"] == 2       # only 2 remain after offset 8
        assert body["total"] == 10
        assert body["offset"] == 8

    async def test_offset_beyond_total_returns_empty(self, client):
        agents = self._many_agents(3)
        with patch(_GET_MGR, return_value=_stub_manager(*agents)):
            async with client as c:
                r = await c.get("/agents/registry?offset=10")
        body = r.json()
        assert body["count"] == 0
        assert body["total"] == 3

    async def test_limit_above_100_rejected(self, client):
        with patch(_GET_MGR, return_value=_stub_manager()):
            async with client as c:
                r = await c.get("/agents/registry?limit=101")
        assert r.status_code == 422

    async def test_limit_zero_rejected(self, client):
        with patch(_GET_MGR, return_value=_stub_manager()):
            async with client as c:
                r = await c.get("/agents/registry?limit=0")
        assert r.status_code == 422

    async def test_negative_offset_rejected(self, client):
        with patch(_GET_MGR, return_value=_stub_manager()):
            async with client as c:
                r = await c.get("/agents/registry?offset=-1")
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Service filter validation
# ---------------------------------------------------------------------------

class TestServiceFilterValidation:

    async def test_valid_dotted_service_accepted(self, client):
        with patch(_GET_MGR, return_value=_stub_manager()):
            async with client as c:
                r = await c.get("/agents/registry?service=search.query")
        assert r.status_code == 200

    async def test_valid_hyphenated_service_accepted(self, client):
        with patch(_GET_MGR, return_value=_stub_manager()):
            async with client as c:
                r = await c.get("/agents/registry?service=my-service_v2")
        assert r.status_code == 200

    async def test_shell_injection_rejected(self, client):
        with patch(_GET_MGR, return_value=_stub_manager()):
            async with client as c:
                r = await c.get("/agents/registry?service=foo;rm+-rf+/")
        assert r.status_code == 422

    async def test_too_long_service_rejected(self, client):
        with patch(_GET_MGR, return_value=_stub_manager()):
            async with client as c:
                r = await c.get(f"/agents/registry?service={'x' * 65}")
        assert r.status_code == 422

    async def test_empty_service_param_treated_as_absent(self, client):
        """Empty string fails the regex (min length 1) → 422."""
        with patch(_GET_MGR, return_value=_stub_manager()):
            async with client as c:
                r = await c.get("/agents/registry?service=")
        assert r.status_code == 422

    async def test_sql_injection_chars_rejected(self, client):
        with patch(_GET_MGR, return_value=_stub_manager()):
            async with client as c:
                r = await c.get("/agents/registry?service=foo'OR'1'='1")
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /agents/registry/{agent_id}
# ---------------------------------------------------------------------------

class TestRegistryGetById:

    async def test_returns_known_agent(self, client):
        agent = _make_agent("oracle", ["price"])
        with patch(_GET_MGR, return_value=_stub_manager(agent)):
            async with client as c:
                r = await c.get("/agents/registry/oracle")
        assert r.status_code == 200
        assert r.json()["agent_id"] == "oracle"

    async def test_unknown_agent_returns_404(self, client):
        with patch(_GET_MGR, return_value=_stub_manager()):
            async with client as c:
                r = await c.get("/agents/registry/nonexistent")
        assert r.status_code == 404

    async def test_404_detail_contains_agent_id(self, client):
        with patch(_GET_MGR, return_value=_stub_manager()):
            async with client as c:
                r = await c.get("/agents/registry/missing-agent")
        assert "missing-agent" in r.json()["detail"]

    async def test_single_agent_cache_control_present(self, client):
        agent = _make_agent("oracle", ["price"])
        with patch(_GET_MGR, return_value=_stub_manager(agent)):
            async with client as c:
                r = await c.get("/agents/registry/oracle")
        assert "cache-control" in r.headers
