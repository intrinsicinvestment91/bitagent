# BitAgent

BitAgent is a Lightning-enabled AI agent framework. Agents can accept Bitcoin Lightning payments via LNbits and can announce themselves over Nostr — both are switched off by default.

## Setup

This package installs in **private free mode**, reachable on your local network only. Nothing needs to be filled in: every service is free and labelled free, and no Nostr connection is made. Leave it this way unless you have decided otherwise.

**Do not enter real credentials during this milestone.**

Under **Config**:

- **Enable Lightning payments** — off by default, so no LNbits wallet is needed. If you turn it on, the LNbits fields below become required and the service refuses to start without them.
- **LNbits URL** and **LNbits Admin API Key** — needed only when payments are enabled. If LNbits runs on this server, its URL is `http://lnbits.embassy`; the admin key is in LNbits → your wallet → API info.
- **Enable public Nostr discovery** — off by default, and while off this service opens no relay connections, publishes no announcements and creates no Nostr identity. Turning it on announces this agent publicly.
- **Nostr Private Key** — needed only when discovery is enabled, where it is required: 64 hex characters, giving the node a stable identity across restarts.
- **Public URL** — needed only when discovery is enabled: the address callers outside this machine use. It cannot be localhost.

## Agents

These prices apply only once Lightning payments are enabled. In the default free mode every service below is free.

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
