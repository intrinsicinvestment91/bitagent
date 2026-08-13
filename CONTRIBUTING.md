# Contributing to BitAgent

## Ways to contribute

- **New agents** — implement a service agent that accepts Lightning payments
- **A real data source for Streamfinder** — it is currently a labelled demo over a fixed dataset
- **Migrating Start9 onto the payment gate** — `start9_server.py` still uses the legacy wallet
- **Payment backends** — add support for wallets beyond LNbits/Fedimint
- **Discovery protocols** — extend the Nostr/DHT discovery layer
- **Bug fixes** — see open issues labeled `bug`
- **Docs and examples** — improve quick starts or add real-world examples

## Development setup

```bash
git clone https://github.com/intrinsicinvestment91/bitagent.git
cd bitagent
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env   # add your LNBITS_URL and LNBITS_API_KEY
python main.py

# Or run with no wallet at all — every service is free and labelled as such:
PAYMENTS_ENABLED=false python main.py
```

Before submitting:

```bash
ruff check . && ruff format --check .
PAYMENTS_ENABLED=false pytest
```

## Adding a new agent

1. Register your service in `SERVICES` in `src/payments/catalog.py`, with a stable
   `<agent>.<method>` id and a price in sats.
2. Create `src/agents/your_agent/` with an `__init__.py` exporting a FastAPI `router`.
3. Gate each priced route through the payment gate:

```python
from src.payments import Quote, paid_work, require_payment

outcome = await require_payment("your_agent.method", body.payment_hash, body.ecash_notes)
if isinstance(outcome, Quote):
    return JSONResponse(status_code=outcome.status_code, content=outcome.body)
async with paid_work(outcome):
    return await do_the_work(...)
```

4. Mount the router in `main.py` under a `/your_agent` prefix.
5. Add the method to `METHOD_SERVICES` and `dispatch_service()` in `agent_logic.py` so it is
   reachable — and priced — over A2A.

`src/agents/search_agent/` is the canonical reference.

### Rules the tests enforce

These are not style preferences; a PR that breaks one will fail CI.

- **No free bypasses.** Every priced HTTP route needs an A2A twin at the same price, resolving the
  same catalog id. `tests/payments/test_no_free_bypass.py` sweeps every route and method.
- **No charging for fabricated output.** A service marked `synthetic` must be free — the catalog
  constructor rejects anything else. If a backend is optional, give the service an
  `is_available` check so it is not billed for when missing.
- **Never fail open.** If you cannot verify a payment, return 503. Do not return the result, and do
  not return a bare 402 that implies the caller has not paid. Add payment logic only in
  `src/payments/`; do not reintroduce per-agent payment helpers.
- **Prices live in the catalog.** Read them with `price_of()` / `pricing_for()`. Do not hardcode a
  price in a route, an agent class, a docstring, or the MCP server.

## Credentials

- LNbits credentials come from untracked local configuration (`.env`) — never commit them
- Do not use realistic provider credentials as test fixtures; use an obvious placeholder such as
  `replace-with-local-demo-key`
- `tests/security/test_no_tracked_credentials.py` guards against reintroduction. Note that it scans
  tracked files only, not git history

## Pull requests

- Keep PRs focused — one feature or fix per PR
- CI must pass: lint, the full test suite on 3.11 and 3.12, a Docker build, and the check that a
  misconfigured node refuses to start

## Questions

Open a GitHub Discussion or file an issue.
