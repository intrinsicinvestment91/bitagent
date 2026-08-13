#!/usr/bin/env python3
"""BitAgent — platform-agnostic entry point.

Used for Railway and any cloud PaaS deployment. Start9 deployment uses
start9_server.py instead.
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent_logic import handle_a2a_request
from src.agents.coordinator_agent import router as coordinator_router
from src.agents.identity_agent.store import get_identity_by_handle
from src.agents.polyglot_agent import router as polyglot_router
from src.agents.price_oracle_agent import router as oracle_router
from src.agents.search_agent import router as search_router
from src.agents.streamfinder.streamfinder import StreamfinderAgent
from src.agents.web_fetch_agent import router as fetch_router
from src.api.middleware import (
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
)
from src.network.registry_router import router as registry_router
from src.payments import (
    AsyncLNbitsClient,
    LNbitsError,
    PaymentConfigError,
    PaymentGate,
    PaymentLedger,
    catalog_info,
    configure_gate,
    data_dir,
    get_gate,
    load_config,
)
from src.security.admin_auth import admin_enabled, require_admin
from src.wallets.fedimint_wallet import FedimintWallet

__version__ = "1.0.0"

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", str(1024 * 1024)))
LEDGER_PURGE_INTERVAL_SECONDS = 3600

streamfinder_agent: StreamfinderAgent | None = None
payment_config = None
payment_ledger: PaymentLedger | None = None
lnbits_client: AsyncLNbitsClient | None = None
_background_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    """Start a background task and keep a reference so it is not garbage collected."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _build_base_url() -> str:
    if domain := os.getenv("RAILWAY_PUBLIC_DOMAIN"):
        return f"https://{domain}"
    return os.getenv("PUBLIC_URL", "http://localhost:8000")


def _resolve_cors_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8000")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if "*" in origins and len(origins) > 1:
        logger.warning("ALLOWED_ORIGINS contains '*' alongside specific origins; using '*' only")
        return ["*"]
    return origins


async def _broadcast_agents(base_url: str, nostr_private_key: str | None) -> None:
    try:
        from src.network.p2p_discovery import AgentInfo, get_discovery_manager

        manager = get_discovery_manager(nostr_private_key)
        pubkey = manager.nostr_discovery.public_key.hex()

        def describe(prefix: str) -> str:
            from src.payments import pricing_for

            prices = pricing_for(prefix)
            free = all(p == 0 for p in prices.values())
            return "free (demo)" if free else ", ".join(f"{k}={v} sats" for k, v in prices.items())

        agents = [
            AgentInfo(
                agent_id="bitagent-polyglot",
                name="PolyglotAgent",
                description=f"Translation and transcription ({describe('polyglot')})",
                endpoint=f"{base_url}/polyglot",
                services=["translate", "transcribe"],
                public_key=pubkey,
                protocol="lightning+nostr",
                last_seen=time.time(),
            ),
            AgentInfo(
                agent_id="bitagent-coordinator",
                name="CoordinatorAgent",
                description=f"Multi-agent workflow coordinator ({describe('coordinator')})",
                endpoint=f"{base_url}/coordinator",
                services=["translate_audio", "chain_tasks"],
                public_key=pubkey,
                protocol="lightning+nostr",
                last_seen=time.time(),
            ),
            AgentInfo(
                agent_id="bitagent-oracle",
                name="PriceOracleAgent",
                description=f"Crypto price lookups via CoinGecko/Binance ({describe('oracle')})",
                endpoint=f"{base_url}/oracle",
                services=["price", "prices", "convert"],
                public_key=pubkey,
                protocol="lightning+nostr",
                last_seen=time.time(),
            ),
            AgentInfo(
                agent_id="bitagent-fetch",
                name="WebFetchAgent",
                description=f"Fetch web content with SSRF protection ({describe('fetch')})",
                endpoint=f"{base_url}/fetch",
                services=["fetch.url"],
                public_key=pubkey,
                protocol="lightning+nostr",
                last_seen=time.time(),
            ),
            AgentInfo(
                agent_id="bitagent-search",
                name="SearchAgent",
                description=f"Web search via Brave/SearXNG/DDG ({describe('search')})",
                endpoint=f"{base_url}/search",
                services=["search.query"],
                public_key=pubkey,
                protocol="lightning+nostr",
                last_seen=time.time(),
            ),
            AgentInfo(
                agent_id="bitagent-identity",
                name="IdentityAgent",
                description=f"NIP-05 registration and trust scoring ({describe('identity')})",
                endpoint=f"{base_url}/a2a",
                services=[
                    "identity.register_nip05",
                    "identity.get_identity",
                    "identity.get_trust_signal",
                ],
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


async def _purge_ledger_periodically(ledger: PaymentLedger) -> None:
    """Drop unpaid quotes that can no longer be redeemed."""
    while True:
        try:
            await asyncio.sleep(LEDGER_PURGE_INTERVAL_SECONDS)
            removed = await ledger.apurge_expired()
            if removed:
                logger.info("Purged %d expired invoice quotes", removed)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Ledger purge failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global streamfinder_agent, payment_config, payment_ledger, lnbits_client
    logger.info("Starting BitAgent %s...", __version__)

    streamfinder_agent = StreamfinderAgent()

    payment_ledger = PaymentLedger(data_dir() / "payments.db")
    if payment_config.enabled:
        lnbits_client = AsyncLNbitsClient(payment_config.lnbits_url, payment_config.lnbits_api_key)
        logger.info("Payments enforced via LNbits at %s", payment_config.lnbits_url)
    else:
        lnbits_client = None
        logger.warning(
            "PAYMENTS ARE DISABLED. Every service on this node is free and is "
            "labeled as such in /health and /info. Do not run a production node "
            "in this mode."
        )

    configure_gate(PaymentGate(payment_config, payment_ledger, lnbits_client, FedimintWallet()))

    if not admin_enabled():
        logger.warning(
            "ADMIN_API_KEY is not set; operational endpoints such as "
            "/wallet/balance are not exposed."
        )

    _spawn(_purge_ledger_periodically(payment_ledger))
    _spawn(_broadcast_agents(_build_base_url(), os.getenv("NOSTR_PRIVATE_KEY")))
    logger.info("Nostr broadcast scheduled for %s", _build_base_url())

    yield

    logger.info("Shutting down BitAgent...")
    for task in list(_background_tasks):
        task.cancel()
    if lnbits_client is not None:
        await lnbits_client.aclose()


# Payment configuration is resolved at import time so a misconfigured deployment
# fails immediately and visibly, rather than starting up and silently serving
# every paid service for free.
try:
    payment_config = load_config()
except PaymentConfigError as exc:
    logger.critical("Refusing to start: %s", exc)
    raise SystemExit(1) from exc


app = FastAPI(
    title="BitAgent",
    description="Autonomous Lightning-enabled AI agents",
    version=__version__,
    lifespan=lifespan,
)

allowed_origins = _resolve_cors_origins()
# Credentials cannot be combined with a wildcard origin: browsers reject it, and
# a server that claims to allow both is misconfigured rather than permissive.
allow_credentials = "*" not in allowed_origins
if not allow_credentials:
    logger.warning("ALLOWED_ORIGINS is '*'; credentialed CORS requests are disabled")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allow_credentials,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-Admin-Key"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(RateLimitMiddleware, enabled=os.getenv("RATE_LIMIT", "true").lower() != "false")
app.add_middleware(
    BodySizeLimitMiddleware,
    max_bytes=MAX_BODY_BYTES,
    exempt_prefixes=("/polyglot/transcribe", "/coordinator/translate_audio"),
)
app.add_middleware(RequestContextMiddleware)

app.include_router(polyglot_router, prefix="/polyglot", tags=["PolyglotAgent"])
app.include_router(coordinator_router, prefix="/coordinator", tags=["CoordinatorAgent"])
app.include_router(oracle_router, prefix="/oracle", tags=["PriceOracleAgent"])
app.include_router(fetch_router, prefix="/fetch", tags=["WebFetchAgent"])
app.include_router(search_router, prefix="/search", tags=["SearchAgent"])
app.include_router(registry_router, prefix="/agents", tags=["AgentRegistry"])


# --- error handling ---------------------------------------------------------
# Internal exception text used to be returned to callers verbatim via str(e).


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": "invalid_request", "detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception("Unhandled error on %s (request_id=%s)", request.url.path, request_id)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "detail": "An internal error occurred.",
            "request_id": request_id,
        },
    )


# --- public endpoints -------------------------------------------------------


@app.get("/health")
async def health():
    """Liveness and readiness. Railway health-checks this path.

    Reports whether the pieces that matter actually work, rather than returning
    a static literal — a node with an unreachable wallet used to report healthy.
    """
    # Read through the gate rather than the module-level config so /health can
    # never disagree with what the running gate actually enforces.
    try:
        gate = get_gate()
        config, ledger = gate.config, gate.ledger
    except RuntimeError:
        return JSONResponse(
            status_code=503,
            content={"status": "starting", "version": __version__, "payments": "unknown"},
        )

    ledger_ok = ledger.healthy() if ledger else False

    payload = {
        "status": "healthy" if ledger_ok else "degraded",
        "version": __version__,
        "payments": config.describe(),
        "ledger": "ok" if ledger_ok else "unavailable",
    }
    if not config.enabled:
        payload["notice"] = "Payments are disabled on this node; all services are free."
    return JSONResponse(status_code=200 if ledger_ok else 503, content=payload)


@app.get("/")
async def root():
    return {
        "name": "BitAgent",
        "version": __version__,
        "payments": payment_config.describe(),
        "agents": [
            "polyglot",
            "coordinator",
            "oracle",
            "fetch",
            "search",
            "streamfinder",
            "identity",
        ],
        "services": "/services",
        "docs": "/docs",
    }


@app.get("/services")
async def services():
    """Every billable surface with its current price and availability."""
    return {"payments": get_gate().config.describe(), "services": catalog_info()}


def _is_not_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return True
    try:
        parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed >= datetime.now(UTC)


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


# --- A2A JSON-RPC -----------------------------------------------------------

JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_PAYMENT_REQUIRED = -32000
JSONRPC_SERVICE_UNAVAILABLE = -32001


def _rpc_error(code: int, message: str, request_id=None, data: dict | None = None) -> JSONResponse:
    error = {"code": code, "message": message}
    if data:
        error["data"] = data
    return JSONResponse(
        status_code=200, content={"jsonrpc": "2.0", "error": error, "id": request_id}
    )


@app.post("/a2a")
async def a2a_endpoint(request: Request):
    """Agent-to-agent JSON-RPC entry point.

    Returns real JSON-RPC ``error`` objects. This previously answered every
    request with HTTP 200 and an ``{"error": ...}`` value inside ``result``,
    which no JSON-RPC client can detect.
    """
    try:
        body = await request.json()
    except Exception:
        return _rpc_error(JSONRPC_PARSE_ERROR, "Parse error: body is not valid JSON")

    if not isinstance(body, dict):
        return _rpc_error(JSONRPC_INVALID_REQUEST, "Invalid request: expected a JSON object")

    request_id = body.get("id", 1)
    method = body.get("method")
    params = body.get("params") or {}

    if not isinstance(method, str) or not method:
        return _rpc_error(
            JSONRPC_INVALID_REQUEST, "Invalid request: 'method' is required", request_id
        )
    if not isinstance(params, dict):
        return _rpc_error(JSONRPC_INVALID_PARAMS, "Invalid params: expected an object", request_id)

    result = await handle_a2a_request(method, params)

    if isinstance(result, dict) and result.get("payment_required"):
        return _rpc_error(
            JSONRPC_PAYMENT_REQUIRED,
            str(result.get("detail") or "Payment required"),
            request_id,
            data=result,
        )
    if isinstance(result, dict) and result.get("service_unavailable"):
        return _rpc_error(
            JSONRPC_SERVICE_UNAVAILABLE,
            str(result.get("detail") or "Service unavailable"),
            request_id,
            data=result,
        )
    if isinstance(result, dict) and "error" in result and len(result) == 1:
        message = str(result["error"])
        code = (
            JSONRPC_METHOD_NOT_FOUND
            if message.startswith(("Unsupported method", "Unknown"))
            else JSONRPC_INVALID_PARAMS
        )
        return _rpc_error(code, message, request_id)

    return {"jsonrpc": "2.0", "result": result, "id": request_id}


@app.get("/agents/status")
async def agents_status():
    from src.payments import SERVICES

    def entry(prefix: str) -> dict:
        prices = {
            sid: svc.effective_price
            for sid, svc in SERVICES.items()
            if sid.startswith(f"{prefix}.")
        }
        synthetic = any(
            svc.synthetic for sid, svc in SERVICES.items() if sid.startswith(f"{prefix}.")
        )
        return {"status": "running", "pricing": prices, "synthetic": synthetic}

    return {
        name: entry(name)
        for name in (
            "polyglot",
            "coordinator",
            "oracle",
            "fetch",
            "search",
            "streamfinder",
            "identity",
        )
    }


# --- operational endpoints (admin key required) -----------------------------

if admin_enabled():

    @app.get("/wallet/balance", tags=["Operations"], dependencies=[Depends(require_admin)])
    async def wallet_balance():
        if lnbits_client is None:
            raise HTTPException(503, "Payments are disabled on this node")
        try:
            return {"balance_sats": await lnbits_client.get_balance_sats()}
        except LNbitsError as exc:
            raise HTTPException(503, "Wallet is unreachable") from exc

    @app.get("/wallet/ledger", tags=["Operations"], dependencies=[Depends(require_admin)])
    async def ledger_stats():
        if payment_ledger is None:
            raise HTTPException(503, "Ledger is not initialized")
        return payment_ledger.stats()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "false").lower() == "true",
    )
