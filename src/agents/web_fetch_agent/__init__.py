import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.agents.web_fetch_agent.web_fetch import WebFetchAgent
from src.payments import Quote, paid_work, require_payment

logger = logging.getLogger(__name__)
agent = WebFetchAgent()
router = APIRouter()

SERVICE_ID = "fetch.url"


class FetchRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    payment_hash: Optional[str] = None
    ecash_notes: Optional[str] = None


@router.get("/info")
async def info():
    return agent.get_info()


async def _run_fetch(url: str) -> dict:
    result = await agent.fetch(url)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/url")
async def fetch(body: FetchRequest):
    outcome = await require_payment(
        SERVICE_ID,
        body.payment_hash,
        body.ecash_notes,
        memo=f"Fetch: {body.url[:60]}",
    )
    if isinstance(outcome, Quote):
        return JSONResponse(status_code=outcome.status_code, content=outcome.body)
    async with paid_work(outcome):
        return await _run_fetch(body.url)


@router.post("/a2a")
async def a2a(body: dict):
    """A2A twin of /url — same service id, same price."""
    method = body.get("method")
    if method != SERVICE_ID:
        return {"error": f"Unknown method '{method}'"}

    params = body.get("params") or {}
    url = params.get("url")
    if not url:
        return {"error": "Missing 'url'"}

    outcome = await require_payment(
        SERVICE_ID,
        params.get("payment_hash"),
        params.get("ecash_notes"),
        memo=f"Fetch: {str(url)[:60]}",
    )
    if isinstance(outcome, Quote):
        return JSONResponse(status_code=outcome.status_code, content=outcome.body)
    async with paid_work(outcome):
        return await _run_fetch(url)
