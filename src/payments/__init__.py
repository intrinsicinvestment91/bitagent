"""Payment core: catalog, LNbits client, single-use ledger, and the payment gate.

Wiring, in ``main.py``'s lifespan::

    config = load_config()
    ledger = PaymentLedger(data_dir() / "payments.db")
    client = AsyncLNbitsClient(config.lnbits_url, config.lnbits_api_key) if config.enabled else None
    configure_gate(PaymentGate(config, ledger, client, fedimint))

Routes then call ``require_payment(service_id, ...)`` and return any ``Quote``
they get back.
"""

from src.payments.catalog import (
    SERVICES,
    Service,
    UnknownServiceError,
    catalog_info,
    get_service,
    price_of,
    pricing_for,
)
from src.payments.config import (
    PaymentConfig,
    PaymentConfigError,
    data_dir,
    load_config,
)
from src.payments.gate import (
    PaymentGate,
    PaymentOutcome,
    Quote,
    Settled,
    configure_gate,
    get_gate,
    paid_work,
    require_payment,
    reset_gate,
)
from src.payments.ledger import ConsumeResult, PaymentLedger
from src.payments.lnbits import (
    AsyncLNbitsClient,
    Invoice,
    LNbitsError,
    PaymentRecord,
    PaymentState,
)

__all__ = [
    "SERVICES",
    "AsyncLNbitsClient",
    "ConsumeResult",
    "Invoice",
    "LNbitsError",
    "PaymentConfig",
    "PaymentConfigError",
    "PaymentGate",
    "PaymentLedger",
    "PaymentOutcome",
    "PaymentRecord",
    "PaymentState",
    "Quote",
    "Service",
    "Settled",
    "UnknownServiceError",
    "catalog_info",
    "configure_gate",
    "data_dir",
    "get_gate",
    "get_service",
    "load_config",
    "paid_work",
    "price_of",
    "pricing_for",
    "require_payment",
    "reset_gate",
]
