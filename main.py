#!/usr/bin/env python3
"""
BitAgent — platform-agnostic entry point.
Used for Railway and any cloud PaaS deployment.
Start9 deployment uses start9_server.py instead.
"""

import os
import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.agents.polyglot_agent import router as polyglot_router
from src.agents.coordinator_agent import router as coordinator_router
from src.agents.streamfinder.streamfinder import StreamfinderAgent
from agent_logic import handle_a2a_request, handle_payment_confirmation
from agent_wallet import AgentWallet

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

streamfinder_agent: StreamfinderAgent | None = None
payment_wallet: AgentWallet | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global streamfinder_agent, payment_wallet
    logger.info("Starting BitAgent...")

    streamfinder_agent = StreamfinderAgent()

    try:
        payment_wallet = AgentWallet()
        balance = payment_wallet.get_balance()
        logger.info(f"Wallet balance: {balance} sats")
    except Exception as e:
        logger.warning(f"Wallet init failed (payments disabled): {e}")
        payment_wallet = None

    yield

    logger.info("Shutting down BitAgent...")


app = FastAPI(
    title="BitAgent",
    description="Autonomous Lightning-enabled AI agents",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: set ALLOWED_ORIGINS env var as comma-separated list, or "*" for open access
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8000")
allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    expose_headers=["X-Payment-Required"],
)

app.include_router(polyglot_router, prefix="/polyglot", tags=["PolyglotAgent"])
app.include_router(coordinator_router, prefix="/coordinator", tags=["CoordinatorAgent"])


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/")
async def root():
    return {
        "name": "BitAgent",
        "agents": ["polyglot", "coordinator", "streamfinder"],
        "docs": "/docs",
    }


@app.post("/a2a")
async def a2a_endpoint(request: Request):
    body = await request.json()
    method = body.get("method", "")
    params = body.get("params", {})
    request_id = body.get("id", 1)

    if method.startswith("streamfinder.") and streamfinder_agent:
        result = await streamfinder_agent.handle_a2a(method, params)
        return {"jsonrpc": "2.0", "result": result, "id": request_id}

    result = await handle_a2a_request(method, params)
    return {"jsonrpc": "2.0", "result": result, "id": request_id}


@app.post("/payment/confirm")
async def confirm_payment(request: Request):
    body = await request.json()
    return await handle_payment_confirmation(body)


@app.get("/wallet/balance")
async def wallet_balance():
    if not payment_wallet:
        raise HTTPException(503, "Wallet not initialized")
    return {"balance_sats": payment_wallet.get_balance()}


@app.get("/agents/status")
async def agents_status():
    return {
        "polyglot": {"status": "running", "port": None},
        "coordinator": {"status": "running", "port": None},
        "streamfinder": {"status": "running" if streamfinder_agent else "unavailable"},
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "false").lower() == "true",
    )
