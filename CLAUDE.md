# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

BitAgent is a modular, Lightning-enabled AI agent framework. Agents autonomously offer services (translation, web search, crypto prices, web fetching, streaming search), accept Bitcoin Lightning (LNbits) payments, discover each other via the Nostr protocol, and verify identity using Decentralized Identifiers (DIDs). Agents can chain together into multi-step workflows through a CoordinatorAgent.

**Live deployment:** `https://bitagent-production.up.railway.app` — connected to a live LNbits wallet (~68k sats). End-to-end Lightning payments have been verified in production (10-sat search, 100-sat translation).

## Deployment Targets

**Primary (Railway — cloud PaaS):**
- Entry point: `main.py` — platform-agnostic, all config from env vars
- Config: `railway.toml` — points to Dockerfile, healthcheck at `/health`
- Deploy: connect Railway to this repo; set env vars in Railway dashboard
- Required env vars: `LNBITS_URL`, `LNBITS_API_KEY`
- Optional: `ALLOWED_ORIGINS` (comma-separated), `PORT`, `LOG_LEVEL`

**Preserved (Start9 — self-hosted):**
- Entry point: `start9_server.py` — do not refactor, kept for future use
- Manifest: `docker-compose.yaml` — this is the Start9 manifest, NOT a standard compose file
- Scripts: `deploy_to_start9.sh`, `deploy_live.sh`

**Local dev:**
```bash
pip install -r requirements.txt
cp env.template .env    # then fill in LNBITS_URL and LNBITS_API_KEY
python main.py          # runs on port 8000

# Or with Docker:
docker-compose -f docker-compose.dev.yml up
```

**Run individual agents:**
```bash
python src/agents/polyglot_agent/run.py      # port 8000
python src/agents/coordinator_agent/run.py   # port 8001
```

**Tests:**
```bash
pytest test_agents_functionality.py
pytest test_security_fixes.py
pytest tests/
```

## Development Priorities

Remaining gaps (already-fixed items removed):

1. **Unify agent pattern** — `polyglot_agent` and `coordinator_agent` use inline payment logic; they should eventually use `@require_payment` from `src/core/payment.py`. The three new agents (oracle, fetch, search) also use inline logic — `streamfinder` is the A2A reference.
2. **CORS config** — `ALLOWED_ORIGINS` is set in Railway env vars; verify it includes any new frontends.
3. **Whisper/transcription** — `openai-whisper` and `ffmpeg-python` are excluded from `requirements.txt` (pulls PyTorch ~2GB, breaks cloud builds). Install locally to use transcription: `pip install openai-whisper ffmpeg-python`.
4. **Phase 3** — WebSocket + MQTT support (needed for SDEN real-time streaming data).
5. **Phase 4** — Stablecoin support (Taproot Assets, Fedimint USD ecash).
6. **Phase 5** — Agent registry + reputation system.

**Fixed in prior session (do not re-fix):**
- `secrets`/`hashlib` removed from requirements.txt (they're stdlib)
- `agent_wallet.py` — validation deferred to `__init__()`, not module level
- `agent_logic.py` — broken relative import and wrong function signature fixed
- `polyglot_agent/__init__.py` — broken `@require_payment` / `@require_authentication` decorator chain replaced with inline payment logic
- DDG scraper replaced with `ddgs` package (DDG blocks server-side scraping)

## Architecture

### Request Lifecycle

```
Client → FastAPI endpoint → Payment check (Lightning invoice if missing)
       → Service execution → Response (includes cost_sats)
```

If no `payment_hash` is included, the endpoint returns a 402 with a Lightning invoice. The client pays, then resubmits with `payment_hash`. New agents (oracle, fetch, search) pass through without payment if no wallet is configured (dev mode).

### Agents (`src/agents/`)

| Agent | Price | Notes |
|---|---|---|
| `polyglot_agent/` | 100 sats (translate), 250 sats (transcribe) | Whisper excluded from prod build |
| `coordinator_agent/` | 350 sats | Chains polyglot calls |
| `price_oracle_agent/` | 2 sats | CoinGecko primary, Binance fallback, 60s cache |
| `web_fetch_agent/` | 25 sats | SSRF protection blocks private IP ranges |
| `search_agent/` | 10 sats | Brave → SearXNG → DuckDuckGo (`ddgs`) fallback |
| `streamfinder/` | 100 sats | A2A JSON-RPC reference implementation |

### MCP Server (`mcp_server.py`)

Exposes `translate`, `search`, `fetch_url`, `get_price`, `convert_sats` as Claude tools via stdio MCP. Imports agent modules directly — no HTTP, no payment gate. Each result includes `cost_sats`. Configured via `.mcp.json`.

To use in Claude Code: run `/mcp` to reload, or restart the session after cloning.

### Core framework (`src/core/`)
- `agent.py` — `Agent` base class wiring together security, monitoring, and payments
- `agent_server.py` — `AgentServer` wraps FastAPI; auto-generates `/info`, `/services`, `/stats`, `/security` endpoints
- `payment.py` — `@require_payment` / `@require_authentication` decorators (target pattern for all agents)

### Payment layer
- `lnbits_client.py` — REST client for LNbits API (invoice creation, payment status)
- `agent_wallet.py` — `AgentWallet` wraps `LNbitsClient`; loads config from `.env`; validation deferred to `__init__()` so import doesn't crash
- `src/wallets/fedimint_wallet.py` — simulated Fedimint ecash wallet (mint/accept/redeem tokens)

### Security (`src/security/`)
- `authentication.py` — JWT tokens, API key hierarchy (read → write → admin)
- `encryption.py` — AES-256-GCM, ChaCha20-Poly1305, X25519 key exchange
- `secure_endpoints.py` — input sanitization, file upload validation, Pydantic models

### Identity and Discovery
- `src/identity/enhanced_did.py` — DID document creation supporting `did:key`, `did:web`, `did:bitcoin`, `did:nostr`
- `src/network/nostr.py` — publishes agent announcements as Nostr Kind 30078 events
- `src/network/p2p_discovery.py` — DHT-based peer discovery across Nostr, DNS, and multicast

### Entry Points

| File | Purpose |
|---|---|
| `main.py` | Railway / cloud deployment — env-driven CORS, no Start9 deps |
| `mcp_server.py` | MCP stdio server — Claude uses this to call agents as tools |
| `start9_server.py` | Start9 deployment — preserved, do not modify for other platforms |
| `src/agents/polyglot_agent/run.py` | Standalone polyglot dev server |
| `src/agents/coordinator_agent/run.py` | Standalone coordinator dev server |

`docker-compose.yaml` is the **Start9 service manifest** (not a real compose file). `docker-compose.dev.yml` is the local dev compose.

## A2A Protocol

`streamfinder` implements the Agent-to-Agent JSON-RPC pattern. Requests hit `POST /a2a` with `{"method": "streamfinder.search", "params": {...}}`. This is the reference implementation for adding new A2A-compatible agents.

`agent_logic.py` routes A2A calls for oracle (`oracle.price`, `oracle.prices`, `oracle.convert`), fetch (`fetch.url`), and search (`search.query`) in addition to streamfinder.

## Relationship to SDEN

SDEN (`/home/charlie/sensor-data-exchange-node`) is a companion protocol for IoT devices that sell signed sensor data via Lightning. A SDEN producer node IS a BitAgent agent — it uses BitAgent's wallet, Nostr discovery, and DID identity. When working on SDEN, understand they are one system. The SDEN `SensorAgent` class should extend BitAgent's `Agent` base class.
