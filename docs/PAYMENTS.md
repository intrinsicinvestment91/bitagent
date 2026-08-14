# The payment model

How BitAgent charges for a request, and what guarantees a caller actually gets.

## The flow

```
1. POST /search/query {"query": "..."}
   → 402 {"payment_required": true, "amount_sats": 10,
          "payment_request": "lnbc10n1...", "payment_hash": "abc…",
          "expires_at": "2026-08-13T22:26:05Z"}

2. Pay the bolt11 invoice with any Lightning wallet.

3. POST /search/query {"query": "...", "payment_hash": "abc…"}
   → 200 {"results": [...]}

4. POST /search/query {"query": "...", "payment_hash": "abc…"}
   → 402 {"error": "already_consumed"}
```

Over A2A JSON-RPC the same thing happens, with the 402 arriving as an error object with code
`-32000` and the invoice under `error.data`.

## What a payment buys

**Exactly one request.** Every invoice the node issues is written to a durable ledger *before* the
402 is returned. Redemption flips that row from `issued` to `consumed` inside a single
`BEGIN IMMEDIATE` transaction, so two concurrent requests carrying the same hash cannot both be
served — SQLite takes the write lock on the first statement and exactly one observes `issued`.

**Exactly one service, at one price.** The ledger row records which service and price the hash was
quoted for. A hash issued for the 2-sat price lookup is refused by the 100-sat translation endpoint
with `wrong_service`, and a hash this node never issued is refused with `unknown_payment_hash`.

**A bounded window.** Quotes expire (`INVOICE_TTL_SECONDS`, default one hour) so an unpaid quote
cannot be redeemed a week later. Expired unpaid quotes are purged hourly; consumed rows are kept as
the audit trail, so an old replay attempt still gets a clear `already_consumed` rather than looking
like an unknown hash.

## Rejection reasons

Every 402 names its cause, so a client can tell "pay me" from "stop replaying" from "you asked the
wrong endpoint".

| `error` | Meaning |
|---|---|
| `payment_not_settled` | The invoice exists but has not been paid yet |
| `already_consumed` | This payment has been redeemed. Buy another invoice |
| `wrong_service` | Issued for a different service |
| `amount_mismatch` | The settled amount was below the invoiced amount |
| `unknown_payment_hash` | Not issued by this node |
| `expired` | The quote's redemption window closed |
| `invalid_payment` | The record is an outgoing payment, not an incoming one |

## Failure modes

The rule is that **no failure produces free service**, and no failure silently takes money either.

| Situation | Response |
|---|---|
| Wallet unreachable when verifying | **503** `payment_verification_unavailable` — your invoice is still valid, retry |
| Wallet unreachable when quoting | **503** `invoice_unavailable` |
| LNbits returns an unrecognisable record | Treated as `UNKNOWN` → 503 |
| Optional backend not installed | **503** `service_unavailable`, and the service is not billed for |
| The work fails *after* settlement | The payment is **released** back to redeemable, and the failure is reported. Retry with the same hash |

That last one matters: Lightning payments cannot be refunded by the recipient, so if an upstream
API dies after we have taken the sats, handing the payment back is the only honest option.

## Running without a wallet

`PAYMENTS_ENABLED` is tri-state:

| LNbits configured | `PAYMENTS_ENABLED` | Behaviour |
|---|---|---|
| yes | unset / `true` | Payments enforced |
| no | `false` | Free mode — everything free, and labelled so in `/health`, `/services` and each `/info` |
| no | unset / `true` | **The node refuses to start** |

The third row is the important one. The alternative — starting up and serving every paid service
for free — is what the previous implementation did whenever `LNBITS_API_KEY` was missing.

## Durability

The ledger lives at `$BITAGENT_DATA_DIR/payments.db` (`/data/payments.db` in the Docker image).

**Mount it on a volume.** If the ledger is lost, the node no longer knows which hashes it has
already honoured, and every previously settled payment becomes replayable.

## Ecash

When `FEDIMINT_CLIENTD_URL` and `FEDIMINT_CLIENTD_PASSWORD` are set, 402 responses also advertise
`ecash_accepted`, and endpoints accept `ecash_notes` in place of `payment_hash`. Ecash is single-use
by construction: notes are validated non-destructively, then reissued, which burns them. A failure
in the ecash backend returns 503 rather than falling through.

## Prices

`GET /services` returns every billable surface with its current price and availability. Prices come
from one place — `src/payments/catalog.py` — which every route, the A2A dispatcher, each agent's
`/info`, and the MCP server read from. Nothing hardcodes a price.

A service whose output is placeholder data is marked `synthetic` and **must** be free; the catalog
refuses to construct a priced synthetic service, and a test asserts it across the whole catalog.

## Operational visibility

With `ADMIN_API_KEY` set, two routes appear, both requiring an `X-Admin-Key` header:

- `GET /wallet/balance` — the node's Lightning balance
- `GET /wallet/ledger` — counts and sat totals for issued vs consumed invoices

Without the key they are not registered at all, so forgetting to set one cannot leave the balance
public — which is how `GET /wallet/balance` used to behave.
