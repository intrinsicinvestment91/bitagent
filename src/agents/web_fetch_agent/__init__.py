import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.agents.web_fetch_agent.web_fetch import WebFetchAgent
from src.wallets.fedimint_wallet import FedimintWallet

logger = logging.getLogger(__name__)
agent = WebFetchAgent()
router = APIRouter()
_fedimint = FedimintWallet()

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
        inv = {
            "payment_required": True,
            "amount_sats": agent.price_sats,
            "payment_request": data.get("bolt11") or data.get("payment_request"),
            "payment_hash": data.get("payment_hash"),
        }
        if _fedimint.enabled:
            inv["ecash_accepted"] = True
            inv["ecash_amount_msats"] = agent.price_sats * 1000
        return inv
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


class FetchRequest(BaseModel):
    url: str
    payment_hash: Optional[str] = None
    ecash_notes: Optional[str] = None


@router.get("/info")
async def info():
    return agent.get_info()


@router.post("/url")
async def fetch(body: FetchRequest):
    if body.ecash_notes:
        if not await _fedimint.verify_and_receive(body.ecash_notes, agent.price_sats):
            raise HTTPException(402, "Ecash payment invalid or insufficient")
    elif body.payment_hash:
        if not _verify(body.payment_hash):
            raise HTTPException(402, "Payment not verified")
    else:
        inv = _invoice(f"Fetch: {body.url[:60]}")
        if inv:
            return JSONResponse(status_code=402, content=inv)

    result = await agent.fetch(body.url)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/a2a")
async def a2a(body: dict):
    method = body.get("method")
    params = body.get("params", {})

    if method == "fetch.url":
        url = params.get("url")
        if not url:
            return {"error": "Missing 'url'"}
        return await agent.fetch(url)

    return {"error": f"Unknown method '{method}'"}
