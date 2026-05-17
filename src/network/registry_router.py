"""
FastAPI router for the agent registry endpoint.

GET /agents/registry           — all locally known agents
GET /agents/registry?service=X — filtered by service name
GET /agents/registry/{agent_id} — single agent lookup
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from src.network.p2p_discovery import get_discovery_manager

router = APIRouter(tags=["AgentRegistry"])


@router.get("/registry")
async def list_agents(service: Optional[str] = Query(default=None)):
    """Return all locally registered/discovered agents, optionally filtered by service."""
    manager = get_discovery_manager()
    agents = list(manager.discovered_agents.values())

    if service:
        agents = [a for a in agents if service in a.services]

    return {
        "agents": [asdict(a) for a in agents],
        "count": len(agents),
        "source": "local",
    }


@router.get("/registry/{agent_id}")
async def get_agent(agent_id: str):
    """Return a single agent by ID."""
    manager = get_discovery_manager()
    agent = manager.discovered_agents.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return asdict(agent)
