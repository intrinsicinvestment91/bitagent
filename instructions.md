# BitAgent

BitAgent is a Lightning-enabled AI agent framework. Agents accept Bitcoin Lightning payments via LNbits and are discoverable via Nostr.

## Setup

After installing, go to **Config** and fill in:

- **LNbits URL** — the URL of your LNbits instance. If LNbits is installed on this Start9 server, use `http://lnbits.embassy`.
- **LNbits Admin API Key** — find this in LNbits → your wallet → API info → Admin key.
- **Nostr Private Key** (optional) — 64-char hex private key. Leave blank to disable Nostr broadcasting.

## Agents

| Endpoint | Service | Price |
|---|---|---|
| `/polyglot` | Translation | 100 sats |
| `/coordinator` | Multi-agent workflow | 350 sats |
| `/oracle` | Crypto price lookups | 2 sats |
| `/fetch` | Web page fetch | 25 sats |
| `/search` | Web search | 10 sats |

## API Docs

Navigate to the service URL and append `/docs` for the interactive Swagger documentation.

## Payment Flow

1. Client sends request without `payment_hash`
2. Server returns HTTP 402 with a Lightning invoice
3. Client pays the invoice
4. Client resends request with `payment_hash`
5. Server verifies payment and returns result
