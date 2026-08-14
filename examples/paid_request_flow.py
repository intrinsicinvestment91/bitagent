#!/usr/bin/env python3
"""Walk the full paid-request lifecycle against a running BitAgent node.

    python examples/paid_request_flow.py --url http://localhost:8000

Shows what a client actually has to do, and demonstrates the two properties that
make the payment layer trustworthy: a payment buys exactly one request, and it
only buys the service it was issued for.

Against a node with payments enforced you will need to pay the printed invoice
before continuing. Against a node started with PAYMENTS_ENABLED=false the
services are free and every step returns immediately.
"""

import argparse
import json
import sys

import httpx


def show(label: str, response: httpx.Response) -> dict:
    body = response.json()
    print(f"\n=== {label} — HTTP {response.status_code} ===")
    print(json.dumps(body, indent=2)[:800])
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000", help="Node base URL")
    args = parser.parse_args()
    base = args.url.rstrip("/")

    with httpx.Client(timeout=30.0) as client:
        health = show("Node health", client.get(f"{base}/health"))
        payments_enforced = health.get("payments") == "enforced"

        show("Service catalog", client.get(f"{base}/services"))

        # 1. Ask for the service with no payment. A paid node answers 402 with a
        #    Lightning invoice; a free-mode node just does the work.
        first = client.post(f"{base}/search/query", json={"query": "bitcoin lightning"})
        body = show("Request without payment", first)

        if first.status_code != 402:
            print("\nThis node is running in free mode; nothing further to demonstrate.")
            return 0

        payment_hash = body["payment_hash"]
        print(f"\nPay this invoice, then press Enter:\n\n  {body['payment_request']}\n")
        if payments_enforced:
            input("Press Enter once paid... ")

        # 2. Resubmit with the payment hash.
        paid = client.post(
            f"{base}/search/query",
            json={"query": "bitcoin lightning", "payment_hash": payment_hash},
        )
        show("Request with payment", paid)
        if paid.status_code != 200:
            print("\nPayment was not accepted. Is the invoice settled?")
            return 1

        # 3. The same payment must not buy a second request.
        replay = client.post(
            f"{base}/search/query",
            json={"query": "something else", "payment_hash": payment_hash},
        )
        show("Replaying the same payment (expected 402 already_consumed)", replay)

        # 4. Nor a different, dearer service.
        cross = client.post(
            f"{base}/polyglot/translate",
            json={"text": "hello", "target_lang": "es", "payment_hash": payment_hash},
        )
        show("Reusing it on another service (expected 402 wrong_service)", cross)

    return 0


if __name__ == "__main__":
    sys.exit(main())
