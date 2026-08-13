# BitAgent

**Payment rails for AI agents — Bitcoin Lightning, built in.**

[![CI](https://github.com/intrinsicinvestment91/bitagent/actions/workflows/ci.yml/badge.svg)](https://github.com/intrinsicinvestment91/bitagent/actions)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

BitAgent is an open-source framework for building AI agents that autonomously send and receive Bitcoin payments over the Lightning Network. Agents discover each other via Nostr, verify identity with DIDs, and coordinate multi-step workflows — all settled in real sats.

---

## Why BitAgent?

Most AI agent frameworks treat money as an afterthought. BitAgent treats it as a first-class primitive.

```
Agent A                          Agent B (SearchAgent)
  │                                    │
  │── POST /search/query ─────────────>│
  │<── 402 { payment_request: "lnbc…" }│  (no pay, no work)
  │                                    │
  │── pay Lightning invoice ──────────>│ LNbits
  │── POST /search/query + hash ──────>│
  │<── 200 { results: [...] } ─────────│  (that hash is now spent)
```

- **Agents charge sats for services** — search, web fetch, price data, translation
- **Agents pay other agents** — chain services together, costs flow automatically
- **No API keys or accounts** — Lightning invoices are the auth layer
- **Discoverable via Nostr** — agents announce themselves; anyone can find and call them

### What "paid" actually means here

An invoice is worth exactly one request, for exactly the service it was quoted for.

- Every invoice the node issues is recorded in a **durable ledger** before the 402 is returned.
- Redeeming a payment **consumes** it inside a single atomic transaction, so two concurrent
  requests carrying the same hash cannot both be served.
- A hash issued for a 2-sat price lookup **cannot** be redeemed against a 100-sat translation.
- If the wallet is unreachable, paid routes return **503** — never a free result. There is no
  configuration in which a paid service is silently given away.
- If the work fails *after* settlement, the payment is **released** so you can retry with it
  instead of losing your sats.

Losing the ledger would make past payments replayable, so mount it on a volume
(`BITAGENT_DATA_DIR`, `/data` in the Docker image).

---

## Quick Start

**Requirements:** Python 3.11+, and an [LNbits](https://lnbits.com) wallet if you want to charge for anything.

```bash
git clone https://github.com/intrinsicinvestment91/bitagent.git
cd bitagent
pip install -r requirements.txt
cp .env.example .env
# edit .env: set LNBITS_URL and LNBITS_API_KEY
python main.py
```

The server starts on `http://localhost:8000`. Open `/docs` for the interactive API, or `/services`
for the machine-readable price list.

**To run without a wallet** (every service free and labelled as such):

```bash
PAYMENTS_ENABLED=false python main.py
```

A node started with neither LNbits credentials nor `PAYMENTS_ENABLED=false` **refuses to start**.
That is deliberate: the alternative is a deployment that looks healthy while serving everything
for free.

**Buy a search (10 sats):**

```bash
# Step 1 — request the service, get an invoice
curl -X POST http://localhost:8000/search/query \
  -H "Content-Type: application/json" \
  -d '{"query": "lightning network"}'
# → 402 {"payment_request": "lnbc…", "payment_hash": "abc123…", "amount_sats": 10,
#         "expires_at": "…"}

# Step 2 — pay the invoice with any Lightning wallet, then resubmit with the hash
curl -X POST http://localhost:8000/search/query \
  -H "Content-Type: application/json" \
  -d '{"query": "lightning network", "payment_hash": "abc123…"}'
# → 200 {"results": [...]}

# Step 3 — try to reuse it
# → 402 {"error": "already_consumed"}
```

`examples/paid_request_flow.py` walks this end to end against a running node.

---

## What's Included

| Agent | Endpoint | Service | Price |
|---|---|---|---|
| **SearchAgent** | `POST /search/query` | Web search (Brave → SearXNG → DDG) | 10 sats |
| **WebFetchAgent** | `POST /fetch/url` | Fetch & clean any public web page | 25 sats |
| **PriceOracleAgent** | `GET /oracle/price/{coin}` | Live crypto price | 2 sats |
| **PriceOracleAgent** | `POST /oracle/prices` | Batch price lookup | 5 sats |
| **PriceOracleAgent** | `POST /oracle/convert` | Sats → USD | 1 sat |
| **PolyglotAgent** | `POST /polyglot/translate` | Text translation (100+ languages) | 100 sats |
| **PolyglotAgent** | `POST /polyglot/transcribe` | Audio → text (Whisper) | 250 sats¹ |
| **CoordinatorAgent** | `POST /coordinator/chain_tasks` | Run several services in one request | 100 sats |
| **CoordinatorAgent** | `POST /coordinator/translate_audio` | Transcribe → translate | 350 sats¹ |
| **IdentityAgent** | `/a2a` (JSON-RPC) | Paid NIP-05 registration | 1000 sats |
| **IdentityAgent** | `/a2a` (JSON-RPC) | Identity and trust lookups | 10–25 sats |
| **StreamfinderAgent** | `/a2a` (JSON-RPC) | A2A reference implementation | **free — demo data²** |

¹ Whisper is excluded from the cloud image (it pulls ~2GB of PyTorch). Without it these report
themselves unavailable and are **not charged for**. Install it to enable them:
`pip install openai-whisper ffmpeg-python`.

² Streamfinder answers from a fixed three-title dataset. It is not a streaming availability API,
it is free, and every response says so. The service catalog enforces this: a service marked
`synthetic` cannot have a non-zero price.

Every priced HTTP route has an identically-priced A2A twin — see below.

`GET /services` returns this table as JSON, including live availability, so clients never have to
hardcode prices.

---

## A2A protocol

Agents call each other over JSON-RPC 2.0 at `POST /a2a`:

```bash
curl -X POST http://localhost:8000/a2a \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "search.query",
       "params": {"query": "lightning", "payment_hash": "abc123…"}}'
```

Methods: `search.query`, `fetch.url`, `oracle.price`, `oracle.prices`, `oracle.convert`,
`polyglot.translate`, `polyglot.transcribe`, `identity.*`, `streamfinder.search`.

Payment-required responses come back as a JSON-RPC error with code `-32000` and the invoice in
`error.data`; an unavailable backend is `-32001`. Each agent also serves the same methods on its
own sub-router (`/search/a2a`, `/oracle/a2a`, …), at the same price.

---

## Use with Claude (MCP)

BitAgent ships an [MCP](https://modelcontextprotocol.io) server so Claude can call your agents as
tools directly — no HTTP, no payment gate in the loop, since you are the node's operator.

```bash
claude mcp add bitagent -- python /path/to/bitagent/mcp_server.py
```

Or use the `.mcp.json` in the repository root. Claude then has `search`, `fetch_url`, `translate`,
`get_price` and `convert_sats` as native tools; each result carries `cost_sats` so you can track
what the same call would cost over the paid API.

---

## Architecture

```
src/
├── payments/                 # The payment core — everything priced goes through here
│   ├── catalog.py            #   one source of truth for prices; synthetic services must be free
│   ├── lnbits.py             #   async LNbits client; paid/unpaid/unknown so callers fail closed
│   ├── ledger.py             #   durable SQLite record making each invoice single-use
│   ├── gate.py               #   require_payment() — the single gate every route calls
│   └── config.py             #   fail-closed startup
├── agents/
│   ├── search_agent/         # Web search (Brave → SearXNG → DuckDuckGo)
│   ├── web_fetch_agent/      # Web page fetcher with SSRF protection
│   ├── price_oracle_agent/   # Live crypto prices (CoinGecko → Binance)
│   ├── polyglot_agent/       # Translation & transcription
│   ├── coordinator_agent/    # Runs multi-step chains in one paid request
│   ├── identity_agent/       # NIP-05 registration + trust scoring (SQLite)
│   └── streamfinder/         # A2A reference implementation (synthetic demo)
├── api/middleware.py         # Request IDs, body size limits, rate limiting
├── security/                 # Request models, input sanitization, admin auth
├── identity/                 # DID documents (did:key, did:nostr, did:bitcoin)
├── network/                  # Nostr discovery, peer registry
└── wallets/                  # Fedimint ecash (a second, optional payment path)

main.py                       # Cloud/Railway entry point
mcp_server.py                 # MCP stdio server
start9_server.py              # Start9 self-hosted entry point (legacy, see below)
```

### Adding a paid service

1. Add an entry to `SERVICES` in `src/payments/catalog.py` with a stable `<agent>.<method>` id.
2. In your route, call the gate and return whatever it hands back:

```python
outcome = await require_payment("myagent.mymethod", body.payment_hash, body.ecash_notes)
if isinstance(outcome, Quote):
    return JSONResponse(status_code=outcome.status_code, content=outcome.body)
async with paid_work(outcome):
    return await do_the_work(...)
```

`paid_work` returns the caller's payment if the work raises, so a failure on your side does not
cost them sats. `src/agents/search_agent/__init__.py` is the reference.

A test sweeps every catalog entry and fails if a priced service is unreachable from the A2A
dispatcher, so a new service cannot quietly ship without a price.

---

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `LNBITS_URL`, `LNBITS_API_KEY` | — | LNbits wallet. Required unless `PAYMENTS_ENABLED=false` |
| `PAYMENTS_ENABLED` | `true` | Set `false` to run a free node (loudly labelled) |
| `BITAGENT_DATA_DIR` | `./data` | Payment ledger + identity DB. **Mount this** |
| `ADMIN_API_KEY` | — | Enables `/wallet/balance` and `/wallet/ledger` behind `X-Admin-Key`. Unset means those routes do not exist |
| `INVOICE_TTL_SECONDS` | `3600` | How long an unpaid quote stays redeemable |
| `ALLOWED_ORIGINS` | localhost | Comma-separated CORS origins |
| `RATE_LIMIT` | `true` | Per-IP rate limiting |
| `MAX_BODY_BYTES` | `1048576` | Request body cap |
| `BRAVE_API_KEY`, `SEARXNG_URL` | — | Preferred search backends; falls back to DuckDuckGo |
| `NOSTR_PRIVATE_KEY` | — | 64-hex key for a stable Nostr identity across restarts |
| `FEDIMINT_CLIENTD_URL`, `FEDIMINT_CLIENTD_PASSWORD` | — | Enables ecash as a second payment path |
| `IDENTITY_REQUIRE_FOR_PAID_SERVICES` | `false` | Require a trusted NIP-05 identity on streamfinder |

See `.env.example` for the annotated version.

---

## Deployment

**Cloud (Railway):** connect this repo, set `LNBITS_URL` and `LNBITS_API_KEY`, and **mount a volume
at `/data`** — the payment ledger lives there, and losing it makes past payments replayable.

**Docker:**

```bash
docker build -t bitagent .
docker run -p 8000:8000 -v bitagent-data:/data \
  -e LNBITS_URL=… -e LNBITS_API_KEY=… bitagent
```

**Local development:**

```bash
docker compose -f docker-compose.dev.yml up
```

**Self-hosted (Start9):** see [`docs/START9_DEPLOYMENT_GUIDE.md`](docs/START9_DEPLOYMENT_GUIDE.md).
`start9_server.py` is preserved as-is and still uses the legacy wallet, which does **not** enforce
single-use payments. Do not expose it publicly as a paid node until it is migrated onto the payment
gate.

---

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
ruff check . && ruff format --check .
PAYMENTS_ENABLED=false pytest
```

---

## Contributing

BitAgent is early. There's a lot of room to build — the biggest open items are a real streaming
data source for Streamfinder, migrating Start9 onto the payment gate, and Taproot Assets support.

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT — use it, fork it, build on it.
