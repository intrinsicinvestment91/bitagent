# Contributing to BitAgent

## Ways to contribute

- **New agents** — implement a service agent that accepts Lightning payments
- **Payment backends** — add support for new wallets beyond LNbits/Fedimint
- **Discovery protocols** — extend the Nostr/DHT discovery layer
- **Bug fixes** — see open issues labeled `bug`
- **Docs and examples** — improve quick starts or add real-world examples

## Development setup

```bash
git clone https://github.com/intrinsicinvestment91/bitagent.git
cd bitagent
pip install -r requirements.txt
cp env.template .env   # add your LNBITS_URL and LNBITS_API_KEY
python main.py
```

## Adding a new agent

1. Create `src/agents/your_agent/` with an `__init__.py` that exports a FastAPI `router`
2. Use `@require_payment(min_sats)` from `src/core/payment.py` to gate endpoints
3. Mount the router in `main.py` under a `/your_agent` prefix
4. Add a route to the A2A endpoint in `agent_logic.py` if you want agent-to-agent calls

Look at `src/agents/streamfinder/` as the reference A2A implementation and `src/agents/polyglot_agent/` for a service agent with payment gating.

## Pull requests

- Keep PRs focused — one feature or fix per PR
- Run `pytest tests/` before submitting
- CI must pass

## Questions

Open a GitHub Discussion or file an issue.
