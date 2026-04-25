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
# Root-level tests (broad integration / live-wallet / security):
pytest tests/test_agents_functionality.py   # PolyglotAgent + CoordinatorAgent
pytest tests/test_security_fixes.py         # auth, input sanitization, payment checks
pytest tests/test_live_deployment.py        # production validation (needs real env vars)

# Subdirectory tests:
pytest tests/agents/         # CameraFeedBot, DataBot unit tests
pytest tests/integration/    # full agent workflow (registration, DID, discovery)
pytest tests/security/       # encryption, auth, audit logging

# Single test:
pytest tests/test_agent_wallet.py::TestAgentWallet::test_create_invoice -v
```

No conftest.py / pytest fixtures — tests use `setup_method()` and inline `unittest.mock`.

## Development Priorities

Remaining gaps (already-fixed items removed):

1. **Unify agent pattern** — all agents use inline payment logic (check `payment_hash` → create invoice → verify via `AgentWallet`). The `@require_payment` decorator in `src/core/payment.py` uses an incompatible escrow/`PaymentSecurityManager` system and is **not wired to the real LNbits wallet** — do not use it until it's rewritten to call `AgentWallet` directly.
2. **CORS config** — `ALLOWED_ORIGINS` is set in Railway env vars; verify it includes any new frontends.
3. **Whisper/transcription** — `openai-whisper` and `ffmpeg-python` are excluded from `requirements.txt` (pulls PyTorch ~2GB, breaks cloud builds). Install locally to use transcription: `pip install openai-whisper ffmpeg-python`.
4. **Phase 3** — WebSocket + MQTT support (needed for SDEN real-time streaming data).
5. **Phase 4** — Fedimint ecash support is live (see payment layer above). Taproot Assets/USDT on Lightning still future work.
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
| `streamfinder/` | 100 sats | A2A JSON-RPC reference implementation; **dummy DB only** — no real streaming API yet |

**Not wired into `main.py`** — the following files exist in `src/agents/` but are not live endpoints:
- `camera_feed_bot.py`, `databot.py`, `service_agent.py` — concrete `BaseAgent` subclasses used in `examples/` and `tests/agents/` only
- `consumer_agent.py` — stub mock (no `BaseAgent` inheritance, print-only logic)
- `cambot.py`, `logibot.py`, `init.py` — empty files, future placeholders

### Adding a new agent

All live agents use this pattern in their `__init__.py` for wallet access:

```python
from src.wallets.fedimint_wallet import FedimintWallet

_fedimint = FedimintWallet()   # eager — safe, no required args
_wallet = None                  # lazy — AgentWallet throws if LNBITS_* not set

def _get_wallet():
    global _wallet
    if _wallet is None:
        try:
            from agent_wallet import AgentWallet
            _wallet = AgentWallet()
        except Exception:
            pass
    return _wallet
```

`AgentWallet` is lazy because it raises `ValueError` on missing `LNBITS_API_KEY` / `LNBITS_URL`, which would crash dev-mode startup. Returning `None` from `_get_wallet()` disables Lightning payments gracefully. `FedimintWallet` is always instantiated but its `enabled` property gates actual ecash use.

See `src/agents/search_agent/__init__.py` as the canonical reference — `web_fetch_agent` and `price_oracle_agent` follow the same pattern exactly.

### MCP Server (`mcp_server.py`)

Exposes `translate`, `search`, `fetch_url`, `get_price`, `convert_sats` as Claude tools via stdio MCP. Imports agent modules directly — no HTTP, no payment gate. Each result includes `cost_sats`. Configured via `.mcp.json`.

To use in Claude Code: run `/mcp` to reload, or restart the session after cloning.

### Root-level modules

`agent_logic.py` — top-level A2A router; dispatches `oracle.*`, `fetch.*`, `search.*`, and `streamfinder.*` methods to their agent classes. Called by `main.py`'s `/a2a` endpoint.

`agent_wallet.py` — `AgentWallet` singleton used by all agents; validation deferred to `__init__()`.

`lnbits_client.py` — raw REST client that `AgentWallet` wraps.

**Wallet tiers:** `_SimWallet` (in `src/agents/base_agent.py`) is the default for `BaseAgent` subclasses — in-memory, no real payments, used for examples and tests. `AgentWallet` (root `agent_wallet.py`) handles Lightning via LNbits and is lazy-loaded by live agents. `FedimintWallet` (`src/wallets/fedimint_wallet.py`) handles ecash and is eagerly instantiated (safe, no required args) — its `enabled` property returns `False` if not configured.

### Core framework (`src/core/`)
- `agent.py` — `Agent` base class wiring together security, monitoring, and payments
- `agent_server.py` — `AgentServer` wraps FastAPI; auto-generates `/info`, `/services`, `/stats`, `/security` endpoints
- `payment.py` — `@require_payment` / `@require_authentication` decorators (target pattern for all agents)

### Payment layer
- `src/wallets/fedimint_wallet.py` — real `fedimint-clientd` HTTP client. Set `FEDIMINT_CLIENTD_URL` + `FEDIMINT_CLIENTD_PASSWORD` to enable. When enabled, all agent 402 responses include `ecash_accepted: true` + `ecash_amount_msats`, and endpoints accept `ecash_notes` alongside `payment_hash`. Flow: `validate` (non-destructive, checks amount) → `reissue` (redeems notes into federation wallet).
- LNbits handles all Lightning bolt11 payments (unchanged). Fedimint is an additive second path — both can be used independently.

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
