import logging
import os
from src.agents.streamfinder.streamfinder import StreamfinderAgent
from src.security.secure_endpoints import sanitize_input
from src.wallets.fedimint_wallet import FedimintWallet

logger = logging.getLogger(__name__)

_agent = None
_wallet = None
_fedimint = FedimintWallet()


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


def _identity_checks_enabled() -> bool:
    return os.getenv("IDENTITY_REQUIRE_FOR_PAID_SERVICES", "false").lower() == "true"


def _identity_min_trust_score() -> float:
    raw = os.getenv("IDENTITY_MIN_TRUST_SCORE", "0.25")
    try:
        return float(raw)
    except ValueError:
        return 0.25


async def _enforce_identity_trust_for_paid_request(params: dict) -> dict | None:
    if not _identity_checks_enabled():
        return None

    requester_pubkey = params.get("requester_pubkey")
    if not requester_pubkey:
        return {"error": "Requester identity required: missing 'requester_pubkey'"}

    from src.agents.identity_agent import IdentityAgent

    identity_agent = IdentityAgent()
    requester_identity = await identity_agent.get_identity(pubkey=requester_pubkey)
    if requester_identity.get("error"):
        return {"error": "Requester identity not found"}

    trust = await identity_agent.get_trust_signal(pubkey=requester_pubkey)
    trust_score = float(trust.get("trust_score", 0.0))
    min_score = _identity_min_trust_score()
    if trust_score < min_score:
        return {"error": f"Requester trust score {trust_score} below minimum {min_score}"}

    return None


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

        if method.startswith("identity."):
            from src.agents.identity_agent import IdentityAgent

            identity = IdentityAgent()
            free_queries = os.getenv("IDENTITY_FREE_QUERIES", "false").lower() == "true"

            if method == "identity.register_nip05":
                return await identity.register_nip05(
                    pubkey=params.get("pubkey", ""),
                    handle=params.get("handle", ""),
                    domain=params.get("domain", ""),
                    relays=params.get("relays"),
                    payment_hash=params.get("payment_hash"),
                )

            if method not in {
                "identity.get_identity",
                "identity.list_verified",
                "identity.search",
                "identity.get_trust_signal",
            }:
                return {"error": f"Unknown identity method '{method}'"}

            if not free_queries:
                payment_hash = params.get("payment_hash")
                if payment_hash:
                    wallet = _get_wallet()
                    if not wallet.check_invoice(payment_hash):
                        return {"error": "Payment not verified"}
                else:
                    wallet = _get_wallet()
                    amount = int(identity.get_price(method))
                    invoice_data = wallet.create_invoice(
                        amount=amount,
                        memo=f"Identity query: {method}",
                    )
                    created_hash = invoice_data.get("payment_hash")
                    payment_request = invoice_data.get("bolt11") or invoice_data.get("payment_request")
                    if not created_hash or not payment_request:
                        return {"error": "Unable to create payment invoice"}
                    return {
                        "payment_required": True,
                        "amount_sats": amount,
                        "payment_request": payment_request,
                        "payment_hash": created_hash,
                    }

            if method == "identity.get_identity":
                return await identity.get_identity(pubkey=params.get("pubkey", ""))
            if method == "identity.list_verified":
                return await identity.list_verified()
            if method == "identity.search":
                return await identity.search(query=params.get("query", ""))
            if method == "identity.get_trust_signal":
                return await identity.get_trust_signal(pubkey=params.get("pubkey", ""))

        agent = _get_agent()

        if method != "streamfinder.search":
            return {"error": f"Unsupported method '{method}'"}

        query = params.get("query")
        if not query:
            return {"error": "Missing 'query' parameter"}

        identity_gate_error = await _enforce_identity_trust_for_paid_request(params)
        if identity_gate_error:
            return identity_gate_error

        query = sanitize_input(query, max_length=500)
        ecash_notes = params.get("ecash_notes")
        payment_hash = params.get("payment_hash")

        if ecash_notes:
            if await _fedimint.verify_and_receive(ecash_notes, agent.get_price()):
                return agent.perform_search(query)
            return {"error": "Ecash payment invalid or insufficient"}

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
            inv = {
                "payment_required": True,
                "amount_sats": agent.get_price(),
                "payment_request": payment_request,
                "payment_hash": payment_hash,
            }
            if _fedimint.enabled:
                inv["ecash_accepted"] = True
                inv["ecash_amount_msats"] = agent.get_price() * 1000
            return inv
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
