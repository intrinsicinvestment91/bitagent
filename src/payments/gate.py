"""The single payment gate.

Every priced surface — HTTP route, per-agent ``/a2a`` sub-router, and the
top-level A2A dispatcher — goes through ``require_payment``. That is what makes
closing the free-bypass routes structural: a route either calls the gate or it is
not wired to a catalog service at all.

Shaped as a plain helper rather than a decorator on purpose. The two decorator
systems this replaces both failed because they tried to resolve FastAPI
dependencies outside of FastAPI's dependency injection, which raised on every
call. A helper also lets a handler *return* a 402 body instead of only raising,
which the 402-with-invoice flow needs.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from src.payments.catalog import Service, get_service
from src.payments.config import PaymentConfig
from src.payments.ledger import ConsumeResult, PaymentLedger
from src.payments.lnbits import AsyncLNbitsClient, LNbitsError, PaymentState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settled:
    """Payment is complete (or the service is free). Proceed with the work."""

    service: Service
    amount_sats: int = 0
    method: str = "free"
    payment_hash: str | None = None


@dataclass(frozen=True)
class Quote:
    """The request may not proceed. Return this to the client verbatim."""

    status_code: int
    body: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Every 402 body carries this flag, whether it is a fresh invoice or a
        # rejection such as already_consumed. Callers that cannot express an HTTP
        # status — the A2A JSON-RPC envelope, for one — rely on it to tell a
        # payment problem apart from a service result.
        if self.status_code == 402:
            self.body.setdefault("payment_required", True)
        elif self.status_code == 503:
            self.body.setdefault("service_unavailable", True)


PaymentOutcome = Settled | Quote


class PaymentGate:
    def __init__(
        self,
        config: PaymentConfig,
        ledger: PaymentLedger,
        client: AsyncLNbitsClient | None,
        fedimint=None,
    ):
        self.config = config
        self.ledger = ledger
        self.client = client
        self.fedimint = fedimint

    async def require_payment(
        self,
        service_id: str,
        payment_hash: str | None = None,
        ecash_notes: str | None = None,
        memo: str | None = None,
    ) -> PaymentOutcome:
        service = get_service(service_id)
        price = service.effective_price

        if not service.available and not service.synthetic:
            return Quote(
                503,
                {
                    "error": "service_unavailable",
                    "service": service_id,
                    "detail": (
                        "This service's backend is not installed on this node. "
                        "No payment was taken."
                    ),
                },
            )

        # Free services (including every synthetic demo) and explicit free mode.
        if price == 0 or not self.config.enabled:
            return Settled(service, 0, "free")

        if ecash_notes:
            return await self._settle_ecash(service, ecash_notes, price)
        if payment_hash:
            return await self._settle_lightning(service, payment_hash, price)
        return await self._quote(service, price, memo)

    # ---- ecash ------------------------------------------------------------

    async def _settle_ecash(self, service: Service, notes: str, price: int) -> PaymentOutcome:
        if not (self.fedimint and self.fedimint.enabled):
            return Quote(
                402,
                {
                    "error": "ecash_not_accepted",
                    "detail": "This node does not accept ecash. Pay the Lightning invoice instead.",
                },
            )
        try:
            accepted = await self.fedimint.verify_and_receive(notes, price)
        except Exception as exc:
            # Fail closed: an ecash backend error must not become free service.
            logger.warning("Ecash settlement errored for %s: %s", service.id, exc)
            return Quote(
                503,
                {"error": "ecash_backend_unavailable", "detail": "Could not verify ecash notes."},
            )
        if not accepted:
            return Quote(
                402,
                {
                    "error": "ecash_invalid",
                    "detail": "Ecash notes were invalid or below the service price.",
                    "amount_sats": price,
                },
            )
        return Settled(service, price, "ecash")

    # ---- lightning --------------------------------------------------------

    async def _settle_lightning(
        self, service: Service, payment_hash: str, price: int
    ) -> PaymentOutcome:
        if self.client is None:
            return Quote(503, {"error": "payments_unavailable"})

        record = await self.client.get_payment(payment_hash)

        if record.state is PaymentState.UNKNOWN:
            # Cannot determine whether this was paid. Never guess in either
            # direction: not 402 (the client may have paid) and never free.
            return Quote(
                503,
                {
                    "error": "payment_verification_unavailable",
                    "detail": (
                        "Could not reach the payment backend to verify this payment. "
                        "Your invoice is still valid — retry shortly."
                    ),
                },
            )

        if record.state is PaymentState.UNPAID:
            return Quote(
                402,
                {
                    "error": "payment_not_settled",
                    "detail": "This invoice has not been paid yet.",
                    "payment_hash": payment_hash,
                    "amount_sats": price,
                },
            )

        if record.incoming is False:
            logger.warning("Rejected outgoing payment %s… as proof of payment", payment_hash[:12])
            return Quote(402, {"error": "invalid_payment", "detail": "Not an incoming payment."})

        # Cross-check the settled amount against the invoice *we* issued, not
        # against this service's price — comparing to the price would report
        # "amount mismatch" for what is really a wrong-service or unknown-hash
        # error, and would mask those. The ledger row is the source of truth for
        # what was quoted; the atomic consume below is what enforces single use.
        issued = await self.ledger.aget(payment_hash)
        if issued is None:
            return Quote(
                402,
                {
                    "error": ConsumeResult.UNKNOWN_HASH.value,
                    "detail": ConsumeResult.UNKNOWN_HASH.message,
                    "service": service.id,
                    "amount_sats": price,
                },
            )
        if record.amount_sats is not None and record.amount_sats < issued["amount_sats"]:
            return Quote(
                402,
                {
                    "error": ConsumeResult.AMOUNT_MISMATCH.value,
                    "detail": (
                        f"Settled {record.amount_sats} sats against an invoice for "
                        f"{issued['amount_sats']} sats."
                    ),
                    "amount_sats": price,
                },
            )
        if record.amount_sats is None:
            logger.info(
                "LNbits did not report an amount for %s…; relying on ledger binding",
                payment_hash[:12],
            )

        result = await self.ledger.aconsume(payment_hash, service.id, price)
        if not result.settled:
            logger.info(
                "Rejected payment %s… for %s: %s", payment_hash[:12], service.id, result.value
            )
            return Quote(
                402,
                {
                    "error": result.value,
                    "detail": result.message,
                    "service": service.id,
                    "amount_sats": price,
                },
            )

        logger.info("Settled %d sats for %s (hash=%s…)", price, service.id, payment_hash[:12])
        return Settled(service, price, "lightning", payment_hash)

    async def release(self, outcome: Settled) -> bool:
        """Undo a settlement so the caller can retry with the same payment."""
        if outcome.method != "lightning" or not outcome.payment_hash:
            return False
        released = await self.ledger.arelease(
            outcome.payment_hash, outcome.service.id, self.config.invoice_ttl_seconds
        )
        if released:
            logger.info(
                "Released payment %s… for %s after a failed request; the caller may retry",
                outcome.payment_hash[:12],
                outcome.service.id,
            )
        return released

    # ---- quoting ----------------------------------------------------------

    async def _quote(self, service: Service, price: int, memo: str | None) -> PaymentOutcome:
        if self.client is None:
            return Quote(503, {"error": "payments_unavailable"})

        try:
            invoice = await self.client.create_invoice(price, memo or service.description)
        except (LNbitsError, ValueError) as exc:
            # This is the exact spot where the previous implementation fell
            # through and served the paid result for free.
            logger.error("Could not issue an invoice for %s: %s", service.id, exc)
            return Quote(
                503,
                {
                    "error": "invoice_unavailable",
                    "detail": "Could not issue a Lightning invoice right now. Try again shortly.",
                },
            )

        issued = await self.ledger.arecord_issued(
            invoice.payment_hash,
            service.id,
            price,
            memo or service.description,
            self.config.invoice_ttl_seconds,
        )

        body = {
            "payment_required": True,
            "service": service.id,
            "amount_sats": price,
            "payment_request": invoice.bolt11,
            "payment_hash": invoice.payment_hash,
            "expires_at": issued.expires_at,
            "detail": (
                "Pay this invoice, then resubmit the same request including "
                "payment_hash. Each invoice is valid for one request."
            ),
        }
        if self.fedimint is not None and self.fedimint.enabled:
            body["ecash_accepted"] = True
            body["ecash_amount_msats"] = price * 1000
        return Quote(402, body)


# --- module-level singleton -------------------------------------------------
# Configured once from main.py's lifespan so routes can call the free function
# without threading a gate object through every signature.

_gate: PaymentGate | None = None


def configure_gate(gate: PaymentGate) -> None:
    global _gate
    _gate = gate


def get_gate() -> PaymentGate:
    if _gate is None:
        raise RuntimeError(
            "Payment gate is not configured. It is set up in the application "
            "lifespan; tests should call configure_gate() explicitly."
        )
    return _gate


def reset_gate() -> None:
    global _gate
    _gate = None


async def require_payment(
    service_id: str,
    payment_hash: str | None = None,
    ecash_notes: str | None = None,
    memo: str | None = None,
) -> PaymentOutcome:
    return await get_gate().require_payment(service_id, payment_hash, ecash_notes, memo)


@asynccontextmanager
async def paid_work(outcome: Settled):
    """Run paid work, returning the payment to the caller if the work fails.

    A settled payment is consumed *before* the work runs, which is what stops
    concurrent replays. If the work then fails, the caller would otherwise have
    paid for nothing and be unable to retry — so on any exception the payment is
    released back to redeemable state and re-raised.
    """
    try:
        yield
    except Exception:
        try:
            await get_gate().release(outcome)
        except Exception:  # pragma: no cover - releasing must never mask the cause
            logger.exception("Failed to release payment after a failed request")
        raise
