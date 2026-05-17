"""
Tests for persistent vs ephemeral Nostr identity in EnhancedNostrDiscovery.
Covers: valid persistent key, no-key ephemeral fallback, malformed key fallback,
        unavailable-Nostr error path, and _ws_publish relay helper.

python-nostr's Event/PrivateKey/Filter modules import cleanly under Python 3.13.
RelayManager was dropped (its relay.py uses a mutable dataclass default rejected
by Python 3.13); relay connectivity is now handled by _ws_publish via aiohttp.
NOSTR_AVAILABLE is therefore True at import time — no patching required for the
happy-path tests.
"""

import asyncio
import logging
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from nostr.key import PrivateKey

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
