"""Public discovery is off unless explicitly and completely configured.

Every case here resolves configuration only; nothing in this file opens a socket,
and no key used below belongs to anything.
"""

import logging

import pytest

from src.network.discovery_config import (
    SECP256K1_ORDER,
    DiscoveryConfig,
    DiscoveryConfigError,
    discovery_enabled,
    load_discovery_config,
    validate_discovery_config,
)

# A valid secp256k1 scalar written as 64 hex characters. Structurally usable,
# deliberately not a secret anyone holds.
VALID_KEY = "11" * 32
PUBLIC_URL = "https://agent.example.test"
CURVE_ORDER_KEY = f"{SECP256K1_ORDER:064x}"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Start every case from an unconfigured environment.

    monkeypatch reverts all of this at teardown, so no case can decide what a
    later one sees.
    """
    for name in (
        "NOSTR_DISCOVERY_ENABLED",
        "NOSTR_PRIVATE_KEY",
        "PUBLIC_URL",
        "RAILWAY_PUBLIC_DOMAIN",
    ):
        monkeypatch.delenv(name, raising=False)


def _enable(monkeypatch, **env: str) -> None:
    monkeypatch.setenv("NOSTR_DISCOVERY_ENABLED", "true")
    for name, value in env.items():
        monkeypatch.setenv(name, value)


# ---------------------------------------------------------------------------
# The flag itself
# ---------------------------------------------------------------------------


class TestFlag:
    def test_unset_is_disabled(self):
        assert discovery_enabled() is False
        config = load_discovery_config()
        assert config.enabled is False
        assert config.nostr_private_key is None
        assert config.public_url is None

    @pytest.mark.parametrize("value", ["false", "FALSE", "0", "no", "off", "", "   "])
    def test_explicit_false_values_are_disabled(self, monkeypatch, value):
        monkeypatch.setenv("NOSTR_DISCOVERY_ENABLED", value)
        assert discovery_enabled() is False

    @pytest.mark.parametrize("value", ["true", "TRUE", "True", "1", "yes", "on"])
    def test_recognised_true_values_enable(self, monkeypatch, value):
        monkeypatch.setenv("NOSTR_DISCOVERY_ENABLED", value)
        assert discovery_enabled() is True

    @pytest.mark.parametrize("value", ["maybe", "enabled", "y", "truthy", "2", "tru"])
    def test_unrecognised_value_fails_closed(self, monkeypatch, caplog, value):
        """A typo must not be the thing that puts a node on public relays."""
        monkeypatch.setenv("NOSTR_DISCOVERY_ENABLED", value)
        with caplog.at_level(logging.WARNING, logger="src.network.discovery_config"):
            assert discovery_enabled() is False
        assert "not a recognised boolean" in caplog.text

    def test_disabled_ignores_a_configured_key(self, monkeypatch):
        """Disabled reads nothing else: a leftover key does not re-enable it."""
        monkeypatch.setenv("NOSTR_DISCOVERY_ENABLED", "false")
        monkeypatch.setenv("NOSTR_PRIVATE_KEY", VALID_KEY)
        monkeypatch.setenv("PUBLIC_URL", PUBLIC_URL)
        config = load_discovery_config()
        assert config.enabled is False
        assert config.nostr_private_key is None


# ---------------------------------------------------------------------------
# Enabled mode: the key
# ---------------------------------------------------------------------------


class TestEnabledKey:
    @pytest.mark.parametrize("key", [None, "", "   ", "\n\t"])
    def test_missing_or_blank_key_fails_closed(self, monkeypatch, key):
        _enable(monkeypatch, PUBLIC_URL=PUBLIC_URL)
        if key is not None:
            monkeypatch.setenv("NOSTR_PRIVATE_KEY", key)
        with pytest.raises(DiscoveryConfigError, match="NOSTR_PRIVATE_KEY is not set"):
            load_discovery_config()

    @pytest.mark.parametrize(
        "key",
        [
            "ff" * 31,  # 31 bytes
            "ff" * 33,  # 33 bytes
            "abc",  # odd length
            "zz" * 32,  # right length, not hex
            "11" * 16 + " " + "11" * 15,  # embedded space
            "11" * 16 + "\t" + "11" * 15,  # embedded tab
            "11" * 16 + "\n" + "11" * 15,  # embedded newline
            "11 " * 32,  # spaced byte pairs, as bytes.fromhex would have accepted
        ],
    )
    def test_malformed_key_fails_closed(self, monkeypatch, key):
        _enable(monkeypatch, NOSTR_PRIVATE_KEY=key, PUBLIC_URL=PUBLIC_URL)
        with pytest.raises(DiscoveryConfigError, match="hexadecimal characters"):
            load_discovery_config()

    @pytest.mark.parametrize(
        ("label", "key"),
        [
            ("all zero", "00" * 32),
            ("the curve order itself", CURVE_ORDER_KEY),
            ("one above the order", f"{SECP256K1_ORDER + 1:064x}"),
            ("all ones", "ff" * 32),
        ],
    )
    def test_key_outside_the_curve_order_fails_closed(self, monkeypatch, label, key):
        """64 hex characters is not enough: the value has to be a usable scalar."""
        _enable(monkeypatch, NOSTR_PRIVATE_KEY=key, PUBLIC_URL=PUBLIC_URL)
        with pytest.raises(DiscoveryConfigError, match="curve order") as exc_info:
            load_discovery_config()
        assert key not in str(exc_info.value), label

    def test_one_below_the_order_is_accepted(self, monkeypatch):
        key = f"{SECP256K1_ORDER - 1:064x}"
        _enable(monkeypatch, NOSTR_PRIVATE_KEY=key, PUBLIC_URL=PUBLIC_URL)
        assert load_discovery_config().nostr_private_key == key

    def test_uppercase_key_is_normalised_to_lowercase(self, monkeypatch):
        _enable(monkeypatch, NOSTR_PRIVATE_KEY="AB" * 32, PUBLIC_URL=PUBLIC_URL)
        assert load_discovery_config().nostr_private_key == "ab" * 32

    @pytest.mark.parametrize(
        "key",
        [
            "ff" * 31,
            "zz" * 32,
            "dead" * 16 + "beef",
            "00" * 32,
            "ff" * 32,
            CURVE_ORDER_KEY,
            "11" * 16 + " " + "11" * 15,
        ],
    )
    def test_error_and_logs_never_contain_key_material(self, monkeypatch, caplog, key):
        _enable(monkeypatch, NOSTR_PRIVATE_KEY=key, PUBLIC_URL=PUBLIC_URL)
        with caplog.at_level(logging.DEBUG), pytest.raises(DiscoveryConfigError) as exc_info:
            load_discovery_config()
        message = str(exc_info.value)
        assert key not in message
        assert key not in caplog.text
        # Nor any leading fragment of it, which a hex-parse error would quote.
        assert key[:8] not in message
        assert key[:8] not in caplog.text

    def test_valid_key_is_accepted_and_stripped(self, monkeypatch):
        _enable(monkeypatch, NOSTR_PRIVATE_KEY=f"  {VALID_KEY}\n", PUBLIC_URL=PUBLIC_URL)
        assert load_discovery_config().nostr_private_key == VALID_KEY


# ---------------------------------------------------------------------------
# Enabled mode: the public URL
# ---------------------------------------------------------------------------


class TestEnabledPublicUrl:
    @pytest.mark.parametrize("url", [None, "", "   ", "/", "///"])
    def test_missing_or_empty_public_url_fails_closed(self, monkeypatch, url):
        _enable(monkeypatch, NOSTR_PRIVATE_KEY=VALID_KEY)
        if url is not None:
            monkeypatch.setenv("PUBLIC_URL", url)
        with pytest.raises(DiscoveryConfigError, match="PUBLIC_URL is not set"):
            load_discovery_config()

    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost:8000",
            "https://localhost",
            "http://localhost.:8000",  # trailing dot is still localhost
            "http://node.localhost:8000",
            "http://LOCALHOST:8000",
            "http://127.0.0.1:8000",
            "http://127.0.0.5:8000",  # the whole loopback range, not one address
            "http://0.0.0.0:8000",
            "http://[::1]:8000",
            "http://[::]:8000",
        ],
    )
    def test_unroutable_public_url_fails_closed(self, monkeypatch, url):
        _enable(monkeypatch, NOSTR_PRIVATE_KEY=VALID_KEY, PUBLIC_URL=url)
        with pytest.raises(DiscoveryConfigError, match="only on this machine"):
            load_discovery_config()

    @pytest.mark.parametrize(
        "url",
        [
            "agent.example.test",
            "ftp://agent.example.test",
            "://x",
            "https://agent.example.test:port",  # non-numeric port
            "https://agent.example.test:99999",  # out of range
            "https://agent.example.test:-1",
            "https://",
        ],
    )
    def test_malformed_public_url_fails_closed(self, monkeypatch, url):
        _enable(monkeypatch, NOSTR_PRIVATE_KEY=VALID_KEY, PUBLIC_URL=url)
        with pytest.raises(DiscoveryConfigError, match="absolute http"):
            load_discovery_config()

    @pytest.mark.parametrize(
        "url",
        [
            "https://operator:s3cret@agent.example.test",
            "https://operator@agent.example.test",
            "https://:s3cret@agent.example.test",
        ],
    )
    def test_embedded_credentials_fail_closed_without_echoing_them(self, monkeypatch, caplog, url):
        _enable(monkeypatch, NOSTR_PRIVATE_KEY=VALID_KEY, PUBLIC_URL=url)
        with caplog.at_level(logging.DEBUG), pytest.raises(DiscoveryConfigError) as exc_info:
            load_discovery_config()
        message = str(exc_info.value)
        assert "username or password" in message
        for leak in ("s3cret", "operator", url):
            assert leak not in message
            assert leak not in caplog.text

    @pytest.mark.parametrize(
        "url",
        [
            f"{PUBLIC_URL}?token=abc123",
            f"{PUBLIC_URL}/agents?token=abc123",
            f"{PUBLIC_URL}#anchor",
            f"{PUBLIC_URL}/agents#anchor",
        ],
    )
    def test_query_or_fragment_fails_closed_without_echoing_it(self, monkeypatch, caplog, url):
        _enable(monkeypatch, NOSTR_PRIVATE_KEY=VALID_KEY, PUBLIC_URL=url)
        with caplog.at_level(logging.DEBUG), pytest.raises(DiscoveryConfigError) as exc_info:
            load_discovery_config()
        message = str(exc_info.value)
        assert "query string or fragment" in message
        for leak in ("abc123", "anchor", url):
            assert leak not in message
            assert leak not in caplog.text

    @pytest.mark.parametrize(
        "url",
        [
            f"{PUBLIC_URL}:8443",
            f"{PUBLIC_URL}/bitagent",
            f"{PUBLIC_URL}:8443/bitagent",
            "http://203.0.113.10:8000",
            "https://agent.example.test.",  # fully qualified, still routable
        ],
    )
    def test_ports_and_path_prefixes_are_accepted(self, monkeypatch, url):
        """Endpoints are built by appending to this value, so a path prefix is fine."""
        _enable(monkeypatch, NOSTR_PRIVATE_KEY=VALID_KEY, PUBLIC_URL=url)
        assert load_discovery_config().public_url == url

    @pytest.mark.parametrize(
        ("configured", "expected"),
        [
            (f"{PUBLIC_URL}/", PUBLIC_URL),
            (f"{PUBLIC_URL}///", PUBLIC_URL),
            (f"  {PUBLIC_URL}/  ", PUBLIC_URL),
            (PUBLIC_URL, PUBLIC_URL),
        ],
    )
    def test_trailing_slashes_normalised(self, monkeypatch, configured, expected):
        """Agent endpoints are built as f"{public_url}/search"; a kept slash
        would announce '…//search'."""
        _enable(monkeypatch, NOSTR_PRIVATE_KEY=VALID_KEY, PUBLIC_URL=configured)
        config = load_discovery_config()
        assert config.public_url == expected
        assert f"{config.public_url}/search" == f"{PUBLIC_URL}/search"

    def test_railway_domain_used_when_public_url_absent(self, monkeypatch):
        _enable(monkeypatch, NOSTR_PRIVATE_KEY=VALID_KEY)
        monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "bitagent.up.railway.test")
        assert load_discovery_config().public_url == "https://bitagent.up.railway.test"

    def test_public_url_wins_over_the_railway_domain(self, monkeypatch):
        """An operator who sets PUBLIC_URL means it."""
        _enable(monkeypatch, NOSTR_PRIVATE_KEY=VALID_KEY, PUBLIC_URL=PUBLIC_URL)
        monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "bitagent.up.railway.test")
        assert load_discovery_config().public_url == PUBLIC_URL

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_public_url_falls_back_to_the_railway_domain(self, monkeypatch, blank):
        _enable(monkeypatch, NOSTR_PRIVATE_KEY=VALID_KEY, PUBLIC_URL=blank)
        monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "bitagent.up.railway.test")
        assert load_discovery_config().public_url == "https://bitagent.up.railway.test"

    def test_fully_configured_loads(self, monkeypatch):
        _enable(monkeypatch, NOSTR_PRIVATE_KEY=VALID_KEY, PUBLIC_URL=PUBLIC_URL)
        config = load_discovery_config()
        assert (config.enabled, config.nostr_private_key, config.public_url) == (
            True,
            VALID_KEY,
            PUBLIC_URL,
        )
        assert config.describe() == "enabled"


# ---------------------------------------------------------------------------
# The single validator, applied to a config somebody built by hand
# ---------------------------------------------------------------------------


class TestValidateDirectlyConstructedConfig:
    """A DiscoveryConfig from a caller gets the same treatment as one from the
    environment — this is the gate the manager accessor relies on."""

    @pytest.mark.parametrize(
        "config",
        [
            DiscoveryConfig(False, None, None),
            DiscoveryConfig(False, VALID_KEY, PUBLIC_URL),
            DiscoveryConfig(False, "not a key", "http://localhost:8000"),
        ],
    )
    def test_disabled_normalises_to_nothing_configured(self, config):
        assert validate_discovery_config(config) == DiscoveryConfig(False, None, None)

    @pytest.mark.parametrize(
        ("label", "config"),
        [
            ("no key", DiscoveryConfig(True, None, PUBLIC_URL)),
            ("short key", DiscoveryConfig(True, "ff" * 31, PUBLIC_URL)),
            ("out-of-range key", DiscoveryConfig(True, "ff" * 32, PUBLIC_URL)),
            ("loopback url", DiscoveryConfig(True, VALID_KEY, "http://localhost:8000")),
            ("no url", DiscoveryConfig(True, VALID_KEY, None)),
            ("credentials in url", DiscoveryConfig(True, VALID_KEY, "https://u:p@a.example.test")),
        ],
    )
    def test_enabled_is_revalidated(self, label, config):
        with pytest.raises(DiscoveryConfigError):
            validate_discovery_config(config)

    def test_enabled_and_valid_is_normalised(self):
        config = validate_discovery_config(
            DiscoveryConfig(True, f" {VALID_KEY.upper()} ", f"{PUBLIC_URL}/")
        )
        assert config == DiscoveryConfig(True, VALID_KEY, PUBLIC_URL)
