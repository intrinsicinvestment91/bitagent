"""Payment configuration, resolved once at import and validated at startup.

The central rule this module enforces: no configuration may silently produce
free service. Either payments are enforced, or they are explicitly disabled and
loudly labeled as such.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_INVOICE_TTL_SECONDS = 3600


class PaymentConfigError(RuntimeError):
    """Raised at startup when the payment configuration is unusable."""


def data_dir() -> Path:
    """Directory for SQLite databases. Mount this as a volume in production."""
    path = Path(os.getenv("BITAGENT_DATA_DIR", "data"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _flag(name: str) -> bool | None:
    """Read a tri-state boolean env var: True, False, or unset."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PaymentConfig:
    enabled: bool
    lnbits_url: str | None
    lnbits_api_key: str | None
    invoice_ttl_seconds: int

    @property
    def lnbits_configured(self) -> bool:
        return bool(self.lnbits_url and self.lnbits_api_key)

    def describe(self) -> str:
        return "enforced" if self.enabled else "disabled"


def load_config() -> PaymentConfig:
    """Resolve payment configuration from the environment.

    Raises PaymentConfigError when LNbits is not configured and the operator has
    not explicitly opted into free mode. Refusing to start is deliberate: a
    misconfigured deploy that quietly serves everything for free is far worse
    than one that fails visibly.
    """
    url = (os.getenv("LNBITS_URL") or "").strip() or None
    key = (os.getenv("LNBITS_API_KEY") or "").strip() or None
    requested = _flag("PAYMENTS_ENABLED")
    configured = bool(url and key)

    try:
        ttl = int(os.getenv("INVOICE_TTL_SECONDS", str(DEFAULT_INVOICE_TTL_SECONDS)))
    except ValueError:
        raise PaymentConfigError(
            "INVOICE_TTL_SECONDS must be an integer number of seconds"
        ) from None
    if ttl <= 0:
        raise PaymentConfigError("INVOICE_TTL_SECONDS must be positive")

    if requested is False:
        # Explicit free mode. Allowed anywhere, but never silent — main.py logs a
        # warning and /health reports it.
        return PaymentConfig(False, url, key, ttl)

    if not configured:
        missing = [
            name for name, value in (("LNBITS_URL", url), ("LNBITS_API_KEY", key)) if not value
        ]
        verb = "is" if len(missing) == 1 else "are"
        raise PaymentConfigError(
            f"Payments are enabled but {' and '.join(missing)} {verb} not set. "
            "Set the LNbits credentials, or set PAYMENTS_ENABLED=false to run "
            "this node in free mode with every service explicitly labeled free."
        )

    return PaymentConfig(True, url, key, ttl)
