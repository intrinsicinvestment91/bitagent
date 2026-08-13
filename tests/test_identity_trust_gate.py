"""Optional identity trust gate on streamfinder.search.

When IDENTITY_REQUIRE_FOR_PAID_SERVICES is on, callers must present a
``requester_pubkey`` whose trust score clears IDENTITY_MIN_TRUST_SCORE.
"""

from unittest.mock import patch

import pytest

import agent_logic

TRUSTED = {"IDENTITY_REQUIRE_FOR_PAID_SERVICES": "true", "IDENTITY_MIN_TRUST_SCORE": "0.25"}


class _UnknownRequester:
    async def get_identity(self, pubkey: str):
        return {"error": "Identity not found"}

    async def get_trust_signal(self, pubkey: str):
        return {"pubkey": pubkey, "trust_score": 0.0}


class _TrustedRequester:
    async def get_identity(self, pubkey: str):
        return {"pubkey": pubkey, "handle": "alice", "verified": True, "trust_score": 0.9}

    async def get_trust_signal(self, pubkey: str):
        return {"pubkey": pubkey, "trusted": True, "trust_score": 0.9, "basis": ["paid_nip05"]}


class _UntrustedRequester:
    async def get_identity(self, pubkey: str):
        return {"pubkey": pubkey, "handle": "mallory", "verified": False, "trust_score": 0.1}

    async def get_trust_signal(self, pubkey: str):
        return {"pubkey": pubkey, "trusted": False, "trust_score": 0.1, "basis": []}


@pytest.fixture
def free_streamfinder(free_gate):
    """streamfinder is a synthetic demo, so it settles without payment."""
    return free_gate


async def test_trust_checks_are_off_by_default(free_streamfinder):
    result = await agent_logic.handle_a2a_request("streamfinder.search", {"query": "Matrix"})

    assert result["found"] is True
    assert result["synthetic"] is True


async def test_enabled_rejects_a_request_with_no_requester(free_streamfinder):
    with patch.dict("os.environ", TRUSTED, clear=False):
        result = await agent_logic.handle_a2a_request(
            "streamfinder.search", {"query": "Matrix"}
        )

    assert "requester_pubkey" in result["error"]


async def test_enabled_rejects_an_unknown_requester(free_streamfinder):
    with (
        patch("src.agents.identity_agent.IdentityAgent", return_value=_UnknownRequester()),
        patch.dict("os.environ", TRUSTED, clear=False),
    ):
        result = await agent_logic.handle_a2a_request(
            "streamfinder.search", {"query": "Matrix", "requester_pubkey": "a" * 64}
        )

    assert result == {"error": "Requester identity not found"}


async def test_enabled_rejects_a_requester_below_the_threshold(free_streamfinder):
    with (
        patch("src.agents.identity_agent.IdentityAgent", return_value=_UntrustedRequester()),
        patch.dict("os.environ", TRUSTED, clear=False),
    ):
        result = await agent_logic.handle_a2a_request(
            "streamfinder.search", {"query": "Matrix", "requester_pubkey": "b" * 64}
        )

    assert "below minimum" in result["error"]


async def test_enabled_allows_a_trusted_requester_through(free_streamfinder):
    with (
        patch("src.agents.identity_agent.IdentityAgent", return_value=_TrustedRequester()),
        patch.dict("os.environ", TRUSTED, clear=False),
    ):
        result = await agent_logic.handle_a2a_request(
            "streamfinder.search", {"query": "Matrix", "requester_pubkey": "c" * 64}
        )

    assert result["found"] is True
