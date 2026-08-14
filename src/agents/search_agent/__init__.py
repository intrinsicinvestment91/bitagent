import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.agents.search_agent.search_agent import SearchAgent
from src.payments import Quote, paid_work, require_payment

logger = logging.getLogger(__name__)
agent = SearchAgent()
router = APIRouter()

SERVICE_ID = "search.query"


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    num_results: int = Field(default=10, ge=1, le=50)
    payment_hash: str | None = None
    ecash_notes: str | None = None


@router.get("/info")
async def info():
    return agent.get_info()


async def _run_search(query: str, num_results: int) -> dict:
    result = await agent.search(query, num_results)
    if "error" in result:
        # The caller has already paid; surface the upstream failure honestly
        # rather than pretending the search succeeded.
        raise HTTPException(502, result["error"])
    return result


@router.post("/query")
async def query(body: SearchRequest):
    outcome = await require_payment(
        SERVICE_ID,
        body.payment_hash,
        body.ecash_notes,
        memo=f"Search: {body.query[:50]}",
    )
    if isinstance(outcome, Quote):
        return JSONResponse(status_code=outcome.status_code, content=outcome.body)
    async with paid_work(outcome):
        return await _run_search(body.query, body.num_results)


@router.post("/a2a")
async def a2a(body: dict):
    """A2A twin of /query — same service id, so the same price applies.

    This route used to run the search with no payment check at all, which made
    every paid endpoint trivially bypassable.
    """
    method = body.get("method")
    if method != SERVICE_ID:
        return {"error": f"Unknown method '{method}'"}

    params = body.get("params") or {}
    query_str = params.get("query")
    if not query_str:
        return {"error": "Missing 'query'"}

    outcome = await require_payment(
        SERVICE_ID,
        params.get("payment_hash"),
        params.get("ecash_notes"),
        memo=f"Search: {str(query_str)[:50]}",
    )
    if isinstance(outcome, Quote):
        return JSONResponse(status_code=outcome.status_code, content=outcome.body)
    async with paid_work(outcome):
        return await _run_search(query_str, params.get("num_results", 10))
