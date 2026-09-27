"""Startup and the registry must generate no public discovery traffic by default.

The tripwires here are deliberate: relay publish/query and the Nostr identity
constructor are replaced with functions that raise, so "nothing happened" is
proven by the absence of an exception rather than assumed. Nothing in this file
reaches the network, and no key used below belongs to anything.
"""

import traceback
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

import main
from src.network import p2p_discovery
from src.network.discovery_config import (
    DiscoveryConfig,
    DiscoveryConfigError,
    DiscoveryDisabledError,
    DiscoveryUnavailableError,
)
from src.network.p2p_discovery import (
    existing_discovery_manager,
    get_discovery_manager,
    preflight_discovery,
    reset_discovery_manager,
)

VALID_KEY = "11" * 32
PUBLIC_URL = "https://agent.example.test"

_REGISTRY_MGR = "src.network.registry_router.existing_discovery_manager"


@pytest.fixture(autouse=True)
def clean_discovery_state(monkeypatch):
    """No leaked singleton, no inherited environment, in either direction."""
    for name in (
        "NOSTR_DISCOVERY_ENABLED",
        "NOSTR_PRIVATE_KEY",
        "PUBLIC_URL",
        "RAILWAY_PUBLIC_DOMAIN",
    ):
        monkeypatch.delenv(name, raising=False)
    reset_discovery_manager()
    yield
    reset_discovery_manager()


@pytest.fixture(autouse=True)
def no_relay_traffic(monkeypatch):
    """Any attempt to reach a relay fails loudly instead of leaving the machine."""

    async def _forbidden(*args, **kwargs):
        raise AssertionError("a Nostr relay connection was attempted")

    monkeypatch.setattr(p2p_discovery, "_ws_publish", _forbidden)
    monkeypatch.setattr(p2p_discovery, "_ws_query", _forbidden)


@pytest.fixture
def identity_tripwire(monkeypatch) -> MagicMock:
    """Fail if a Nostr identity is constructed at all."""
    tripwire = MagicMock(side_effect=AssertionError("a Nostr identity was created"))
    monkeypatch.setattr(p2p_discovery, "EnhancedNostrDiscovery", tripwire)
    return tripwire


@pytest.fixture
def broadcast_recorder(monkeypatch) -> list[DiscoveryConfig]:
    """Replace the broadcast coroutine with one that only records its argument."""
    calls: list[DiscoveryConfig] = []

    async def _record(config: DiscoveryConfig) -> None:
        calls.append(config)

    monkeypatch.setattr(main, "_broadcast_agents", _record)
    return calls


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


class TestDisabledStartup:
    def test_no_broadcast_task_is_scheduled(self, broadcast_recorder, identity_tripwire):
        with TestClient(main.app) as client:
            assert client.get("/health").status_code in (200, 503)
        assert broadcast_recorder == []
        identity_tripwire.assert_not_called()

    def test_no_discovery_manager_is_created(self, identity_tripwire):
        with TestClient(main.app):
            assert existing_discovery_manager() is None
        assert p2p_discovery._manager is None
        identity_tripwire.assert_not_called()

    def test_startup_says_so_once(self, caplog, identity_tripwire):
        with caplog.at_level("INFO", logger="main"), TestClient(main.app):
            pass
        disabled = [r for r in caplog.records if "Public discovery is disabled" in r.message]
        assert len(disabled) == 1
        assert "Nostr broadcast scheduled" not in caplog.text


class TestEnabledStartup:
    """An enabled node must prove it can announce before it finishes starting."""

    @pytest.fixture
    def enabled(self, monkeypatch) -> DiscoveryConfig:
        config = DiscoveryConfig(True, VALID_KEY, PUBLIC_URL)
        monkeypatch.setattr(main, "discovery_config", config)
        return config

    def test_broadcast_is_scheduled_with_the_validated_config(
        self, enabled, monkeypatch, broadcast_recorder
    ):
        """The flag has to actually gate something, or the tests above prove nothing."""
        monkeypatch.setattr(p2p_discovery, "preflight_discovery", lambda config: MagicMock())
        with TestClient(main.app):
            pass
        assert broadcast_recorder == [enabled]

    def test_preflight_runs_before_the_broadcast_is_scheduled(self, enabled, monkeypatch):
        order: list[str] = []

        def _preflight(config):
            order.append("preflight")
            return MagicMock()

        async def _broadcast(config):
            order.append("broadcast")

        monkeypatch.setattr(p2p_discovery, "preflight_discovery", _preflight)
        monkeypatch.setattr(main, "_broadcast_agents", _broadcast)
        with TestClient(main.app):
            pass
        assert order[0] == "preflight"
        assert "broadcast" in order

    def test_unavailable_nostr_support_aborts_startup(
        self, enabled, monkeypatch, broadcast_recorder
    ):
        monkeypatch.setattr(p2p_discovery, "NOSTR_AVAILABLE", False)
        with pytest.raises(DiscoveryUnavailableError, match="Nostr support is unavailable"):
            with TestClient(main.app):
                pass
        assert broadcast_recorder == []

    def test_identity_construction_failure_aborts_startup(
        self, enabled, monkeypatch, broadcast_recorder
    ):
        monkeypatch.setattr(
            p2p_discovery,
            "EnhancedNostrDiscovery",
            MagicMock(side_effect=RuntimeError("identity backend unavailable")),
        )
        with pytest.raises(DiscoveryUnavailableError, match="could not"):
            with TestClient(main.app):
                pass
        assert broadcast_recorder == []
        assert existing_discovery_manager() is None

    def test_manager_without_an_identity_aborts_startup(
        self, enabled, monkeypatch, broadcast_recorder
    ):
        identity_less = MagicMock()
        identity_less.nostr_discovery = None
        monkeypatch.setattr(
            p2p_discovery, "get_discovery_manager", lambda config=None: identity_less
        )
        with pytest.raises(DiscoveryUnavailableError, match="no Nostr identity"):
            with TestClient(main.app):
                pass
        assert broadcast_recorder == []

    def test_a_refused_config_aborts_startup(self, monkeypatch, broadcast_recorder):
        """A config built by hand is revalidated, so a bad one cannot start a node."""
        monkeypatch.setattr(main, "discovery_config", DiscoveryConfig(True, "ff" * 31, PUBLIC_URL))
        with pytest.raises(DiscoveryConfigError):
            with TestClient(main.app):
                pass
        assert broadcast_recorder == []


class TestPreflight:
    """Preflight builds an identity and nothing else — the relay tripwires in this
    module's autouse fixture are what prove no connection is made."""

    @pytest.mark.skipif(not p2p_discovery.NOSTR_AVAILABLE, reason="nostr library unavailable")
    def test_returns_a_manager_with_an_identity(self):
        manager = preflight_discovery(DiscoveryConfig(True, VALID_KEY, PUBLIC_URL))
        assert manager.nostr_discovery is not None
        assert manager.nostr_discovery.private_key.raw_secret.hex() == VALID_KEY

    def test_refuses_a_disabled_config(self, identity_tripwire):
        with pytest.raises(DiscoveryDisabledError):
            preflight_discovery(DiscoveryConfig(False, None, None))
        identity_tripwire.assert_not_called()

    def test_refuses_an_invalid_config(self, identity_tripwire):
        with pytest.raises(DiscoveryConfigError):
            preflight_discovery(DiscoveryConfig(True, VALID_KEY, "http://127.0.0.1:8000"))
        identity_tripwire.assert_not_called()


# ---------------------------------------------------------------------------
# The production accessor
# ---------------------------------------------------------------------------


class TestAccessorFailsClosed:
    def test_refuses_while_disabled(self, identity_tripwire):
        with pytest.raises(DiscoveryDisabledError, match="NOSTR_DISCOVERY_ENABLED"):
            get_discovery_manager()
        assert existing_discovery_manager() is None
        identity_tripwire.assert_not_called()

    def test_refuses_enabled_without_a_key(self, monkeypatch, identity_tripwire):
        monkeypatch.setenv("NOSTR_DISCOVERY_ENABLED", "true")
        monkeypatch.setenv("PUBLIC_URL", PUBLIC_URL)
        with pytest.raises(DiscoveryConfigError):
            get_discovery_manager()
        assert existing_discovery_manager() is None
        identity_tripwire.assert_not_called()

    def test_refuses_enabled_with_an_invalid_key_rather_than_going_ephemeral(
        self, monkeypatch, identity_tripwire
    ):
        monkeypatch.setenv("NOSTR_DISCOVERY_ENABLED", "true")
        monkeypatch.setenv("NOSTR_PRIVATE_KEY", "ff" * 31)
        monkeypatch.setenv("PUBLIC_URL", PUBLIC_URL)
        with pytest.raises(DiscoveryConfigError):
            get_discovery_manager()
        assert existing_discovery_manager() is None
        identity_tripwire.assert_not_called()

    def test_refuses_enabled_without_a_routable_public_url(self, monkeypatch, identity_tripwire):
        monkeypatch.setenv("NOSTR_DISCOVERY_ENABLED", "true")
        monkeypatch.setenv("NOSTR_PRIVATE_KEY", VALID_KEY)
        monkeypatch.setenv("PUBLIC_URL", "http://localhost:8000")
        with pytest.raises(DiscoveryConfigError, match="only on this machine"):
            get_discovery_manager()
        assert existing_discovery_manager() is None
        identity_tripwire.assert_not_called()

    @pytest.mark.skipif(not p2p_discovery.NOSTR_AVAILABLE, reason="nostr library unavailable")
    def test_builds_one_manager_from_a_validated_config(self):
        config = DiscoveryConfig(True, VALID_KEY, PUBLIC_URL)
        manager = get_discovery_manager(config)
        assert manager is get_discovery_manager(config)
        assert existing_discovery_manager() is manager
        # The configured key, not an improvised one.
        assert manager.nostr_discovery.private_key.raw_secret.hex() == VALID_KEY


def _formatted(exc: BaseException) -> str:
    return "".join(traceback.format_exception(exc))


def _unavailable(exc: BaseException) -> DiscoveryUnavailableError:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if isinstance(current, DiscoveryUnavailableError):
            return current
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    raise AssertionError(f"no DiscoveryUnavailableError in {exc!r}")


class _LeakingPrivateKey:
    """Stand-in for nostr.key.PrivateKey that quotes the configured secret.

    Instantiating with arguments is the persistent-key path. Instantiating with
    none is the ephemeral fallback. The production accessor must take the first
    and never the second.
    """

    calls: list[tuple[tuple, dict]] = []

    def __init__(self, *args, **kwargs):
        type(self).calls.append((args, kwargs))
        if not args and not kwargs:
            raise AssertionError("zero-argument PrivateKey fallback was attempted")
        raise RuntimeError(f"could not load key {VALID_KEY}")


@pytest.mark.skipif(not p2p_discovery.NOSTR_AVAILABLE, reason="nostr library unavailable")
class TestStrictIdentityBoundary:
    """The production accessor must not inherit EnhancedNostrDiscovery's default
    ephemeral fallback, and must not leak a key that a library exception quoted."""

    @pytest.fixture
    def leaking_private_key(self, monkeypatch) -> type[_LeakingPrivateKey]:
        _LeakingPrivateKey.calls = []
        monkeypatch.setattr(p2p_discovery, "PrivateKey", _LeakingPrivateKey)
        return _LeakingPrivateKey

    def test_strict_accessor_does_not_fall_back_or_leak(self, leaking_private_key, caplog):
        with caplog.at_level("DEBUG"), pytest.raises(DiscoveryUnavailableError) as caught:
            get_discovery_manager(DiscoveryConfig(True, VALID_KEY, PUBLIC_URL))
        error = caught.value
        assert existing_discovery_manager() is None
        assert all(args or kwargs for args, kwargs in leaking_private_key.calls)
        formatted = _formatted(error)
        assert VALID_KEY not in formatted
        assert VALID_KEY[:8] not in formatted
        assert VALID_KEY not in caplog.text
        assert VALID_KEY[:8] not in caplog.text
        assert error.__cause__ is None
        assert error.__suppress_context__ is True

    def test_strict_preflight_does_not_fall_back_or_leak(self, leaking_private_key):
        with pytest.raises(DiscoveryUnavailableError) as caught:
            preflight_discovery(DiscoveryConfig(True, VALID_KEY, PUBLIC_URL))
        error = caught.value
        assert existing_discovery_manager() is None
        assert all(args or kwargs for args, kwargs in leaking_private_key.calls)
        formatted = _formatted(error)
        assert VALID_KEY not in formatted
        assert VALID_KEY[:8] not in formatted
        assert error.__cause__ is None
        assert error.__suppress_context__ is True

    def test_startup_aborts_without_scheduling_broadcast(
        self, monkeypatch, leaking_private_key, broadcast_recorder
    ):
        monkeypatch.setattr(main, "discovery_config", DiscoveryConfig(True, VALID_KEY, PUBLIC_URL))
        with pytest.raises(DiscoveryUnavailableError) as caught:
            with TestClient(main.app):
                pass
        error = _unavailable(caught.value)
        assert broadcast_recorder == []
        assert existing_discovery_manager() is None
        formatted = _formatted(caught.value)
        assert VALID_KEY not in formatted
        assert VALID_KEY[:8] not in formatted
        assert error.__cause__ is None
        assert error.__suppress_context__ is True

    @pytest.mark.skipif(not p2p_discovery.NOSTR_AVAILABLE, reason="nostr library unavailable")
    def test_mismatched_constructed_identity_is_rejected(self, monkeypatch):
        """A manager that built *an* identity, just not the configured one, must
        not become the process singleton."""
        other = "22" * 32

        class WrongIdentity:
            def __init__(self, *args, **kwargs):
                self.private_key = MagicMock()
                self.private_key.raw_secret.hex.return_value = other
                self.public_key = MagicMock()
                self.public_key.hex.return_value = "33" * 32

        monkeypatch.setattr(p2p_discovery, "EnhancedNostrDiscovery", WrongIdentity)
        with pytest.raises(DiscoveryUnavailableError, match="does not match"):
            get_discovery_manager(DiscoveryConfig(True, VALID_KEY, PUBLIC_URL))
        assert existing_discovery_manager() is None

    @pytest.mark.skipif(not p2p_discovery.NOSTR_AVAILABLE, reason="nostr library unavailable")
    def test_direct_construction_still_falls_back_by_default(self):
        """The reusable class keeps its documented ephemeral default. The
        production accessor is what opts out — not this constructor."""
        discovery = p2p_discovery.EnhancedNostrDiscovery("not-a-valid-hex-string")
        assert len(discovery.public_key.hex()) == 64
        assert discovery.private_key.raw_secret.hex() != VALID_KEY


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test")


class TestRegistryWhileDisabled:
    async def test_list_reports_disabled_and_creates_nothing(self, client, identity_tripwire):
        async with client as c:
            r = await c.get("/agents/registry")
        assert r.status_code == 200
        body = r.json()
        assert (body["count"], body["total"], body["agents"]) == (0, 0, [])
        assert body["source"] == "disabled"
        assert existing_discovery_manager() is None
        identity_tripwire.assert_not_called()

    async def test_lookup_returns_404_without_creating_anything(self, client, identity_tripwire):
        async with client as c:
            r = await c.get("/agents/registry/bitagent-search")
        assert r.status_code == 404
        assert existing_discovery_manager() is None
        identity_tripwire.assert_not_called()

    async def test_source_is_local_once_discovery_is_enabled(self, monkeypatch, client):
        """The label follows the flag, not the presence of a manager, which is
        briefly absent while an enabled node is still starting up."""
        monkeypatch.setenv("NOSTR_DISCOVERY_ENABLED", "true")
        with patch(_REGISTRY_MGR, return_value=None):
            async with client as c:
                r = await c.get("/agents/registry")
        assert r.json()["source"] == "local"
