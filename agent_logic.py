import logging
from src.agents.streamfinder.streamfinder import StreamfinderAgent
from src.security.secure_endpoints import sanitize_input

logger = logging.getLogger(__name__)

_agent = None
_wallet = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = StreamfinderAgent()
    return _agent


def _get_wallet():
    global _wallet
    if _wallet is None:
        from agent_wallet import AgentWallet
        _wallet = AgentWallet()
    return _wallet


async def handle_a2a_request(method: str, params: dict) -> dict:
    try:
        # Route oracle, fetch, search methods to their agents
        if method.startswith("oracle."):
            from src.agents.price_oracle_agent.price_oracle import PriceOracleAgent
            oracle = PriceOracleAgent()
            if method == "oracle.price":
                return await oracle.price([params.get("coin", "bitcoin")])
            if method == "oracle.prices":
                return await oracle.price(params.get("coins", ["bitcoin"]))
            if method == "oracle.convert":
                return await oracle.convert(params.get("sats", 0))
            return {"error": f"Unknown oracle method '{method}'"}

        if method.startswith("fetch."):
            from src.agents.web_fetch_agent.web_fetch import WebFetchAgent
            fetcher = WebFetchAgent()
            if method == "fetch.url":
                url = params.get("url")
                if not url:
                    return {"error": "Missing 'url'"}
                return await fetcher.fetch(url)
            return {"error": f"Unknown fetch method '{method}'"}

        if method.startswith("search."):
            from src.agents.search_agent.search_agent import SearchAgent
            searcher = SearchAgent()
            if method == "search.query":
                q = params.get("query")
                if not q:
                    return {"error": "Missing 'query'"}
                return await searcher.search(q, params.get("num_results", 10))
            return {"error": f"Unknown search method '{method}'"}

        agent = _get_agent()

        if method != "streamfinder.search":
            return {"error": f"Unsupported method '{method}'"}

        query = params.get("query")
        if not query:
            return {"error": "Missing 'query' parameter"}

        query = sanitize_input(query, max_length=500)
        payment_hash = params.get("payment_hash")

        if payment_hash:
            wallet = _get_wallet()
            if wallet.check_invoice(payment_hash):
                return agent.perform_search(query)
            return {"error": "Payment not verified"}

        try:
            wallet = _get_wallet()
            invoice_data = wallet.create_invoice(
                amount=agent.get_price(),
                memo=f"Streamfinder: {query}",
            )
            payment_hash = invoice_data.get("payment_hash")
            payment_request = invoice_data.get("bolt11") or invoice_data.get("payment_request")
            if not payment_hash or not payment_request:
                raise ValueError("Invalid invoice response")
            return {
                "payment_required": True,
                "amount_sats": agent.get_price(),
                "payment_request": payment_request,
                "payment_hash": payment_hash,
            }
        except Exception:
            return agent.perform_search(query)

    except Exception as e:
        logger.error(f"handle_a2a_request error: {e}")
        return {"error": str(e)}


async def handle_payment_confirmation(body: dict) -> dict:
    try:
        payment_hash = body.get("payment_hash")
        query = body.get("query", "")
        if not payment_hash:
            return {"error": "Missing payment_hash"}
        wallet = _get_wallet()
        if not wallet.check_invoice(payment_hash):
            return {"error": "Payment not yet received"}
        return _get_agent().perform_search(query)
    except Exception as e:
        logger.error(f"handle_payment_confirmation error: {e}")
        return {"error": str(e)}
