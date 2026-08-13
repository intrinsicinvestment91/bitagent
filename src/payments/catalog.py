"""The service catalog: one source of truth for what a service costs.

Prices used to live in seven places in three different shapes (scalar
``price_sats`` attributes, dicts, and ``get_price(service)`` accessors), which is
how an HTTP route and its A2A twin ended up disagreeing about whether a service
was paid at all. Every priced surface now resolves the same entry by service id.

The ``synthetic`` flag carries the honesty invariant: a service whose output is
not real data may not cost anything. That is enforced in ``Service.__post_init__``
rather than by convention, so the "charging sats for a mock" class of bug cannot
reappear without failing at import time.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from typing import Callable


class UnknownServiceError(KeyError):
    """Raised when a service id is not present in the catalog."""


def _module_available(name: str) -> Callable[[], bool]:
    def check() -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            return False

    return check


def _always() -> bool:
    return True


@dataclass(frozen=True)
class Service:
    """A single billable (or explicitly free) capability."""

    id: str
    description: str
    price_sats: int
    #: True when the response is demo/placeholder data rather than a real result.
    synthetic: bool = False
    #: Runtime check for optional backends (e.g. whisper for transcription).
    is_available: Callable[[], bool] = field(default=_always, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.price_sats < 0:
            raise ValueError(f"{self.id}: price_sats may not be negative")
        if self.synthetic and self.price_sats > 0:
            raise ValueError(
                f"{self.id}: a synthetic service returns placeholder data and "
                "must not be charged for (price_sats must be 0)"
            )

    @property
    def available(self) -> bool:
        return self.is_available()

    def info(self) -> dict:
        """Public description used by /info and /services responses."""
        payload = {
            "id": self.id,
            "description": self.description,
            "price_sats": self.effective_price,
            "available": self.available,
        }
        if self.synthetic:
            payload["synthetic"] = True
            payload["notice"] = (
                "Demo output — this endpoint returns placeholder data, not real "
                "results, and is free of charge."
            )
        elif not self.available:
            payload["notice"] = "Temporarily unavailable: backend not installed."
        return payload

    @property
    def effective_price(self) -> int:
        """Price actually charged. An unavailable backend is never billed for."""
        return self.price_sats if self.available else 0


def _service(*args, **kwargs) -> tuple[str, Service]:
    svc = Service(*args, **kwargs)
    return svc.id, svc


#: Every billable surface in the application, keyed by stable service id.
SERVICES: dict[str, Service] = dict(
    [
        _service("search.query", "Web search (Brave → SearXNG → DuckDuckGo)", 10),
        _service("fetch.url", "Fetch and clean a public web page", 25),
        _service("oracle.price", "Live price for a single asset", 2),
        _service("oracle.prices", "Live prices for several assets", 5),
        _service("oracle.convert", "Convert sats to fiat", 1),
        _service("polyglot.translate", "Translate text between languages", 100),
        _service(
            "polyglot.transcribe",
            "Transcribe speech to text (Whisper)",
            250,
            is_available=_module_available("whisper"),
        ),
        _service("identity.register_nip05", "Register and verify a NIP-05 identifier", 1000),
        _service("identity.get_identity", "Look up an identity by pubkey", 10),
        _service("identity.list_verified", "List currently verified identities", 25),
        _service("identity.search", "Search registered identities", 25),
        _service("identity.get_trust_signal", "Trust score and supporting evidence", 10),
        # --- Synthetic demos: reference implementations, not real data sources ---
        _service(
            "streamfinder.search",
            "Streaming availability lookup — A2A reference implementation over a "
            "small fixed demo dataset",
            0,
            synthetic=True,
        ),
        _service(
            "coordinator.translate_audio",
            "Chained transcribe → translate across sibling agents",
            350,
            is_available=_module_available("whisper"),
        ),
        _service(
            "coordinator.chain_tasks",
            "Chain arbitrary services across BitAgent agents",
            100,
        ),
    ]
)


def get_service(service_id: str) -> Service:
    try:
        return SERVICES[service_id]
    except KeyError:
        raise UnknownServiceError(f"Unknown service id '{service_id}'") from None


def price_of(service_id: str) -> int:
    """Price actually charged for a service, in sats."""
    return get_service(service_id).effective_price


def pricing_for(prefix: str) -> dict[str, int]:
    """Prices for every service under a dotted prefix, e.g. ``oracle``."""
    return {
        sid: svc.effective_price
        for sid, svc in SERVICES.items()
        if sid.split(".", 1)[0] == prefix
    }


def catalog_info() -> list[dict]:
    return [svc.info() for svc in SERVICES.values()]
