"""
FastAPI router for the agent registry endpoint.

GET /agents/registry                — list locally known agents (paginated)
GET /agents/registry?service=X      — filter by service name
GET /agents/registry/{agent_id}     — single agent lookup
"""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from src.network.p2p_discovery import get_discovery_manager

router = APIRouter(tags=["AgentRegistry"])

# Allowlist: service names are dot/dash/underscore-separated identifiers.
_SERVICE_RE = re.compile(r'^[\w.\-]{1,64}$')

_CACHE_CONTROL = "public, max-age=10"


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class AgentEntry(BaseModel):
    agent_id: str = Field(..., description="Stable unique identifier for this agent")
    name: str = Field(..., description="Human-readable display name")
    description: str = Field(..., description="Short description of what the agent does")
    endpoint: str = Field(..., description="Base URL clients use to reach this agent")
    services: List[str] = Field(..., description="Service capability identifiers offered")
    public_key: str = Field(..., description="Hex-encoded secp256k1 public key")
    protocol: str = Field(..., description="Transport/payment protocol (e.g. lightning+nostr)")
    last_seen: float = Field(..., description="Unix timestamp of last registration or heartbeat")
    reputation_score: float = Field(..., ge=0.0, le=1.0, description="Reputation in [0, 1]")
    capabilities: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary capability metadata")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "agent_id": "bitagent-search",
            "name": "SearchAgent",
            "description": "Web search via Brave/SearXNG/DDG (10 sats)",
            "endpoint": "https://bitagent-production.up.railway.app/search",
            "services": ["search.query"],
            "public_key": "a" * 64,
            "protocol": "lightning+nostr",
            "last_seen": 1747440000.0,
            "reputation_score": 0.0,
            "capabilities": {},
        }
    })


class RegistryListResponse(BaseModel):
    agents: List[AgentEntry] = Field(..., description="Agents matching the query")
    count: int = Field(..., description="Number of agents in this page")
    total: int = Field(..., description="Total matching agents before pagination")
    offset: int = Field(..., description="Offset used for this page")
    limit: int = Field(..., description="Limit used for this page")
    source: str = Field(default="local", description="Data source (always 'local' for now)")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "agents": [],
            "count": 0,
            "total": 0,
            "offset": 0,
            "limit": 50,
            "source": "local",
        }
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_service(service: Optional[str]) -> Optional[str]:
    if service is None:
        return None
    if not _SERVICE_RE.match(service):
        raise HTTPException(
            status_code=422,
            detail="service filter must be 1–64 characters: letters, digits, '.', '-', '_' only",
        )
    return service


def _cached_json(data: dict) -> JSONResponse:
    return JSONResponse(content=data, headers={"Cache-Control": _CACHE_CONTROL})


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/registry",
    response_model=RegistryListResponse,
    summary="List known agents",
    description=(
        "Returns all agents this node has registered or discovered, optionally filtered "
        "by service name. Results are paginated via `limit` and `offset`."
    ),
)
async def list_agents(
    service: Optional[str] = Query(
        default=None,
        description="Filter by service capability (e.g. `search.query`, `translate`)",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
        description="Maximum number of agents to return (1–100)",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of agents to skip before returning results",
    ),
) -> JSONResponse:
    service = _validate_service(service)

    manager = get_discovery_manager()
    all_agents = list(manager.discovered_agents.values())

    if service:
        all_agents = [a for a in all_agents if service in a.services]

    total = len(all_agents)
    page = all_agents[offset: offset + limit]

    body = RegistryListResponse(
        agents=[AgentEntry(**asdict(a)) for a in page],
        count=len(page),
        total=total,
        offset=offset,
        limit=limit,
        source="local",
    )
    return _cached_json(body.model_dump())


@router.get(
    "/registry/{agent_id}",
    response_model=AgentEntry,
    summary="Get agent by ID",
    description="Returns a single agent record by its stable `agent_id`, or 404 if not found.",
    responses={404: {"description": "Agent not found"}},
)
async def get_agent(agent_id: str) -> JSONResponse:
    manager = get_discovery_manager()
    agent = manager.discovered_agents.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    entry = AgentEntry(**asdict(agent))
    return _cached_json(entry.model_dump())
