"""
Tests for persistent vs ephemeral Nostr identity in EnhancedNostrDiscovery,
and for the relay query (_query_events / _ws_query) introduced in Packet 15.

python-nostr's Event/PrivateKey/Filter modules import cleanly under Python 3.13.
RelayManager was dropped (its relay.py uses a mutable dataclass default rejected
by Python 3.13); relay connectivity is now handled by _ws_publish/_ws_query via
aiohttp. NOSTR_AVAILABLE is therefore True at import time — no patching required
for the happy-path tests.
"""

import asyncio
import json
import logging
import time
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from nostr.key import PrivateKey
from nostr.filter import Filter, Filters

import src.network.p2p_discovery as pd_module

_LOG = "src.network.p2p_discovery"
_NOSTR_AVAIL = "src.network.p2p_discovery.NOSTR_AVAILABLE"


class TestNostrPersistentIdentity:
    """Valid NOSTR_PRIVATE_KEY → deterministic public key, 'persistent' logged."""

    def test_known_key_produces_correct_pubkey(self):
        k = PrivateKey()
        discovery = pd_module.EnhancedNostrDiscovery(k.raw_secret.hex())
        assert discovery.public_key.hex() == k.public_key.hex()

    def test_same_key_same_pubkey_across_instances(self):
        k = PrivateKey()
        key_hex = k.raw_secret.hex()
        d1 = pd_module.EnhancedNostrDiscovery(key_hex)
        d2 = pd_module.EnhancedNostrDiscovery(key_hex)
        assert d1.public_key.hex() == d2.public_key.hex()

    def test_logs_persistent_mode(self, caplog):
        k = PrivateKey()
        with caplog.at_level(logging.INFO, logger=_LOG):
            pd_module.EnhancedNostrDiscovery(k.raw_secret.hex())
        assert any("persistent" in r.message.lower() for r in caplog.records)

    def test_key_with_surrounding_whitespace_accepted(self):
        """strip() should handle copy-paste whitespace around the key."""
        k = PrivateKey()
        discovery = pd_module.EnhancedNostrDiscovery("  " + k.raw_secret.hex() + "\n")
        assert discovery.public_key.hex() == k.public_key.hex()


class TestNostrEphemeralIdentity:
    """No NOSTR_PRIVATE_KEY → fresh random keypair, 'ephemeral' logged."""

    def test_no_key_generates_valid_pubkey(self):
        discovery = pd_module.EnhancedNostrDiscovery()
        pubkey_hex = discovery.public_key.hex()
        assert len(pubkey_hex) == 64
        assert all(c in "0123456789abcdef" for c in pubkey_hex)

    def test_two_instances_have_different_pubkeys(self):
        d1 = pd_module.EnhancedNostrDiscovery()
        d2 = pd_module.EnhancedNostrDiscovery()
        assert d1.public_key.hex() != d2.public_key.hex()

    def test_logs_ephemeral_mode(self, caplog):
        with caplog.at_level(logging.INFO, logger=_LOG):
            pd_module.EnhancedNostrDiscovery()
        assert any("ephemeral" in r.message.lower() for r in caplog.records)


class TestNostrMalformedKey:
    """Invalid NOSTR_PRIVATE_KEY → falls back to ephemeral with a WARNING."""

    def _check_fallback(self, key: str, caplog) -> pd_module.EnhancedNostrDiscovery:
        with caplog.at_level(logging.WARNING, logger=_LOG):
            discovery = pd_module.EnhancedNostrDiscovery(key)
        assert len(discovery.public_key.hex()) == 64
        assert any("invalid" in r.message.lower() for r in caplog.records)
        return discovery

    def test_non_hex_string_falls_back(self, caplog):
        self._check_fallback("not-a-valid-hex-string", caplog)

    def test_too_short_hex_falls_back(self, caplog):
        self._check_fallback("deadbeef", caplog)  # 4 bytes, need 32

    def test_too_long_hex_falls_back(self, caplog):
        self._check_fallback("aa" * 33, caplog)  # 33 bytes, need 32

    def test_empty_string_treated_as_absent(self):
        """Empty string is falsy — goes directly to ephemeral path without warning."""
        discovery = pd_module.EnhancedNostrDiscovery("")
        assert len(discovery.public_key.hex()) == 64

    def test_fallback_logs_ephemeral_after_warning(self, caplog):
        with caplog.at_level(logging.INFO, logger=_LOG):
            pd_module.EnhancedNostrDiscovery("bad_key_value")
        messages = [r.message.lower() for r in caplog.records]
        assert any("invalid" in m for m in messages)
        assert any("ephemeral" in m for m in messages)


class TestNostrUnavailable:
    """When NOSTR_AVAILABLE is False, EnhancedNostrDiscovery raises RuntimeError."""

    def test_raises_when_nostr_unavailable(self):
        with patch(_NOSTR_AVAIL, False):
            with pytest.raises(RuntimeError, match="unavailable"):
                pd_module.EnhancedNostrDiscovery()

    def test_p2p_manager_skips_nostr_when_unavailable(self):
        with patch(_NOSTR_AVAIL, False):
            manager = pd_module.P2PDiscoveryManager()
        assert manager.nostr_discovery is None
        assert pd_module.DiscoveryProtocol.NOSTR not in manager.discovery_protocols


class TestWsPublish:
    """_ws_publish sends the NIP-01 message over a WebSocket connection."""

    def test_sends_message_to_relay(self):
        mock_ws = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.ws_connect = MagicMock(return_value=mock_ws)

        with patch("src.network.p2p_discovery.aiohttp.ClientSession", return_value=mock_session):
            asyncio.run(pd_module._ws_publish("wss://relay.example.com", '["EVENT",{}]'))

        mock_ws.send_str.assert_awaited_once_with('["EVENT",{}]')


# ---------------------------------------------------------------------------
# Helpers shared by TestWsQuery and TestQueryEvents
# ---------------------------------------------------------------------------

def _raw_event(agent_id: str = "agent-1") -> dict:
    return {
        "pubkey": "aa" * 32,
        "content": json.dumps({"agent_id": agent_id}),
        "created_at": int(time.time()),
        "kind": 30078,
        "tags": [["t", "bitagent"]],
        "sig": "cc" * 32,
    }


def _make_filters() -> Filters:
    return Filters([Filter(kinds=[30078], since=int(time.time() - 3600))])


# ---------------------------------------------------------------------------
# _ws_query unit tests
# ---------------------------------------------------------------------------

class TestWsQuery:
    """_ws_query collects EVENT messages and stops on EOSE or timeout."""

    def _run(self, messages: list[str], url: str = "wss://relay.test") -> list[dict]:
        """
        Drive _ws_query against a fake WebSocket that yields `messages` in order.
        Each call to receive_str() pops the next message from the list.
        """
        msg_iter = iter(messages)

        async def fake_receive_str(timeout=None):
            try:
                return next(msg_iter)
            except StopIteration:
                raise asyncio.TimeoutError

        mock_ws = AsyncMock()
        mock_ws.receive_str = fake_receive_str
        mock_ws.send_str = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.ws_connect = MagicMock(return_value=mock_ws)

        with patch("src.network.p2p_discovery.aiohttp.ClientSession", return_value=mock_session):
            return asyncio.run(pd_module._ws_query(url, '["REQ","sub1",{}]', "sub1"))

    def test_returns_events_before_eose(self):
        evt = json.dumps(["EVENT", "sub1", _raw_event("a1")])
        eose = json.dumps(["EOSE", "sub1"])
        results = self._run([evt, eose])
        assert len(results) == 1
        assert results[0]["content"] == json.dumps({"agent_id": "a1"})

    def test_multiple_events_before_eose(self):
        msgs = [
            json.dumps(["EVENT", "sub1", _raw_event("a1")]),
            json.dumps(["EVENT", "sub1", _raw_event("a2")]),
            json.dumps(["EOSE", "sub1"]),
        ]
        results = self._run(msgs)
        assert len(results) == 2

    def test_stops_at_eose_ignores_later_events(self):
        msgs = [
            json.dumps(["EVENT", "sub1", _raw_event("a1")]),
            json.dumps(["EOSE", "sub1"]),
            json.dumps(["EVENT", "sub1", _raw_event("a2")]),  # should not be collected
        ]
        results = self._run(msgs)
        assert len(results) == 1

    def test_timeout_returns_partial_results(self):
        # Only one event before the iterator runs out (simulating timeout)
        msgs = [json.dumps(["EVENT", "sub1", _raw_event("a1")])]
        results = self._run(msgs)
        assert len(results) == 1

    def test_empty_result_when_no_events(self):
        results = self._run([json.dumps(["EOSE", "sub1"])])
        assert results == []

    def test_malformed_json_skipped(self):
        msgs = [
            "not valid json{{",
            json.dumps(["EVENT", "sub1", _raw_event("a1")]),
            json.dumps(["EOSE", "sub1"]),
        ]
        results = self._run(msgs)
        assert len(results) == 1

    def test_event_for_wrong_sub_id_skipped(self):
        msgs = [
            json.dumps(["EVENT", "other-sub", _raw_event("a1")]),
            json.dumps(["EOSE", "sub1"]),
        ]
        results = self._run(msgs)
        assert results == []

    def test_connection_failure_returns_empty(self):
        with patch("src.network.p2p_discovery.aiohttp.ClientSession", side_effect=OSError("refused")):
            result = asyncio.run(pd_module._ws_query("wss://dead.relay", '["REQ","s",{}]', "s"))
        assert result == []


# ---------------------------------------------------------------------------
# _query_events integration tests
# ---------------------------------------------------------------------------

class TestQueryEvents:
    """_query_events aggregates results from all relays via _ws_query."""

    def test_returns_events_from_all_relays(self):
        async def fake_query(url, req_msg, sub_id, per_relay_timeout=5.0):
            return [_raw_event(url[-4:])]  # one unique event per relay

        async def run():
            d = pd_module.EnhancedNostrDiscovery()
            with patch("src.network.p2p_discovery._ws_query", side_effect=fake_query):
                return await d._query_events(_make_filters())

        events = asyncio.run(run())
        assert len(events) == len(pd_module.EnhancedNostrDiscovery().relays)

    def test_relay_failure_does_not_crash(self):
        call_count = 0

        async def flaky_query(url, req_msg, sub_id, per_relay_timeout=5.0):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise OSError("dead relay")
            return [_raw_event("ok")]

        async def run():
            d = pd_module.EnhancedNostrDiscovery()
            with patch("src.network.p2p_discovery._ws_query", side_effect=flaky_query):
                return await d._query_events(_make_filters())

        events = asyncio.run(run())
        assert len(events) > 0  # at least the non-failing relays contributed

    def test_all_relays_fail_returns_empty(self):
        async def dead_query(url, req_msg, sub_id, per_relay_timeout=5.0):
            return []

        async def run():
            d = pd_module.EnhancedNostrDiscovery()
            with patch("src.network.p2p_discovery._ws_query", side_effect=dead_query):
                return await d._query_events(_make_filters())

        events = asyncio.run(run())
        assert events == []

    def test_malformed_event_dict_skipped(self):
        """A raw event with bad fields should be dropped, not crash the method."""
        async def bad_query(url, req_msg, sub_id, per_relay_timeout=5.0):
            return [{"this": "is", "not": "a valid event"}]

        async def run():
            d = pd_module.EnhancedNostrDiscovery()
            with patch("src.network.p2p_discovery._ws_query", side_effect=bad_query):
                return await d._query_events(_make_filters())

        # Should not raise; bad events are silently dropped
        events = asyncio.run(run())
        assert isinstance(events, list)
