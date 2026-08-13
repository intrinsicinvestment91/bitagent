import logging
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.agents.price_oracle_agent.price_oracle import PriceOracleAgent
from src.payments import Quote, paid_work, require_payment

logger = logging.getLogger(__name__)
agent = PriceOracleAgent()
router = APIRouter()

MAX_COINS = 10


class ConvertRequest(BaseModel):
    sats: int = Field(ge=0)
    payment_hash: Optional[str] = None
    ecash_notes: Optional[str] = None


class BatchRequest(BaseModel):
    coins: list[str] = Field(min_length=1, max_length=MAX_COINS)
    payment_hash: Optional[str] = None
    ecash_notes: Optional[str] = None


@router.get("/info")
async def info():
    return agent.get_info()


@router.get("/price/{coin}")
async def price_single(coin: str, payment_hash: Optional[str] = None):
    outcome = await require_payment("oracle.price", payment_hash, memo=f"Price: {coin}")
    if isinstance(outcome, Quote):
        return JSONResponse(status_code=outcome.status_code, content=outcome.body)

    async with paid_work(outcome):
        result = await agent.price([coin.lower()])
        return {"coin": coin, **result.get(coin.lower(), {"error": "Not found"})}


@router.post("/prices")
async def price_batch(body: BatchRequest):
    coins = [c.lower() for c in body.coins[:MAX_COINS]]
    outcome = await require_payment(
        "oracle.prices",
        body.payment_hash,
        body.ecash_notes,
        memo=f"Prices: {','.join(coins)}",
    )
    if isinstance(outcome, Quote):
        return JSONResponse(status_code=outcome.status_code, content=outcome.body)
    async with paid_work(outcome):
        return await agent.price(coins)


@router.post("/convert")
async def convert(body: ConvertRequest):
    outcome = await require_payment(
        "oracle.convert",
        body.payment_hash,
        body.ecash_notes,
        memo=f"Convert {body.sats} sats",
    )
    if isinstance(outcome, Quote):
        return JSONResponse(status_code=outcome.status_code, content=outcome.body)
    async with paid_work(outcome):
        return await agent.convert(body.sats)


@router.post("/a2a")
async def a2a(body: dict):
    """A2A twins of the three priced routes above — same service ids, same prices."""
    method = body.get("method")
    params = body.get("params") or {}

    if method not in {"oracle.price", "oracle.prices", "oracle.convert"}:
        return {"error": f"Unknown method '{method}'"}

    outcome = await require_payment(
        method, params.get("payment_hash"), params.get("ecash_notes"), memo=method
    )
    if isinstance(outcome, Quote):
        return JSONResponse(status_code=outcome.status_code, content=outcome.body)

    async with paid_work(outcome):
        if method == "oracle.price":
            coin = str(params.get("coin", "bitcoin")).lower()
            result = await agent.price([coin])
            return result.get(coin, {"error": "Not found"})

        if method == "oracle.prices":
            coins = [str(c).lower() for c in params.get("coins", ["bitcoin"])[:MAX_COINS]]
            return await agent.price(coins)

        return await agent.convert(params.get("sats", 0))
