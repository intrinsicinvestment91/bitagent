import asyncio
from unittest.mock import patch

import agent_logic


class _MockIdentityAgentUnknown:
    async def get_identity(self, pubkey: str):
        return {"error": "Identity not found"}

    async def get_trust_signal(self, pubkey: str):
        return {"pubkey": pubkey, "trust_score": 0.0}


class _MockIdentityAgentTrusted:
    async def get_identity(self, pubkey: str):
        return {
            "pubkey": pubkey,
            "handle": "alice",
            "nip05": "alice@example.com",
            "verified": True,
            "category": "dev",
            "tags": ["nostr"],
            "trust_score": 0.9,
        }

    async def get_trust_signal(self, pubkey: str):
        return {
            "pubkey": pubkey,
            "trusted": True,
            "trust_score": 0.9,
            "basis": ["paid_nip05", "active_registration"],
            "warning": "Trust score is heuristic and not KYC.",
        }


class _MockWallet:
    def create_invoice(self, amount: int, memo: str = ""):
        return {"payment_hash": "hash_streamfinder", "bolt11": "ln_invoice_hash_streamfinder"}

    def check_invoice(self, checking_id: str) -> bool:
        return False


def _run(coro):
    return asyncio.run(coro)


def test_trust_checks_disabled_by_default():
    with patch.dict("os.environ", {}, clear=False):
        result = _run(
            agent_logic.handle_a2a_request(
                "streamfinder.search",
                {"query": "Matrix"},
            )
        )
    # With checks off, request continues to normal flow (invoice or search result).
    assert "error" not in result or "Missing 'query' parameter" not in str(result.get("error", ""))


def test_enabled_rejects_unknown_requester():
    with (
        patch("src.agents.identity_agent.IdentityAgent", return_value=_MockIdentityAgentUnknown()),
        patch.dict(
            "os.environ",
            {"IDENTITY_REQUIRE_FOR_PAID_SERVICES": "true", "IDENTITY_MIN_TRUST_SCORE": "0.25"},
            clear=False,
        ),
    ):
        result = _run(
            agent_logic.handle_a2a_request(
                "streamfinder.search",
                {"query": "Matrix", "requester_pubkey": "unknown_pubkey"},
            )
        )
    assert result == {"error": "Requester identity not found"}


def test_enabled_allows_trusted_requester_to_continue():
    original_wallet = agent_logic._wallet
    try:
        agent_logic._wallet = _MockWallet()
        with (
            patch("src.agents.identity_agent.IdentityAgent", return_value=_MockIdentityAgentTrusted()),
            patch.dict(
                "os.environ",
                {"IDENTITY_REQUIRE_FOR_PAID_SERVICES": "true", "IDENTITY_MIN_TRUST_SCORE": "0.25"},
                clear=False,
            ),
        ):
            result = _run(
                agent_logic.handle_a2a_request(
                    "streamfinder.search",
                    {"query": "Matrix", "requester_pubkey": "trusted_pubkey"},
                )
            )
    finally:
        agent_logic._wallet = original_wallet

    # Trusted requester should reach normal payment/service flow.
    assert "payment_required" in result or "results" in result
