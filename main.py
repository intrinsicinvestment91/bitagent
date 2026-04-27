#!/usr/bin/env python3
"""
BitAgent — platform-agnostic entry point.
Used for Railway and any cloud PaaS deployment.
Start9 deployment uses start9_server.py instead.
"""

import os
import logging
import asyncio
import time
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.agents.polyglot_agent import router as polyglot_router
from src.agents.coordinator_agent import router as coordinator_router
from src.agents.price_oracle_agent import router as oracle_router
from src.agents.web_fetch_agent import router as fetch_router
from src.agents.search_agent import router as search_router
from src.agents.streamfinder.streamfinder import StreamfinderAgent
from src.agents.identity_agent.store import get_identity_by_handle
from src.core.request import validate_request_envelope
from agent_logic import handle_a2a_request, handle_payment_confirmation
from agent_wallet import AgentWallet

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

streamfinder_agent: StreamfinderAgent | None = None
payment_wallet: AgentWallet | None = None
REQUEST_ENVELOPE_METRICS = {
    "valid": 0,
    "invalid": 0,
}


def record_request_envelope_metric(is_valid: bool) -> None:
    if is_valid:
        REQUEST_ENVELOPE_METRICS["valid"] += 1
    else:
        REQUEST_ENVELOPE_METRICS["invalid"] += 1


def _build_base_url() -> str:
    if domain := os.getenv("RAILWAY_PUBLIC_DOMAIN"):
        return f"https://{domain}"
    return os.getenv("PUBLIC_URL", "http://localhost:8000")


async def _broadcast_agents(base_url: str, nostr_private_key: str | None) -> None:
    try:
        from src.network.p2p_discovery import P2PDiscoveryManager, AgentInfo

        manager = P2PDiscoveryManager(nostr_private_key)
        pubkey = manager.nostr_discovery.public_key.hex()

        agents = [
            AgentInfo(
                agent_id="bitagent-polyglot",
                name="PolyglotAgent",
                description="Translation and transcription (100–250 sats)",
                endpoint=f"{base_url}/polyglot",
                services=["translate", "transcribe"],
                public_key=pubkey,
                protocol="lightning+nostr",
                last_seen=time.time(),
            ),
            AgentInfo(
                agent_id="bitagent-coordinator",
                name="CoordinatorAgent",
                description="Multi-agent workflow coordinator (350 sats)",
                endpoint=f"{base_url}/coordinator",
                services=["coordinate"],
                public_key=pubkey,
                protocol="lightning+nostr",
                last_seen=time.time(),
            ),
            AgentInfo(
                agent_id="bitagent-oracle",
                name="PriceOracleAgent",
                description="Crypto price lookups via CoinGecko/Binance (2 sats)",
                endpoint=f"{base_url}/oracle",
                services=["price", "prices", "convert"],
                public_key=pubkey,
                protocol="lightning+nostr",
                last_seen=time.time(),
            ),
            AgentInfo(
                agent_id="bitagent-fetch",
                name="WebFetchAgent",
                description="Fetch web content with SSRF protection (25 sats)",
                endpoint=f"{base_url}/fetch",
                services=["fetch.url"],
                public_key=pubkey,
                protocol="lightning+nostr",
                last_seen=time.time(),
            ),
            AgentInfo(
                agent_id="bitagent-search",
                name="SearchAgent",
                description="Web search via Brave/SearXNG/DDG (10 sats)",
                endpoint=f"{base_url}/search",
                services=["search.query"],
                public_key=pubkey,
                protocol="lightning+nostr",
                last_seen=time.time(),
            ),
            AgentInfo(
                agent_id="bitagent-identity",
                name="IdentityAgent",
                description="NIP-05 registration and trust scoring (10–1000 sats)",
                endpoint=f"{base_url}/a2a",
                services=["identity.register_nip05", "identity.get_identity", "identity.get_trust_signal"],
                public_key=pubkey,
                protocol="lightning+nostr",
                last_seen=time.time(),
            ),
        ]

        for agent_info in agents:
            await manager.register_agent(agent_info)

        logger.info("Broadcasted %d agents to Nostr relays", len(agents))
    except Exception as e:
        logger.warning("Nostr agent broadcast failed: %s", e)


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

    base_url = _build_base_url()
    nostr_key = os.getenv("NOSTR_PRIVATE_KEY")
    asyncio.create_task(_broadcast_agents(base_url, nostr_key))
    logger.info("Nostr broadcast scheduled for %s", base_url)

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
app.include_router(oracle_router, prefix="/oracle", tags=["PriceOracleAgent"])
app.include_router(fetch_router, prefix="/fetch", tags=["WebFetchAgent"])
app.include_router(search_router, prefix="/search", tags=["SearchAgent"])


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/")
async def root():
    return {
        "name": "BitAgent",
        "agents": ["polyglot", "coordinator", "oracle", "fetch", "search", "streamfinder", "identity"],
        "docs": "/docs",
    }


def _is_not_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return True
    try:
        parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed >= datetime.now(timezone.utc)


@app.get("/.well-known/nostr.json")
async def nostr_well_known(request: Request, name: str | None = None):
    if not name:
        return {"names": {}}

    domain = request.url.hostname or ""
    identity = get_identity_by_handle(name, domain)
    if not identity:
        return {"names": {}}
    if not identity.get("paid") or not identity.get("verified"):
        return {"names": {}}
    if not _is_not_expired(identity.get("expires_at")):
        return {"names": {}}

    pubkey = identity["pubkey"]
    return {
        "names": {name: pubkey},
        "relays": {pubkey: identity.get("relays", [])},
    }


@app.post("/a2a")
async def a2a_endpoint(request: Request):
    body = await request.json()
    is_valid_envelope = validate_request_envelope(body)
    record_request_envelope_metric(is_valid_envelope)
    if not is_valid_envelope:
        logger.warning("Invalid request envelope received; continuing in compatibility mode")
    method = body.get("method", "")
    params = body.get("params", {})
    request_id = body.get("id", 1)

    result = await handle_a2a_request(method, params)
    return {"jsonrpc": "2.0", "result": result, "id": request_id}


@app.get("/internal/request-envelope-metrics")
def get_request_envelope_metrics():
    return dict(REQUEST_ENVELOPE_METRICS)


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
        "polyglot": {"status": "running"},
        "coordinator": {"status": "running"},
        "oracle": {"status": "running"},
        "fetch": {"status": "running"},
        "search": {"status": "running"},
        "streamfinder": {"status": "running" if streamfinder_agent else "unavailable"},
        "identity": {"status": "running"},
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "false").lower() == "true",
    )
