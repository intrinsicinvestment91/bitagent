"""
Tests for GET /agents/registry and GET /agents/registry/{agent_id}.

Uses httpx AsyncClient against the FastAPI app with get_discovery_manager
patched to a controlled stub — no real Nostr/DHT I/O.
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


class TestRegistryList:
    """GET /agents/registry"""

    async def test_empty_registry_returns_zero(self, client):
        with patch(_GET_MGR, return_value=_stub_manager()):
            async with client as c:
                r = await c.get("/agents/registry")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 0
        assert body["agents"] == []
        assert body["source"] == "local"

    async def test_returns_all_agents(self, client):
        agents = [_make_agent("search", ["search.query"]), _make_agent("oracle", ["price"])]
        with patch(_GET_MGR, return_value=_stub_manager(*agents)):
            async with client as c:
                r = await c.get("/agents/registry")
        body = r.json()
        assert body["count"] == 2
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
        assert body["agents"][0]["agent_id"] == "search"

    async def test_service_filter_no_match_returns_empty(self, client):
        with patch(_GET_MGR, return_value=_stub_manager(_make_agent("oracle", ["price"]))):
            async with client as c:
                r = await c.get("/agents/registry?service=translate")
        body = r.json()
        assert body["count"] == 0

    async def test_agent_fields_present(self, client):
        agent = _make_agent("fetch", ["fetch.url"], score=0.5)
        with patch(_GET_MGR, return_value=_stub_manager(agent)):
            async with client as c:
                r = await c.get("/agents/registry")
        a = r.json()["agents"][0]
        for field in ("agent_id", "name", "description", "endpoint", "services",
                      "public_key", "protocol", "last_seen", "reputation_score", "capabilities"):
            assert field in a, f"missing field: {field}"


class TestRegistryGetById:
    """GET /agents/registry/{agent_id}"""

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
