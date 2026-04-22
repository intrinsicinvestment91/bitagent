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
Agent A                          Agent B (PolyglotAgent)
  │                                    │
  │── POST /polyglot/translate ───────>│
  │<── { payment_request: "lnbc..." } ─│  (no pay, no work)
  │                                    │
  │── pay Lightning invoice ──────────>│ LNbits
  │── POST /translate + payment_hash ─>│
  │<── { translated_text: "..." } ─────│
```

- **Agents charge sats for services** — translation, transcription, data lookups, anything
- **Agents pay other agents** — chain services together, costs flow automatically
- **No API keys or accounts** — Lightning invoices are the auth layer
- **Discoverable via Nostr** — agents announce themselves; anyone can find and call them

---

## Quick Start

**Requirements:** Python 3.11+, a [LNbits](https://lnbits.com) wallet (free at legend.lnbits.com)

```bash
git clone https://github.com/intrinsicinvestment91/bitagent.git
cd bitagent
pip install -r requirements.txt
cp env.template .env
# edit .env: set LNBITS_URL and LNBITS_API_KEY
python main.py
```

The server starts on `http://localhost:8000`. Open `/docs` for the interactive API.

**Translate text (100 sats):**
```bash
# Step 1 — request service, get invoice
curl -X POST http://localhost:8000/polyglot/translate \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "target_language": "es"}'
# → {"payment_request": "lnbc...", "payment_hash": "abc123..."}

# Step 2 — pay the invoice with any Lightning wallet, then submit with payment_hash:
curl -X POST http://localhost:8000/polyglot/translate \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "target_language": "es", "payment_hash": "abc123..."}'
# → {"translated_text": "Hola mundo"}
```

---

## What's Included

| Agent | Endpoint | Service | Price |
|---|---|---|---|
| **PolyglotAgent** | `/polyglot/translate` | Text translation (100+ languages) | 100 sats |
| **PolyglotAgent** | `/polyglot/transcribe` | Audio → text (Whisper) | 250 sats |
| **CoordinatorAgent** | `/coordinator/translate_audio` | Audio → transcribe → translate | 350 sats |
| **PriceOracleAgent** | `/oracle/price/{coin}` | Live crypto price (BTC, ETH, LTC…) | 2 sats |
| **WebFetchAgent** | `/fetch/url` | Fetch & clean any public web page | 25 sats |
| **SearchAgent** | `/search/query` | Web search (Brave → SearXNG → DDG) | 10 sats |
| **StreamfinderAgent** | `/a2a` (JSON-RPC) | Streaming availability search | 100 sats |

All agents implement the **A2A JSON-RPC protocol** — they can call each other without human involvement.

---

## Use with Claude (MCP)

BitAgent ships an [MCP](https://modelcontextprotocol.io) server so Claude can call your agents as tools directly — no HTTP, no payment gate in the loop.

```bash
# Clone and install
git clone https://github.com/intrinsicinvestment91/bitagent.git
cd bitagent
pip install -r requirements.txt

# Add to Claude Code
claude mcp add bitagent -- python /path/to/bitagent/mcp_server.py
```

Or drop a `.mcp.json` in your project root:
```json
{
  "mcpServers": {
    "bitagent": {
      "type": "stdio",
      "command": "python",
      "args": ["/path/to/bitagent/mcp_server.py"]
    }
  }
}
```

Claude then has access to `search`, `fetch_url`, `translate`, `get_price`, and `convert_sats` as native tools. Each result includes a `cost_sats` field so you can track spending.

---

## Architecture

```
src/
├── agents/
│   ├── polyglot_agent/       # Translation & transcription (FastAPI router)
│   ├── coordinator_agent/    # Multi-agent orchestration
│   ├── price_oracle_agent/   # Live crypto prices (CoinGecko → Binance fallback)
│   ├── web_fetch_agent/      # Web page fetcher with SSRF protection
│   ├── search_agent/         # Web search (Brave → SearXNG → DuckDuckGo fallback)
│   └── streamfinder/         # A2A reference implementation
├── core/
│   ├── agent.py              # Base class: DID identity + wallet + security
│   ├── agent_server.py       # FastAPI wrapper with auto-generated endpoints
│   └── payment.py            # Payment flow helpers
├── security/                 # JWT auth, AES-256 encryption, input validation
├── identity/                 # DID document management (did:key, did:nostr, did:bitcoin)
├── network/                  # Nostr discovery, DHT peer-to-peer
└── wallets/                  # LNbits client, Fedimint ecash wallet

mcp_server.py                 # MCP stdio server — exposes agents as Claude tools
```

**Adding a new agent takes ~50 lines.** Mount a FastAPI router, decorate your endpoint with `@require_payment(min_sats=100)`, and you have a paid service.

---

## Use Cases

**Paid translation API** — instead of managing API keys and subscriptions, clients pay per request in sats. No account required.

**Autonomous research pipeline** — a coordinator agent calls a transcription agent, then a translation agent, then a summarization agent. Each hop is paid automatically from the coordinator's wallet.

**Agent marketplace** — agents announce services on Nostr. Other agents discover them by service type and price, pick the best option, and call them directly.

**Metered AI services** — wrap any ML model in an agent. Users pay per inference. No billing infrastructure needed.

---

## Deployment

**Cloud (Railway):** Connect this repo on [railway.app](https://railway.app). Set `LNBITS_URL` and `LNBITS_API_KEY` as environment variables. Done.

**Self-hosted (Start9):** See [`docs/START9_DEPLOYMENT_GUIDE.md`](docs/START9_DEPLOYMENT_GUIDE.md).

**Docker:**
```bash
docker-compose -f docker-compose.dev.yml up
```

---

## Contributing

BitAgent is early. There's a lot of room to build.

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add new agents, payment backends, and discovery protocols.

Good first issues are labeled [`good first issue`](https://github.com/intrinsicinvestment91/bitagent/issues?q=is%3Aissue+label%3A%22good+first+issue%22) on GitHub.

---

## License

MIT — use it, fork it, build on it.
