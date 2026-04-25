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
      "pubkey": "npub1examplepubkey",
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
  "result": {
    "payment_required": true,
    "amount_sats": 1000,
    "payment_request": "lnbc...",
    "payment_hash": "hash123"
  },
  "id": 1
}
```

### Confirm payment (step 2)

```bash
curl -X POST http://localhost:8000/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "identity.register_nip05",
    "params": {
      "pubkey": "npub1examplepubkey",
      "handle": "alice",
      "domain": "example.com",
      "relays": ["wss://relay.damus.io"],
      "payment_hash": "hash123"
    }
  }'
```

## Payment Flow

- `identity.register_nip05` is always paid.
- Query methods can run as free lookups in development when `IDENTITY_FREE_QUERIES=true`.
- If free mode is disabled, query methods return standard BitAgent payment-required envelopes.

## NIP-05 Endpoint

Resolve a verified identity:

```bash
curl "http://localhost:8000/.well-known/nostr.json?name=alice"
```

Example response:

```json
{
  "names": {
    "alice": "npub1examplepubkey"
  },
  "relays": {
    "npub1examplepubkey": ["wss://relay.damus.io"]
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
    "params": { "pubkey": "npub1examplepubkey" }
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
    "params": { "pubkey": "npub1examplepubkey" }
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
