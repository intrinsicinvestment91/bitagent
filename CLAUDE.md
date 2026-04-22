# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

BitAgent is a modular, Lightning-enabled AI agent framework. Agents autonomously offer services (translation, transcription, streaming search), accept Bitcoin Lightning (LNbits) and Fedimint ecash payments, discover each other via the Nostr protocol, and verify identity using Decentralized Identifiers (DIDs). Agents can chain together into multi-step workflows through a CoordinatorAgent.

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

These are the known gaps to address when "finishing" the project (in order):

1. **Verify import paths** — `bitagent.core.*` imports in agents should resolve to `src.core.*`; check each agent's `__init__.py` before running
2. **CORS config** — `main.py` reads from `ALLOWED_ORIGINS` env var; set it for production Railway deploy
3. **Unify agent pattern** — `polyglot_agent` and `coordinator_agent` should use `@require_payment` from `src/core/payment.py`; `streamfinder` is the A2A reference
4. **LNbits live test** — run `python check_invoice.py` to verify wallet connectivity before testing payment flows
5. **Remove `START9_NODE_ID` requirement** — `main.py` does not require it; `start9_server.py` still does (intentional)

## Architecture

### Request Lifecycle

```
Client → FastAPI endpoint → Auth check (JWT/API key) → Payment check (Lightning invoice)
       → Service execution → Audit log → Response
```

If no payment is included, the endpoint returns a Lightning invoice. The client pays, then re-submits with the `payment_hash`. The `@require_payment(min_sats)` and `@require_authentication(permissions)` decorators in `src/core/payment.py` enforce this pattern.

### Key Layers

**Agents (`src/agents/`)** — three concrete agents:
- `polyglot_agent/` — translation (100 sats) and transcription via Whisper (250 sats)
- `coordinator_agent/` — chains polyglot calls; orchestrates `translate_audio` (350 sats) and generic `chain_tasks`
- `streamfinder/streamfinder.py` — streaming search via A2A JSON-RPC protocol (100 sats)

**Core framework (`src/core/`):**
- `agent.py` — `Agent` base class wiring together security, monitoring, and payments
- `agent_server.py` — `AgentServer` wraps FastAPI; auto-generates `/info`, `/services`, `/stats`, `/security` endpoints
- `payment.py` — `@require_payment` / `@require_authentication` decorators

**Payment layer:**
- `lnbits_client.py` — REST client for LNbits API (invoice creation, payment status)
- `agent_wallet.py` — `AgentWallet` wraps `LNbitsClient`; loads config from `.env`
- `src/wallets/fedimint_wallet.py` — simulated Fedimint ecash wallet (mint/accept/redeem tokens)

**Security (`src/security/`):**
- `authentication.py` — JWT tokens, API key hierarchy (read → write → admin)
- `encryption.py` — AES-256-GCM, ChaCha20-Poly1305, X25519 key exchange
- `payment_security.py` — escrow payments, fraud scoring, dispute resolution
- `secure_endpoints.py` — input sanitization, file upload validation, Pydantic models

**Identity (`src/identity/`):**
- `enhanced_did.py` — DID document creation supporting `did:key`, `did:web`, `did:bitcoin`, `did:nostr`; verifiable credentials and trust scoring

**Discovery (`src/network/`):**
- `nostr.py` — publishes agent announcements as Nostr Kind 30078 events with service tags and pricing
- `p2p_discovery.py` — DHT-based peer discovery across Nostr, DNS, and multicast

**Monitoring (`src/monitoring/`):**
- `audit_logger.py` — structured audit log for all system events, agent actions, payments, and auth
- `performance_monitor.py` — per-service latency and success/failure metrics

### Entry Points

| File | Purpose |
|---|---|
| `main.py` | Railway / cloud deployment — env-driven CORS, no Start9 deps |
| `start9_server.py` | Start9 deployment — preserved, do not modify for other platforms |
| `src/agents/polyglot_agent/run.py` | Standalone polyglot dev server |
| `src/agents/coordinator_agent/run.py` | Standalone coordinator dev server |

`docker-compose.yaml` is the **Start9 service manifest** (not a real compose file). `docker-compose.dev.yml` is the local dev compose.

## A2A Protocol

`streamfinder` implements the Agent-to-Agent JSON-RPC pattern. Requests hit `POST /a2a` with `{"method": "streamfinder.search", "params": {...}}`. This is the reference implementation for adding new A2A-compatible agents.
