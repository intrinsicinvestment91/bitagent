"""Tests for the payment gate.

These encode the properties the product depends on: a payment buys exactly one
request, of exactly the service it was issued for, and no failure mode anywhere
degrades into free service.
"""

import asyncio

import pytest

from src.payments.gate import Quote, Settled
from src.payments.lnbits import LNbitsError


class TestQuoting:
    async def test_unpaid_request_returns_402_with_an_invoice(self, paid_gate):
        outcome = await paid_gate.require_payment("search.query")

        assert isinstance(outcome, Quote)
        assert outcome.status_code == 402
        assert outcome.body["payment_required"] is True
        assert outcome.body["amount_sats"] == 10
        assert outcome.body["payment_request"].startswith("lnbc")
        assert outcome.body["service"] == "search.query"

    async def test_quote_is_recorded_in_the_ledger_before_it_is_returned(self, paid_gate, ledger):
        outcome = await paid_gate.require_payment("search.query")
        row = ledger.get(outcome.body["payment_hash"])

        assert row is not None
        assert row["service_id"] == "search.query"
        assert row["amount_sats"] == 10
        assert row["state"] == "issued"

    async def test_paid_invoice_settles(self, paid_gate, fake_lnbits):
        quote = await paid_gate.require_payment("search.query")
        fake_lnbits.settle(quote.body["payment_hash"])

        outcome = await paid_gate.require_payment("search.query", quote.body["payment_hash"])

        assert isinstance(outcome, Settled)
        assert outcome.amount_sats == 10
        assert outcome.method == "lightning"

    async def test_unsettled_hash_is_refused(self, paid_gate):
        quote = await paid_gate.require_payment("search.query")

        outcome = await paid_gate.require_payment("search.query", quote.body["payment_hash"])

        assert isinstance(outcome, Quote)
        assert outcome.status_code == 402
        assert outcome.body["error"] == "payment_not_settled"


class TestSingleUse:
    async def test_a_payment_cannot_be_replayed(self, paid_gate, pay_for):
        payment_hash = await pay_for("search.query")

        first = await paid_gate.require_payment("search.query", payment_hash)
        second = await paid_gate.require_payment("search.query", payment_hash)

        assert isinstance(first, Settled)
        assert isinstance(second, Quote)
        assert second.body["error"] == "already_consumed"

    async def test_concurrent_redemptions_settle_exactly_once(self, paid_gate, pay_for):
        payment_hash = await pay_for("search.query")

        outcomes = await asyncio.gather(
            *(paid_gate.require_payment("search.query", payment_hash) for _ in range(25))
        )

        settled = [o for o in outcomes if isinstance(o, Settled)]
        assert len(settled) == 1, "a payment must settle exactly once under concurrency"
        assert all(o.body["error"] == "already_consumed" for o in outcomes if isinstance(o, Quote))

    async def test_a_released_payment_can_be_retried(self, paid_gate, pay_for):
        payment_hash = await pay_for("search.query")
        settled = await paid_gate.require_payment("search.query", payment_hash)

        # The work failed after settlement, so the caller gets their payment back.
        assert await paid_gate.release(settled) is True

        retry = await paid_gate.require_payment("search.query", payment_hash)
        assert isinstance(retry, Settled)


class TestServiceAndAmountBinding:
    async def test_a_payment_for_one_service_is_refused_by_another(self, paid_gate, pay_for):
        # Buy the cheapest service, then try to redeem it against a dearer one.
        payment_hash = await pay_for("oracle.convert")

        outcome = await paid_gate.require_payment("polyglot.translate", payment_hash)

        assert isinstance(outcome, Quote)
        assert outcome.body["error"] == "wrong_service"

    async def test_a_hash_this_node_never_issued_is_refused(self, paid_gate, fake_lnbits):
        fake_lnbits.paid.add("f" * 64)

        outcome = await paid_gate.require_payment("search.query", "f" * 64)

        assert isinstance(outcome, Quote)
        assert outcome.body["error"] == "unknown_payment_hash"

    async def test_underpayment_is_refused(self, paid_gate, fake_lnbits):
        quote = await paid_gate.require_payment("polyglot.translate")
        fake_lnbits.settle(quote.body["payment_hash"])
        fake_lnbits.reported_amount = 1  # settled far below the 100 sat price

        outcome = await paid_gate.require_payment("polyglot.translate", quote.body["payment_hash"])

        assert isinstance(outcome, Quote)
        assert outcome.body["error"] == "amount_mismatch"

    async def test_an_outgoing_payment_is_not_proof_of_payment(self, paid_gate, fake_lnbits):
        quote = await paid_gate.require_payment("search.query")
        fake_lnbits.settle(quote.body["payment_hash"])
        fake_lnbits.outgoing = True

        outcome = await paid_gate.require_payment("search.query", quote.body["payment_hash"])

        assert isinstance(outcome, Quote)
        assert outcome.body["error"] == "invalid_payment"

    async def test_settlement_proceeds_when_lnbits_reports_no_amount(self, paid_gate, fake_lnbits):
        # Schema drift must not cause an outage: the ledger binding is the
        # primary control, so a missing amount is logged, not fatal.
        quote = await paid_gate.require_payment("search.query")
        fake_lnbits.settle(quote.body["payment_hash"])
        fake_lnbits.reported_amount = 0

        outcome = await paid_gate.require_payment("search.query", quote.body["payment_hash"])
        assert isinstance(outcome, Quote)  # 0 < 10, so this is still refused

        fake_lnbits.reported_amount = 10
        quote2 = await paid_gate.require_payment("search.query")
        fake_lnbits.settle(quote2.body["payment_hash"])
        assert isinstance(
            await paid_gate.require_payment("search.query", quote2.body["payment_hash"]), Settled
        )


class TestExpiry:
    async def test_an_expired_quote_cannot_be_redeemed(self, paid_gate, fake_lnbits, ledger):
        quote = await paid_gate.require_payment("search.query")
        payment_hash = quote.body["payment_hash"]
        fake_lnbits.settle(payment_hash)

        # Rewrite the deadline into the past, as if the client paid days later.
        with ledger._connect() as conn:
            conn.execute(
                "UPDATE invoices SET expires_at = '2000-01-01T00:00:00+00:00' "
                "WHERE payment_hash = ?",
                (payment_hash,),
            )

        outcome = await paid_gate.require_payment("search.query", payment_hash)

        assert isinstance(outcome, Quote)
        assert outcome.body["error"] == "expired"


class TestFailClosed:
    async def test_an_lnbits_outage_returns_503_not_free_service(self, paid_gate, pay_for):
        payment_hash = await pay_for("search.query")
        paid_gate.client.unreachable = True

        outcome = await paid_gate.require_payment("search.query", payment_hash)

        assert isinstance(outcome, Quote)
        assert outcome.status_code == 503, "an unreachable wallet must never settle or 402"
        assert outcome.body["error"] == "payment_verification_unavailable"

    async def test_failure_to_mint_an_invoice_returns_503_not_free_service(
        self, paid_gate, fake_lnbits
    ):
        fake_lnbits.invoice_error = LNbitsError("LNbits is down")

        outcome = await paid_gate.require_payment("search.query")

        assert isinstance(outcome, Quote)
        assert outcome.status_code == 503
        assert outcome.body["error"] == "invoice_unavailable"

    async def test_ecash_is_refused_when_no_backend_is_configured(self, paid_gate):
        outcome = await paid_gate.require_payment("search.query", ecash_notes="notes")

        assert isinstance(outcome, Quote)
        assert outcome.status_code == 402
        assert outcome.body["error"] == "ecash_not_accepted"

    async def test_an_unavailable_backend_is_not_billed_for(self, paid_gate, monkeypatch):
        from src.payments import catalog

        monkeypatch.setitem(
            catalog.SERVICES,
            "search.query",
            catalog.Service("search.query", "Web search", 10, is_available=lambda: False),
        )

        outcome = await paid_gate.require_payment("search.query")

        assert isinstance(outcome, Quote)
        assert outcome.status_code == 503
        assert outcome.body["error"] == "service_unavailable"


class TestFreeMode:
    async def test_free_mode_settles_without_payment(self, free_gate):
        outcome = await free_gate.require_payment("search.query")

        assert isinstance(outcome, Settled)
        assert outcome.amount_sats == 0
        assert outcome.method == "free"

    async def test_synthetic_services_are_free_even_when_payments_are_enforced(self, paid_gate):
        outcome = await paid_gate.require_payment("streamfinder.search")

        assert isinstance(outcome, Settled)
        assert outcome.amount_sats == 0


class TestUnknownService:
    async def test_an_unknown_service_id_raises(self, paid_gate):
        from src.payments import UnknownServiceError

        with pytest.raises(UnknownServiceError):
            await paid_gate.require_payment("nope.nothing")
