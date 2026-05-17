# Agent Registry API

The registry exposes agents this node has registered or discovered via Nostr/DHT.
All endpoints are read-only, unauthenticated, and require no payment.

## Base path

```
/agents
```

## Endpoints

### List agents

```
GET /agents/registry
```

Returns all locally known agents, with optional service filtering and pagination.

**Query parameters**

| Parameter | Type | Default | Constraints | Description |
|---|---|---|---|---|
| `service` | string | *(none)* | 1–64 chars; `[a-zA-Z0-9._-]` only | Filter to agents that offer this service |
| `limit` | integer | `50` | 1–100 | Max agents to return |
| `offset` | integer | `0` | ≥ 0 | Agents to skip (for pagination) |

**Response — 200**

```json
{
  "agents": [ ...AgentEntry ],
  "count": 2,
  "total": 6,
  "offset": 0,
  "limit": 50,
  "source": "local"
}
```

**Errors**

| Status | Condition |
|---|---|
| `422` | `service` contains disallowed characters or exceeds 64 chars |
| `422` | `limit` < 1 or > 100 |
| `422` | `offset` < 0 |

---

### Get agent by ID

```
GET /agents/registry/{agent_id}
```

Returns a single agent entry by its stable ID.

**Path parameters**

| Parameter | Description |
|---|---|
| `agent_id` | The agent's stable unique identifier (e.g. `bitagent-search`) |

**Response — 200** — see `AgentEntry` below

**Errors**

| Status | Condition |
|---|---|
| `404` | No agent with that ID is known to this node |

---

## AgentEntry schema

| Field | Type | Description |
|---|---|---|
| `agent_id` | string | Stable unique identifier |
| `name` | string | Human-readable display name |
| `description` | string | Short capability summary |
| `endpoint` | string | Base URL for client requests |
| `services` | string[] | Service identifiers offered (e.g. `search.query`) |
| `public_key` | string | Hex-encoded secp256k1 public key (64 chars) |
| `protocol` | string | Transport/payment protocol (e.g. `lightning+nostr`) |
| `last_seen` | float | Unix timestamp of last registration or heartbeat |
| `reputation_score` | float | Reputation in [0.0, 1.0]; 0.0 = unscored |
| `capabilities` | object | Arbitrary key/value capability metadata |

---

## Caching

Both endpoints set `Cache-Control: public, max-age=10`. Clients may cache responses
for up to 10 seconds. The registry reflects real-time discovery state, so short TTLs
are intentional.

---

## Pagination example

Fetch agents 11–20 (zero-indexed):

```bash
curl "https://bitagent-production.up.railway.app/agents/registry?limit=10&offset=10"
```

## Service filter example

Find all agents offering `search.query`:

```bash
curl "https://bitagent-production.up.railway.app/agents/registry?service=search.query"
```

## Notes

- `source` is always `"local"` — this node only returns agents it has directly registered
  or discovered. Cross-node federation is a future capability.
- `total` reflects the count before pagination; `count` is the number in the current page.
- The live OpenAPI spec is available at `/docs` (Swagger UI) and `/redoc`.
