# IdentityAgent

IdentityAgent provides paid NIP-05 registration, NIP-05 resolution, and machine-readable trust signals for BitAgent-to-BitAgent interactions.

## Endpoints

- A2A JSON-RPC: `POST /a2a`
- NIP-05 resolution: `GET /.well-known/nostr.json?name=<handle>`

## Registration Flow

`identity.register_nip05` creates a pending identity first, then activates it after Lightning payment is confirmed.

### Request invoice (step 1)

```bash
curl -X POST http://localhost:8000/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "identity.register_nip05",
    "params": {
      "pubkey": "3bf0c63fcb93463407af97a5e5ee64fa883d107ef9e558472c4eb9aaaefa459d",
      "handle": "alice",
      "domain": "example.com",
      "relays": ["wss://relay.damus.io"]
    }
  }'
```

Example response:

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32000,
    "message": "Pay this invoice, then resubmit the same request including payment_hash.",
    "data": {
      "payment_required": true,
      "service": "identity.register_nip05",
      "amount_sats": 1000,
      "payment_request": "lnbc...",
      "payment_hash": "abc123...",
      "expires_at": "2026-08-13T22:26:05+00:00"
    }
  },
  "id": 1
}
```

The invoice is a proper JSON-RPC error, not a result, so a standard client can detect it.

### Confirm payment (step 2)

```bash
curl -X POST http://localhost:8000/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "identity.register_nip05",
    "params": {
      "pubkey": "3bf0c63fcb93463407af97a5e5ee64fa883d107ef9e558472c4eb9aaaefa459d",
      "handle": "alice",
      "domain": "example.com",
      "relays": ["wss://relay.damus.io"],
      "payment_hash": "abc123..."
    }
  }'
```

## Payment Flow

- `identity.register_nip05` is always paid, and the payment is bound to the specific pending
  registration it was quoted for. Replaying a settled hash returns `already_consumed`.
- Query methods can run as free lookups in development when `IDENTITY_FREE_QUERIES=true`.
- If free mode is disabled, query methods return the standard payment-required envelope.

See [PAYMENTS.md](PAYMENTS.md) for the guarantees a payment carries.

## Validation and lifecycle

- `pubkey` must be a 64-character lowercase hex Nostr key; `handle` may contain only
  `a-z 0-9 - _ .`; `domain` must be a valid hostname. All three are lowercased.
- A paid registration is valid for one year. `expires_at` is set at verification and the
  `.well-known` resolver refuses to serve an expired identity.
- Requesting an invoice inserts a *pending* row that holds the handle. If that invoice is not paid
  before it expires, the handle is released to the next caller — otherwise anyone could squat every
  handle on the node for free by requesting invoices and never paying them.

## Known limitation

Registration does **not** prove control of the pubkey. Anyone willing to pay can register any
pubkey under any handle on this node. A Nostr signature challenge would close this; until then,
treat a NIP-05 record here as "someone paid to claim this", not as verified ownership.

## NIP-05 Endpoint

Resolve a verified identity:

```bash
curl "http://localhost:8000/.well-known/nostr.json?name=alice"
```

Example response:

```json
{
  "names": {
    "alice": "3bf0c63fcb93463407af97a5e5ee64fa883d107ef9e558472c4eb9aaaefa459d"
  },
  "relays": {
    "3bf0c63fcb93463407af97a5e5ee64fa883d107ef9e558472c4eb9aaaefa459d": ["wss://relay.damus.io"]
  }
}
```

If no matching active verified identity exists, response is:

```json
{
  "names": {}
}
```

## Trust Lookup Examples

### Identity lookup by pubkey

```bash
curl -X POST http://localhost:8000/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "identity.get_identity",
    "params": { "pubkey": "3bf0c63fcb93463407af97a5e5ee64fa883d107ef9e558472c4eb9aaaefa459d" }
  }'
```

### Trust signal lookup by pubkey

```bash
curl -X POST http://localhost:8000/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "identity.get_trust_signal",
    "params": { "pubkey": "3bf0c63fcb93463407af97a5e5ee64fa883d107ef9e558472c4eb9aaaefa459d" }
  }'
```

## Agent-Before-Transaction Use Case

A paid service can validate requester trust before generating an invoice:

1. requester sends `requester_pubkey`
2. service queries `identity.get_identity` and `identity.get_trust_signal`
3. service compares trust against local policy threshold
4. service either rejects early or proceeds to payment and execution

This avoids starting costly paid workflows for unknown or low-trust requesters.

## Security Warnings

- Trust score is heuristic and not KYC.
- NIP-05 verification is not legal identity verification.
- Always enforce your own risk policy for high-value workflows.
- Expired identities should not be treated as active trust anchors.
