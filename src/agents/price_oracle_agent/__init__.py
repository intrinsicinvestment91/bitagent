import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from src.agents.price_oracle_agent.price_oracle import PriceOracleAgent
from src.wallets.fedimint_wallet import FedimintWallet

logger = logging.getLogger(__name__)
agent = PriceOracleAgent()
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


def _invoice(price: int, memo: str):
    wallet = _get_wallet()
    if not wallet:
        return None
    try:
        data = wallet.create_invoice(price, memo)
        inv = {
            "payment_required": True,
            "amount_sats": price,
            "payment_request": data.get("bolt11") or data.get("payment_request"),
            "payment_hash": data.get("payment_hash"),
        }
        if _fedimint.enabled:
            inv["ecash_accepted"] = True
            inv["ecash_amount_msats"] = price * 1000
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


class ConvertRequest(BaseModel):
    sats: int
    payment_hash: Optional[str] = None
    ecash_notes: Optional[str] = None

class BatchRequest(BaseModel):
    coins: list[str]
    payment_hash: Optional[str] = None
    ecash_notes: Optional[str] = None


@router.get("/info")
async def info():
    return agent.get_info()


@router.get("/price/{coin}")
async def price_single(coin: str, payment_hash: Optional[str] = None):
    price = agent.price_sats["single"]

    if payment_hash:
        if not _verify(payment_hash):
            raise HTTPException(402, "Payment not verified")
    else:
        inv = _invoice(price, f"Price: {coin}")
        if inv:
            return JSONResponse(status_code=402, content=inv)

    result = await agent.price([coin.lower()])
    return {"coin": coin, **result.get(coin.lower(), {"error": "Not found"})}


@router.post("/prices")
async def price_batch(body: BatchRequest):
    coins = [c.lower() for c in body.coins[:10]]
    price = agent.price_sats["batch"]

    if body.ecash_notes:
        if not await _fedimint.verify_and_receive(body.ecash_notes, price):
            raise HTTPException(402, "Ecash payment invalid or insufficient")
    elif body.payment_hash:
        if not _verify(body.payment_hash):
            raise HTTPException(402, "Payment not verified")
    else:
        inv = _invoice(price, f"Prices: {','.join(coins)}")
        if inv:
            return JSONResponse(status_code=402, content=inv)

    return await agent.price(coins)


@router.post("/convert")
async def convert(body: ConvertRequest):
    price = agent.price_sats["convert"]

    if body.ecash_notes:
        if not await _fedimint.verify_and_receive(body.ecash_notes, price):
            raise HTTPException(402, "Ecash payment invalid or insufficient")
    elif body.payment_hash:
        if not _verify(body.payment_hash):
            raise HTTPException(402, "Payment not verified")
    else:
        inv = _invoice(price, f"Convert {body.sats} sats")
        if inv:
            return JSONResponse(status_code=402, content=inv)

    return await agent.convert(body.sats)


@router.post("/a2a")
async def a2a(body: dict):
    method = body.get("method")
    params = body.get("params", {})

    if method == "oracle.price":
        coin = params.get("coin", "bitcoin")
        result = await agent.price([coin.lower()])
        return result.get(coin.lower(), {"error": "Not found"})

    if method == "oracle.prices":
        coins = [c.lower() for c in params.get("coins", ["bitcoin"])]
        return await agent.price(coins)

    if method == "oracle.convert":
        sats = params.get("sats", 0)
        return await agent.convert(sats)

    return {"error": f"Unknown method '{method}'"}
