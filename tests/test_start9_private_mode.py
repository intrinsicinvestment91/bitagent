"""The StartOS package must stay private-first.

These are text-level guards on the package files rather than a packaging test:
they cannot prove how StartOS renders a config value (that needs an install), but
they do fail if the Tor interface, a wildcard CORS origin, or a payments-on
default comes back. scripts/embassy.js is the bundle StartOS actually executes,
so it is checked for the new fields too — editing the TypeScript alone has no
effect until the bundle is regenerated.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

PASSED_THROUGH = (
    "PAYMENTS_ENABLED",
    "NOSTR_DISCOVERY_ENABLED",
    "LNBITS_URL",
    "LNBITS_API_KEY",
    "NOSTR_PRIVATE_KEY",
    "PUBLIC_URL",
)

CONFIG_FIELDS = (
    "payments_enabled",
    "nostr_discovery_enabled",
    "lnbits_url",
    "lnbits_api_key",
    "nostr_private_key",
    "public_url",
)


@pytest.fixture(scope="module")
def manifest() -> str:
    return (REPO_ROOT / "manifest.yaml").read_text()


@pytest.fixture(scope="module")
def get_config_ts() -> str:
    return (REPO_ROOT / "scripts" / "procedures" / "getConfig.ts").read_text()


@pytest.fixture(scope="module")
def bundle() -> str:
    return (REPO_ROOT / "scripts" / "embassy.js").read_text()


class TestManifest:
    @pytest.mark.parametrize("name", PASSED_THROUGH)
    def test_environment_passes_the_setting_through(self, manifest, name):
        assert f"{name}: " in manifest

    @pytest.mark.parametrize("name", ("payments_enabled", "nostr_discovery_enabled", "public_url"))
    def test_setting_comes_from_config(self, manifest, name):
        assert f"{{{{ config.{name} }}}}" in manifest

    def test_no_tor_interface(self, manifest):
        keys = {line.strip().rstrip(":") for line in manifest.splitlines()}
        assert "tor-config" not in keys

    def test_lan_interface_kept(self, manifest):
        keys = {line.strip().rstrip(":") for line in manifest.splitlines()}
        assert "lan-config" in keys

    def test_no_wildcard_cors_origin(self, manifest):
        assert 'ALLOWED_ORIGINS: "*"' not in manifest
        assert 'ALLOWED_ORIGINS: ""' in manifest


class TestConfigSpec:
    @pytest.mark.parametrize("field", CONFIG_FIELDS)
    def test_field_is_declared(self, get_config_ts, field):
        assert f'"{field}"' in get_config_ts

    @pytest.mark.parametrize("field", ("payments_enabled", "nostr_discovery_enabled"))
    def test_boolean_defaults_to_false(self, get_config_ts, field):
        block = get_config_ts.split(f'"{field}"', 1)[1].split("},", 1)[0]
        assert '"type": "boolean"' in block
        assert '"default": false' in block

    @pytest.mark.parametrize(
        "field", ("lnbits_url", "lnbits_api_key", "nostr_private_key", "public_url")
    )
    def test_optional_fields_are_nullable_with_no_default(self, get_config_ts, field):
        """Absence, not a placeholder: the compatibility type has no null default,
        and an empty string would be a value rather than nothing."""
        block = get_config_ts.split(f'"{field}"', 1)[1].split("},", 1)[0]
        assert '"nullable": true' in block
        assert '"default"' not in block

    @pytest.mark.parametrize("field", ("lnbits_api_key", "nostr_private_key"))
    def test_secrets_are_masked(self, get_config_ts, field):
        block = get_config_ts.split(f'"{field}"', 1)[1].split("},", 1)[0]
        assert '"masked": true' in block

    def test_nostr_key_no_longer_claims_to_disable_discovery(self, get_config_ts):
        block = get_config_ts.split('"nostr_private_key"', 1)[1].split("},", 1)[0]
        assert "Leave empty to disable" not in block
        assert "discovery is enabled" in block


class TestBundleIsCurrent:
    """The .ts files are source; embassy.js is what runs."""

    @pytest.mark.parametrize("field", CONFIG_FIELDS)
    def test_bundle_contains_the_field(self, bundle, field):
        assert f'"{field}"' in bundle
