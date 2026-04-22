import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.agents.search_agent.search_agent import SearchAgent

logger = logging.getLogger(__name__)
agent = SearchAgent()
router = APIRouter()

_wallet = None


def _get_wallet():
    global _wallet
    if _wallet is None:
        try:
            from agent_wallet import AgentWallet
            _wallet = AgentWallet()
        except Exception:
            pass
    return _wallet


def _invoice(memo: str):
    wallet = _get_wallet()
    if not wallet:
        return None
    try:
        data = wallet.create_invoice(agent.price_sats, memo)
        return {
            "payment_required": True,
            "amount_sats": agent.price_sats,
            "payment_request": data.get("bolt11") or data.get("payment_request"),
            "payment_hash": data.get("payment_hash"),
        }
    except Exception as e:
        logger.warning(f"Invoice creation failed: {e}")
        return None


def _verify(payment_hash: str) -> bool:
    wallet = _get_wallet()
    if not wallet:
        return True
    try:
        return wallet.check_invoice(payment_hash)
    except Exception:
        return False


class SearchRequest(BaseModel):
    query: str
    num_results: int = 10
    payment_hash: Optional[str] = None


@router.get("/info")
async def info():
    return agent.get_info()


@router.post("/query")
async def query(body: SearchRequest):
    if body.payment_hash:
        if not _verify(body.payment_hash):
            raise HTTPException(402, "Payment not verified")
    else:
        inv = _invoice(f"Search: {body.query[:50]}")
        if inv:
            return JSONResponse(status_code=402, content=inv)

    result = await agent.search(body.query, body.num_results)
    if "error" in result:
        raise HTTPException(500, result["error"])
    return result


@router.post("/a2a")
async def a2a(body: dict):
    method = body.get("method")
    params = body.get("params", {})

    if method == "search.query":
        query_str = params.get("query")
        if not query_str:
            return {"error": "Missing 'query'"}
        num = params.get("num_results", 10)
        return await agent.search(query_str, num)

    return {"error": f"Unknown method '{method}'"}
