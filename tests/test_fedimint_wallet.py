"""FedimintWallet tests.

The previous version of this file tested an in-memory token API
(``FedimintWallet(wallet_id=...)``, ``receive_tokens(dict)``) that no longer
exists — the wallet is an HTTP client for fedimint-clientd. These exercise the
real client against a fake transport.
"""

import httpx
import pytest

from src.wallets.fedimint_wallet import FedimintWallet

PRICE_SATS = 100


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("FEDIMINT_CLIENTD_URL", "http://fedimint.test")
    monkeypatch.setenv("FEDIMINT_CLIENTD_PASSWORD", "secret")


def _wallet(handler) -> FedimintWallet:
    return FedimintWallet(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


class TestDisabledByDefault:
    def test_not_enabled_without_configuration(self, monkeypatch):
        monkeypatch.delenv("FEDIMINT_CLIENTD_URL", raising=False)
        monkeypatch.delenv("FEDIMINT_CLIENTD_PASSWORD", raising=False)

        assert FedimintWallet().enabled is False

    async def test_all_operations_are_inert_when_disabled(self, monkeypatch):
        monkeypatch.delenv("FEDIMINT_CLIENTD_URL", raising=False)
        wallet = FedimintWallet()

        assert await wallet.validate_notes("notes") is None
        assert await wallet.receive_notes("notes") is None
        assert await wallet.get_balance_sats() is None
        assert await wallet.verify_and_receive("notes", PRICE_SATS) is False


class TestSettlement:
    async def test_sufficient_notes_are_validated_then_redeemed(self, configured):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            return httpx.Response(200, json={"amount_msat": PRICE_SATS * 1000})

        assert await _wallet(handler).verify_and_receive("notes", PRICE_SATS) is True
        # Validate is non-destructive; reissue is what actually burns the notes.
        assert calls == ["/v2/mint/validate", "/v2/mint/reissue"]

    async def test_underpaying_notes_are_refused_without_redeeming(self, configured):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            return httpx.Response(200, json={"amount_msat": 1_000})

        assert await _wallet(handler).verify_and_receive("notes", PRICE_SATS) is False
        assert "/v2/mint/reissue" not in calls, "must not redeem notes it then rejects"

    async def test_invalid_notes_are_refused(self, configured):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": "invalid notes"})

        assert await _wallet(handler).verify_and_receive("notes", PRICE_SATS) is False

    async def test_a_failed_reissue_does_not_settle(self, configured):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("validate"):
                return httpx.Response(200, json={"amount_msat": PRICE_SATS * 1000})
            return httpx.Response(500, json={"error": "already spent"})

        assert await _wallet(handler).verify_and_receive("notes", PRICE_SATS) is False

    async def test_a_transport_failure_does_not_settle(self, configured):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("federation unreachable")

        assert await _wallet(handler).verify_and_receive("notes", PRICE_SATS) is False


class TestBalance:
    async def test_balance_is_converted_from_msats(self, configured):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"total_amount_msat": 12_345_000})

        assert await _wallet(handler).get_balance_sats() == 12_345
