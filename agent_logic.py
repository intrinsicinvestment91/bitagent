"""Top-level A2A JSON-RPC dispatcher.

Every method here resolves a catalog service id and goes through the payment
gate. Previously ``oracle.*``, ``fetch.*`` and ``search.*`` were dispatched with
no payment check at all, so ``POST /a2a`` was a free mirror of the paid HTTP
routes; and the streamfinder branch fell back to serving results for free when
invoice creation raised.
"""

import logging
import os

from src.agents.streamfinder.streamfinder import StreamfinderAgent
from src.payments import Quote, UnknownServiceError, paid_work, require_payment
from src.security.secure_endpoints import sanitize_input

logger = logging.getLogger(__name__)

#: A2A method name -> catalog service id. Methods absent from this map are
#: rejected, so a new route cannot be added without also pricing it.
METHOD_SERVICES = {
    "oracle.price": "oracle.price",
    "oracle.prices": "oracle.prices",
    "oracle.convert": "oracle.convert",
    "fetch.url": "fetch.url",
    "search.query": "search.query",
    "polyglot.translate": "polyglot.translate",
    "polyglot.transcribe": "polyglot.transcribe",
    "identity.register_nip05": "identity.register_nip05",
    "identity.get_identity": "identity.get_identity",
    "identity.list_verified": "identity.list_verified",
    "identity.search": "identity.search",
    "identity.get_trust_signal": "identity.get_trust_signal",
    "streamfinder.search": "streamfinder.search",
}

_streamfinder: StreamfinderAgent | None = None


def _get_streamfinder() -> StreamfinderAgent:
    global _streamfinder
    if _streamfinder is None:
        _streamfinder = StreamfinderAgent()
    return _streamfinder


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


def _quote_to_dict(quote: Quote) -> dict:
    """Render a gate Quote as an A2A result body."""
    return dict(quote.body)


async def dispatch_service(method: str, params: dict) -> dict:
    """Run the work for a method whose payment has already settled.

    Public so the coordinator can execute chain steps in-process after it has
    collected payment for the whole chain, instead of HTTP-calling itself.
    """
    if method.startswith("oracle."):
        from src.agents.price_oracle_agent.price_oracle import PriceOracleAgent

        oracle = PriceOracleAgent()
        if method == "oracle.price":
            coin = str(params.get("coin", "bitcoin")).lower()
            result = await oracle.price([coin])
            return result.get(coin, {"error": "Not found"})
        if method == "oracle.prices":
            coins = [str(c).lower() for c in params.get("coins", ["bitcoin"])[:10]]
            return await oracle.price(coins)
        return await oracle.convert(params.get("sats", 0))

    if method == "fetch.url":
        from src.agents.web_fetch_agent.web_fetch import WebFetchAgent

        return await WebFetchAgent().fetch(params["url"])

    if method == "search.query":
        from src.agents.search_agent.search_agent import SearchAgent

        return await SearchAgent().search(params["query"], params.get("num_results", 10))

    if method.startswith("polyglot."):
        from src.agents.polyglot_agent.polyglot_agent import PolyglotAgent

        polyglot = PolyglotAgent()
        if method == "polyglot.translate":
            return await polyglot.handle_translation(
                sanitize_input(params["text"]),
                params.get("source_lang", "auto"),
                params.get("target_lang", "en"),
            )
        return await polyglot.handle_transcription(audio_data=params.get("audio_data"))

    if method.startswith("identity."):
        from src.agents.identity_agent import IdentityAgent

        identity = IdentityAgent()
        if method == "identity.get_identity":
            return await identity.get_identity(pubkey=params.get("pubkey", ""))
        if method == "identity.list_verified":
            return await identity.list_verified()
        if method == "identity.search":
            return await identity.search(query=params.get("query", ""))
        return await identity.get_trust_signal(pubkey=params.get("pubkey", ""))

    # streamfinder.search
    query = sanitize_input(params["query"], max_length=500)
    return _get_streamfinder().perform_search(query)


def _validate_params(method: str, params: dict) -> str | None:
    """Return an error message when required params are missing."""
    if method == "fetch.url" and not params.get("url"):
        return "Missing 'url'"
    if method == "search.query" and not params.get("query"):
        return "Missing 'query'"
    if method == "polyglot.translate" and not params.get("text"):
        return "Missing 'text'"
    if method == "polyglot.transcribe" and not params.get("audio_data"):
        return "Missing 'audio_data'"
    if method == "streamfinder.search" and not params.get("query"):
        return "Missing 'query' parameter"
    if method in {"identity.get_identity", "identity.get_trust_signal"} and not params.get(
        "pubkey"
    ):
        return "Missing 'pubkey'"
    if method == "identity.search" and not params.get("query"):
        return "Missing 'query'"
    return None


async def handle_a2a_request(method: str, params: dict) -> dict:
    """Dispatch one A2A call. Never returns service output without settlement."""
    params = params or {}

    service_id = METHOD_SERVICES.get(method)
    if service_id is None:
        return {"error": f"Unsupported method '{method}'"}

    validation_error = _validate_params(method, params)
    if validation_error:
        return {"error": validation_error}

    if method == "streamfinder.search":
        identity_gate_error = await _enforce_identity_trust_for_paid_request(params)
        if identity_gate_error:
            return identity_gate_error

    # Registration binds the payment to a pending database row, so it owns its
    # own settlement flow rather than using the generic gate here.
    if method == "identity.register_nip05":
        from src.agents.identity_agent import IdentityAgent

        return await IdentityAgent().register_nip05(
            pubkey=params.get("pubkey", ""),
            handle=params.get("handle", ""),
            domain=params.get("domain", ""),
            relays=params.get("relays"),
            payment_hash=params.get("payment_hash"),
        )

    if method.startswith("identity.") and os.getenv(
        "IDENTITY_FREE_QUERIES", "false"
    ).lower() in {"1", "true", "yes", "on"}:
        return await dispatch_service(method, params)

    try:
        outcome = await require_payment(
            service_id,
            params.get("payment_hash"),
            params.get("ecash_notes"),
            memo=method,
        )
    except UnknownServiceError:
        return {"error": f"Unsupported method '{method}'"}

    if isinstance(outcome, Quote):
        return _quote_to_dict(outcome)

    try:
        async with paid_work(outcome):
            return await dispatch_service(method, params)
    except Exception:
        logger.exception("A2A method %s failed after settlement", method)
        return {"error": "Service temporarily unavailable. Your payment can be retried."}
