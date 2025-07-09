# agent_logic.py

import json
import logging
from fastapi import Request
from agent_wallet import AgentWallet
from .streamfinder import StreamfinderAgent

# Initialize agent and wallet
agent = StreamfinderAgent()
wallet = AgentWallet()

# Minimum sats required
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

        # Create invoice
        invoice_data = wallet.create_invoice(
            amount=TASK_PRICE_SATS,
            memo=f"Streamfinder: {query}"
        )

        # Defensive checks
        if not invoice_data:
            logging.error("Invoice creation failed: no response from LNbits")
            return {"error": "No response from LNbits invoice API"}

        payment_hash = invoice_data.get("payment_hash")
        payment_request = invoice_data.get("bolt11") or invoice_data.get("payment_request")

        if not payment_hash or not payment_request:
            logging.error(f"Invalid invoice response from wallet: {invoice_data}")
            return {"error": "Failed to generate Lightning invoice"}

        logging.info(f"Invoice created for query '{query}' with hash {payment_hash}")

        return {
            "payment_required": True,
            "amount_sats": TASK_PRICE_SATS,
            "payment_request": payment_request,
            "payment_hash": payment_hash
        }

    except Exception as e:
        logging.error(f"Error in handle_a2a_request: {e}")
        return {"error": str(e)}

async def handle_payment_confirmation(payment_hash: str, query: str):
    """Call after payment is confirmed."""
    try:
        logging.info(f"Checking payment for hash: {payment_hash}")
        if not wallet.check_invoice(payment_hash):
            return {"error": "Payment not yet received."}

        result = agent.perform_search(query)
        logging.info(f"Search result: {result}")
        return result

    except Exception as e:
        logging.error(f"Payment confirmation error: {e}")
        return {"error": str(e)}
