# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

BitAgent is a modular, Lightning-enabled AI agent framework. Agents autonomously offer services (web search, web fetching, crypto prices, translation, transcription, NIP-05 identity), accept Bitcoin Lightning (LNbits) payments, discover each other via the Nostr protocol, and verify identity using Decentralized Identifiers (DIDs). Agents can chain into multi-step workflows through a CoordinatorAgent.

**The single most important invariant:** an invoice buys exactly one request, of exactly the service it was quoted for, and no failure mode anywhere degrades into free service. If you touch anything under `src/payments/`, that is the property you are protecting.

## The payment core (`src/payments/`)

Everything priced goes through this package. Do not add payment logic anywhere else.

| Module | Responsibility |
|---|---|
| `catalog.py` | `SERVICES` — one source of truth for prices, keyed by `<agent>.<method>`. A `synthetic` service (placeholder output) **cannot** have a non-zero price; the constructor rejects it. |
| `lnbits.py` | `AsyncLNbitsClient`. Explicit timeouts, bounded retries, and a three-state lookup: `PAID` / `UNPAID` / `UNKNOWN`. `UNKNOWN` is what lets callers fail closed. |
| `ledger.py` | Durable SQLite (WAL) record of every invoice issued. `consume()` flips `issued`→`consumed` in a `BEGIN IMMEDIATE` transaction, so concurrent redemptions serialise and exactly one wins. `release()` hands a payment back if the work fails after settlement. |
| `gate.py` | `require_payment()` — the one gate every route calls — plus the `paid_work()` context manager. |
| `config.py` | Tri-state startup: enforced / explicitly free / **refuse to start**. |

### Rules

1. **Never fail open.** Wallet unreachable → 503. Invoice minting failed → 503. Never 402-with-a-result, never a free result. Three separate code paths used to do exactly that.
2. **Prices come from the catalog.** Agent classes expose `price_sats` as a property reading `price_of(...)`. Do not reintroduce hardcoded prices — they previously lived in seven places in three shapes and disagreed.
3. **Every priced HTTP route needs an identically-priced A2A twin.** Each agent's `/a2a` sub-router and the top-level dispatcher in `agent_logic.py` resolve the *same* catalog id. `tests/payments/test_no_free_bypass.py` sweeps all of them and fails if one is free.
4. **Never charge for fabricated output.** If a backend is missing, mark the service unavailable (it is then not billed) or `synthetic` with price 0. Do not return mock data from a priced path.
5. **The ledger must be durable.** It lives under `BITAGENT_DATA_DIR`. Losing it makes every past payment replayable.

### Adding a paid service

```python
# 1. src/payments/catalog.py
_service("myagent.mymethod", "What it does", 42),

# 2. in the route
outcome = await require_payment("myagent.mymethod", body.payment_hash, body.ecash_notes)
if isinstance(outcome, Quote):
    return JSONResponse(status_code=outcome.status_code, content=outcome.body)
async with paid_work(outcome):
    return await do_the_work(...)

# 3. add it to METHOD_SERVICES + dispatch_service in agent_logic.py
```

`src/agents/search_agent/__init__.py` is the canonical reference.

## Deployment Targets

**Primary (Railway — cloud PaaS):**
- Entry point: `main.py` — platform-agnostic, all config from env vars
- Config: `railway.toml` (Dockerfile builder, healthcheck at `/health`)
- Required: `LNBITS_URL`, `LNBITS_API_KEY` — **or** `PAYMENTS_ENABLED=false`
- **Mount a volume at `/data`.** `BITAGENT_DATA_DIR` defaults there in the image and holds the payment ledger and identity DB.
- Optional: `ADMIN_API_KEY`, `ALLOWED_ORIGINS`, `PORT`, `LOG_LEVEL`, `NOSTR_PRIVATE_KEY`, `PUBLIC_URL`, `RATE_LIMIT`, `MAX_BODY_BYTES`, `INVOICE_TTL_SECONDS`

**Legacy (Start9 — self-hosted):**
- Entry point: `start9_server.py`, manifest `docker-compose.yaml` (a Start9 manifest, *not* a compose file), build with `make`
- It still uses `agent_wallet.py` / `lnbits_client.py`, which **do not enforce single-use payments**. Do not run it publicly as a paid node until it is migrated onto the payment gate.

**Local dev:**
```bash
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env          # then fill in LNBITS_URL and LNBITS_API_KEY
python main.py                # port 8000
PAYMENTS_ENABLED=false python main.py   # no wallet needed; everything free and labelled

docker compose -f docker-compose.dev.yml up
```

**Tests and lint:**
```bash
ruff check . && ruff format --check .
PAYMENTS_ENABLED=false pytest
pytest tests/payments/ -v     # the payment core
```

`tests/conftest.py` provides `paid_gate`, `free_gate`, `fake_lnbits`, `ledger` and `pay_for`. `FakeLNbits` implements the real client's contract, so tests exercise the real gate, ledger and SQL with no network. Tests set `PAYMENTS_ENABLED=false` and `RATE_LIMIT=false` at import.

Note: `TestClient(main.app)` runs the app's lifespan, which installs its own gate from the environment. Fixtures that need the paid gate re-`configure_gate()` *after* entering the client context.

## Architecture

### Request lifecycle

```
Client → route → require_payment(service_id, payment_hash)
                   ├─ no hash        → mint invoice, record in ledger, 402
                   ├─ hash unpaid    → 402
                   ├─ wallet down    → 503        (never free, never a bare 402)
                   └─ hash paid      → ledger.consume() → Settled
                                        └─ work fails → release() so it can be retried
```

### Live agents (`src/agents/`)

| Agent | Price | Notes |
|---|---|---|
| `search_agent/` | 10 sats | Brave → SearXNG → DuckDuckGo fallback |
| `web_fetch_agent/` | 25 sats | SSRF protection blocks private IP ranges |
| `price_oracle_agent/` | 1–5 sats | CoinGecko primary, Binance fallback, 60s cache |
| `polyglot_agent/` | 100 / 250 sats | Transcribe reports itself unavailable (and is not billed) when whisper is absent |
| `coordinator_agent/` | 100 / 350 sats | Runs chain steps in-process via `dispatch_service` |
| `identity_agent/` | 10–1000 sats | NIP-05 + trust scoring, SQLite. A2A only, no router prefix |
| `streamfinder/` | **free, synthetic** | A2A reference implementation over a fixed 3-title dataset |

`base_agent.py`, `camera_feed_bot.py` and `databot.py` are `BaseAgent` demos used by `examples/` and `tests/agents/` — not live endpoints. `BaseAgent`'s default wallet is `_SimWallet`, an in-memory fake.

### Root modules

- `main.py` — Railway/cloud entry point. Middleware (request IDs, body size cap, rate limiting), global exception handlers, real `/health`, JSON-RPC-compliant `/a2a`, admin routes registered only when `ADMIN_API_KEY` is set.
- `agent_logic.py` — top-level A2A dispatcher. `METHOD_SERVICES` maps method → catalog id; a method absent from it is rejected, so a route cannot exist unpriced. `dispatch_service()` runs settled work and is reused by the coordinator.
- `agent_wallet.py`, `lnbits_client.py` — **legacy, Start9 only.** Synchronous, no timeouts, no replay protection. Do not use in new code.

### Other packages

- `src/api/middleware.py` — request context, body size limit, per-IP rate limiting (in-process; the effective limit multiplies by worker count)
- `src/security/` — request models and input sanitization (`secure_endpoints.py`), JWT/API keys (`authentication.py`, whose `RateLimiter` backs the middleware), admin auth (`admin_auth.py`)
- `src/identity/enhanced_did.py` — DID documents for `did:key`, `did:web`, `did:bitcoin`, `did:nostr`
- `src/network/p2p_discovery.py` — Nostr Kind 30078 announcements and DHT peer discovery; `registry_router.py` serves `/agents/registry`
- `src/monitoring/audit_logger.py` — structured audit events
- `src/wallets/fedimint_wallet.py` — Fedimint ecash, an additive second payment path. Enabled by `FEDIMINT_CLIENTD_URL` + `FEDIMINT_CLIENTD_PASSWORD`. `validate` (non-destructive) → `reissue` (burns the notes).

### MCP server (`mcp_server.py`)

Exposes `translate`, `search`, `fetch_url`, `get_price`, `convert_sats` as Claude tools over stdio. Imports agent modules directly — no HTTP, no payment gate, since the caller is the node's operator. Costs come from the catalog. Written against the **mcp 2.x** decorator API (`MCPServer`, `@server.tool()`).

## Known gaps / next steps

1. **Streamfinder has no real data source.** Wire it to a real availability API (JustWatch, TMDB watch-providers), then give it a price in the catalog. The catalog will refuse a price while `synthetic=True`, so flip both together.
2. **Start9 shares none of the payment fixes** and still has the replay hole. Migrating `start9_server.py` onto the gate is the single highest-value follow-up.
3. **Rate limiting is per-process.** A shared store is needed for multi-worker accuracy.
4. **NIP-05 registration does not prove key ownership.** Anyone who pays can register any pubkey; a Nostr signature challenge would fix it.
5. **Trust scoring is a fixed-weight heuristic**, effectively a synonym for "paid once". No graph, history, or decay.
6. Phase 3: WebSocket + MQTT (for SDEN real-time streaming). Phase 5: agent registry + reputation. Taproot Assets/USDT on Lightning remain future work.

## Relationship to SDEN

SDEN is a companion protocol for IoT devices that sell signed sensor data via Lightning. A SDEN producer node *is* a BitAgent agent — it uses BitAgent's wallet, Nostr discovery, and DID identity. When working on SDEN, treat them as one system: the `SensorAgent` class should extend BitAgent's base agent and go through `src/payments/` for billing.
