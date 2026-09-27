"""Free mode must start without a wallet; enabled mode must not start without one.

This is the property the StartOS package depends on: it ships with
PAYMENTS_ENABLED=false and no LNbits fields filled in. None of these cases
contacts a wallet, and none of them uses a real credential.
"""

import pytest
from fastapi.testclient import TestClient

import main
from src.payments.config import PaymentConfigError, load_config


@pytest.fixture(autouse=True)
def no_wallet_env(monkeypatch):
    """No LNbits values, whatever the surrounding environment happens to hold."""
    monkeypatch.delenv("LNBITS_URL", raising=False)
    monkeypatch.delenv("LNBITS_API_KEY", raising=False)


class TestFreeMode:
    def test_loads_without_lnbits_credentials(self, monkeypatch):
        monkeypatch.setenv("PAYMENTS_ENABLED", "false")
        config = load_config()
        assert config.enabled is False
        assert config.lnbits_configured is False
        assert config.describe() == "disabled"

    def test_app_serves_health_in_free_mode(self):
        """PAYMENTS_ENABLED=false is set for the whole suite, so this is the
        package's default posture booting end to end."""
        with TestClient(main.app) as client:
            response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["payments"] == "disabled"
        assert "free" in body["notice"]


class TestEnabledModeFailsClosed:
    def test_enabled_without_any_credentials_refuses(self, monkeypatch):
        monkeypatch.setenv("PAYMENTS_ENABLED", "true")
        with pytest.raises(PaymentConfigError) as exc_info:
            load_config()
        message = str(exc_info.value)
        assert "LNBITS_URL" in message and "LNBITS_API_KEY" in message

    def test_enabled_with_only_a_url_refuses(self, monkeypatch):
        monkeypatch.setenv("PAYMENTS_ENABLED", "true")
        monkeypatch.setenv("LNBITS_URL", "http://lnbits.invalid")
        with pytest.raises(PaymentConfigError, match="LNBITS_API_KEY"):
            load_config()

    def test_unset_flag_without_credentials_refuses(self, monkeypatch):
        """Silence is not consent to free service."""
        monkeypatch.delenv("PAYMENTS_ENABLED", raising=False)
        with pytest.raises(PaymentConfigError):
            load_config()
