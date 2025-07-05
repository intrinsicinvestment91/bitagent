# __init__.py

import json
import logging
from fastapi import Request
from lnbits_client import LNbitsClient
from agent_wallet import AgentWallet
from .streamfinder import StreamfinderAgent

# Initialize agent and payment tools
agent = StreamfinderAgent()
wallet = AgentWallet()
lnbits = LNbitsClient()

# Set this agent's minimum sats per task
TASK_PRICE_SATS = agent.get_price()

async def handle_a2a_request(request: Request):
    try:
        body = await request.json()
        logging.info(f"Received A2A request: {body}")

        method = body.get("method")
        params = body.get("params", {})

        if method != "streamfinder.search":
            return {
                "error": f"Unsupported method '{method}'. Use 'streamfinder.search'."
            }

        query = params.get("query")
        if not query:
            return {"error": "Missing 'query' parameter in request."}

        # 1. Create invoice
        invoice_data = lnbits.create_invoice(
            amount=TASK_PRICE_SATS,
            memo=f"Streamfinder: {query}"
        )
        payment_hash = invoice_data["payment_hash"]
        payment_request = invoice_data["payment_request"]

        logging.info(f"Invoice created for query '{query}' with hash {payment_hash}")

        # 2. Return invoice to client
        response = {
            "payment_required": True,
            "amount_sats": TASK_PRICE_SATS,
            "payment_request": payment_request,
            "payment_hash": payment_hash
        }
        return response

    except Exception as e:
        logging.error(f"Error in handle_a2a_request: {e}")
        return {"error": str(e)}

async def handle_payment_confirmation(payment_hash: str, query: str):
    """Call after payment has been confirmed (manually or automatically)."""
    try:
        logging.info(f"Checking payment for hash: {payment_hash}")
        if not lnbits.check_invoice(payment_hash):
            return {"error": "Payment not yet received."}

        result = agent.perform_search(query)
        logging.info(f"Search result: {result}")
        return result

    except Exception as e:
        logging.error(f"Payment confirmation error: {e}")
        return {"error": str(e)}
