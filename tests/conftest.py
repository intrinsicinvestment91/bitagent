"""Shared test fixtures.

The payment core is exercised against a fake LNbits rather than mocks of our own
code: the fake implements the same ``AsyncLNbitsClient`` surface, so tests run
the real gate, the real ledger and the real SQL, with no network.
"""

from __future__ import annotations

import os
import secrets

import pytest

# Tests never talk to a real wallet. Set this before anything imports the
# payment config, which refuses to load when LNbits is absent and payments are
# not explicitly disabled.
os.environ.setdefault("PAYMENTS_ENABLED", "false")

# Rate limiting is per-process and keyed by client address, so every test shares
# one bucket and later tests would be throttled by earlier ones. It has its own
# dedicated tests; keep it off everywhere else.
os.environ.setdefault("RATE_LIMIT", "false")

from src.payments.config import PaymentConfig  # noqa: E402
from src.payments.gate import PaymentGate, configure_gate, reset_gate  # noqa: E402
from src.payments.ledger import PaymentLedger  # noqa: E402
from src.payments.lnbits import Invoice, PaymentRecord, PaymentState  # noqa: E402


class FakeLNbits:
    """In-memory stand-in for AsyncLNbitsClient.

    Mirrors the real client's contract, including the three-state payment lookup
    that lets the gate fail closed.
    """

    def __init__(self):
        self.invoices: dict[str, Invoice] = {}
        self.paid: set[str] = set()
        #: Set to simulate an LNbits outage: lookups return UNKNOWN.
        self.unreachable = False
        #: Set to simulate invoice minting failing.
        self.invoice_error: Exception | None = None
        #: Override the amount LNbits reports, in sats.
        self.reported_amount: int | None = None
        #: Report records as outgoing payments.
        self.outgoing = False
        self.balance_sats = 100_000

    async def create_invoice(self, amount_sats: int, memo: str) -> Invoice:
        if self.invoice_error is not None:
            raise self.invoice_error
        payment_hash = secrets.token_hex(32)
        invoice = Invoice(payment_hash, f"lnbc{amount_sats}n1fake{payment_hash[:8]}", amount_sats)
        self.invoices[payment_hash] = invoice
        return invoice

    async def get_payment(self, payment_hash: str) -> PaymentRecord:
        if self.unreachable:
            return PaymentRecord(PaymentState.UNKNOWN)
        if payment_hash not in self.paid:
            return PaymentRecord(PaymentState.UNPAID)
        invoice = self.invoices.get(payment_hash)
        amount = self.reported_amount
        if amount is None:
            amount = invoice.amount_sats if invoice else 0
        return PaymentRecord(
            PaymentState.PAID, amount_sats=amount, incoming=not self.outgoing
        )

    async def get_balance_sats(self) -> int:
        return self.balance_sats

    async def aclose(self) -> None:
        return None

    # --- helpers for tests -------------------------------------------------

    def settle(self, payment_hash: str) -> None:
        """Mark an invoice as paid, as if a client had paid it."""
        self.paid.add(payment_hash)

    def settle_all(self) -> None:
        self.paid.update(self.invoices)


class DisabledFedimint:
    enabled = False

    async def verify_and_receive(self, notes, price):  # pragma: no cover - never called
        return False


@pytest.fixture
def ledger(tmp_path) -> PaymentLedger:
    return PaymentLedger(tmp_path / "payments.db")


@pytest.fixture
def fake_lnbits() -> FakeLNbits:
    return FakeLNbits()


@pytest.fixture
def paid_gate(ledger, fake_lnbits) -> PaymentGate:
    """A gate with payments enforced, backed by the fake LNbits."""
    config = PaymentConfig(
        enabled=True,
        lnbits_url="https://lnbits.test",
        lnbits_api_key="test-key",
        invoice_ttl_seconds=3600,
    )
    gate = PaymentGate(config, ledger, fake_lnbits, DisabledFedimint())
    configure_gate(gate)
    yield gate
    reset_gate()


@pytest.fixture
def free_gate(ledger) -> PaymentGate:
    """A gate in explicit free mode (PAYMENTS_ENABLED=false)."""
    config = PaymentConfig(
        enabled=False, lnbits_url=None, lnbits_api_key=None, invoice_ttl_seconds=3600
    )
    gate = PaymentGate(config, ledger, None, DisabledFedimint())
    configure_gate(gate)
    yield gate
    reset_gate()


@pytest.fixture
async def pay_for(paid_gate, fake_lnbits):
    """Return a helper that runs the full quote → pay → redeem handshake."""

    async def _pay_for(service_id: str) -> str:
        quote = await paid_gate.require_payment(service_id)
        payment_hash = quote.body["payment_hash"]
        fake_lnbits.settle(payment_hash)
        return payment_hash

    return _pay_for
