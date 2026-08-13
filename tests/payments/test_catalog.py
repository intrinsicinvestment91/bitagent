"""Catalog invariants.

The catalog is the single source of truth for prices. These tests pin the two
properties that keep it honest.
"""

import pytest

from src.payments.catalog import SERVICES, Service, UnknownServiceError, get_service, pricing_for


class TestHonestyInvariant:
    def test_no_service_charges_for_synthetic_output(self):
        """A service returning placeholder data must be free.

        This is the invariant that stops the original bug class from returning:
        streamfinder charged 100 sats for a three-title hardcoded dict, and
        transcription charged 250 sats to answer "[MOCK TRANSCRIPTION]".
        """
        for service_id, service in SERVICES.items():
            if service.synthetic:
                assert service.price_sats == 0, f"{service_id} is synthetic but priced"

    def test_constructing_a_priced_synthetic_service_is_rejected(self):
        with pytest.raises(ValueError, match="must not be charged for"):
            Service("demo.thing", "A demo", price_sats=100, synthetic=True)

    def test_negative_prices_are_rejected(self):
        with pytest.raises(ValueError, match="negative"):
            Service("bad.thing", "Bad", price_sats=-1)

    def test_an_unavailable_backend_is_not_billed_for(self):
        service = Service("x.y", "X", price_sats=250, is_available=lambda: False)

        assert service.effective_price == 0
        assert service.available is False


class TestLookup:
    def test_unknown_service_raises(self):
        with pytest.raises(UnknownServiceError):
            get_service("nope.nothing")

    def test_pricing_for_a_prefix_returns_its_services(self):
        oracle = pricing_for("oracle")

        assert set(oracle) == {"oracle.price", "oracle.prices", "oracle.convert"}
        assert oracle["oracle.price"] == 2

    def test_every_service_id_is_dotted_and_matches_its_key(self):
        for service_id, service in SERVICES.items():
            assert service.id == service_id
            assert "." in service_id, f"{service_id} must be namespaced as <agent>.<method>"

    def test_synthetic_services_declare_themselves_in_info(self):
        info = get_service("streamfinder.search").info()

        assert info["synthetic"] is True
        assert info["price_sats"] == 0
        assert "notice" in info
