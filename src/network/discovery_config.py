"""Public discovery configuration, resolved at import and validated at startup.

Announcing an agent is a public act: it opens WebSockets to third-party relays
and publishes an endpoint anyone can call. So the default here is off, and the
enabled path is validated the way src/payments/config.py validates a wallet —
an explicitly enabled but incompletely configured node refuses to start rather
than inventing an identity and announcing itself anyway.

Key material never appears in an error message or a log line from this module.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

NOSTR_KEY_HEX_CHARS = 64

#: Order of the secp256k1 group. A secret must be in [1, order).
SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}

# Anchored, so embedded whitespace and any other stray character are rejected
# rather than tolerated the way bytes.fromhex would tolerate them.
_HEX_KEY = re.compile(rf"\A[0-9a-fA-F]{{{NOSTR_KEY_HEX_CHARS}}}\Z")

# Messages deliberately describe the defect without quoting the value: a key must
# never reach a log or an exception, and a URL may carry embedded credentials.
_KEY_SHAPE = (
    f"NOSTR_PRIVATE_KEY must be exactly {NOSTR_KEY_HEX_CHARS} hexadecimal characters "
    "(a 32-byte secp256k1 secret), with no embedded whitespace. The configured value "
    "is not; it is not echoed here."
)
_KEY_RANGE = (
    "NOSTR_PRIVATE_KEY is not a usable secp256k1 secret: the value must be at least 1 "
    "and below the curve order. The configured value is not; it is not echoed here."
)
_URL_SHAPE = (
    "PUBLIC_URL must be an absolute http(s) URL — host, optional port, optional path — "
    "and nothing else. The configured value is not; it is not echoed here."
)
_URL_CREDENTIALS = (
    "PUBLIC_URL must not embed a username or password; it is published to strangers. "
    "The configured value is not echoed here."
)
_URL_EXTRAS = (
    "PUBLIC_URL must not carry a query string or fragment: agent endpoints are built by "
    "appending a path to it. The configured value is not echoed here."
)


class DiscoveryConfigError(RuntimeError):
    """Raised at startup when discovery is enabled but not usable."""


class DiscoveryDisabledError(RuntimeError):
    """Raised when discovery machinery is requested while discovery is disabled."""


class DiscoveryUnavailableError(RuntimeError):
    """Raised when discovery is configured but cannot be brought up.

    Distinct from DiscoveryConfigError: the configuration is fine, the machinery
    is not — a missing Nostr dependency, or an identity that will not build.
    """


def discovery_enabled() -> bool:
    """Whether the operator has explicitly opted into public discovery.

    Anything other than a recognised true value means disabled, including an
    unrecognised one: a typo must not be the thing that puts a node on public
    relays.
    """
    raw = (os.getenv("NOSTR_DISCOVERY_ENABLED") or "").strip()
    if not raw:
        return False
    value = raw.lower()
    if value in _TRUE_VALUES:
        return True
    if value not in _FALSE_VALUES:
        logger.warning(
            "NOSTR_DISCOVERY_ENABLED=%r is not a recognised boolean; "
            "public discovery stays disabled. Use 'true' to enable it.",
            raw,
        )
    return False


def _validated_key(raw: str | None) -> str:
    """Return the key lowercased, or raise. Never quotes the value."""
    key = (raw or "").strip()
    if not key:
        raise DiscoveryConfigError(
            "Public discovery is enabled but NOSTR_PRIVATE_KEY is not set. "
            "Discovery needs a persistent key: an ephemeral one would announce "
            "this node under a different identity after every restart."
        )
    if not _HEX_KEY.match(key):
        raise DiscoveryConfigError(_KEY_SHAPE)
    if not 1 <= int(key, 16) < SECP256K1_ORDER:
        raise DiscoveryConfigError(_KEY_RANGE)
    return key.lower()


def _is_unroutable_host(host: str) -> bool:
    """Whether a host only ever resolves on the machine itself.

    An announcement carrying one of these tells every reader to call itself.
    """
    name = host.lower().rstrip(".")  # "localhost." is localhost
    if name == "localhost" or name.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(name)
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


def _validated_public_url(raw: str | None) -> str:
    """Return the URL without its trailing slashes, or raise.

    A path prefix is kept: endpoints are built by appending to this value.
    """
    url = (raw or "").strip().rstrip("/")
    if not url:
        raise DiscoveryConfigError(
            "Public discovery is enabled but PUBLIC_URL is not set. Without it "
            "every announcement would advertise a URL no caller can reach."
        )
    try:
        parsed = urlparse(url)
        port = parsed.port  # raises ValueError on a malformed port
    except ValueError:
        raise DiscoveryConfigError(_URL_SHAPE) from None
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise DiscoveryConfigError(_URL_SHAPE)
    if port is not None and not 1 <= port <= 65535:
        raise DiscoveryConfigError(_URL_SHAPE)
    if parsed.username or parsed.password:
        raise DiscoveryConfigError(_URL_CREDENTIALS)
    if parsed.query or parsed.fragment:
        raise DiscoveryConfigError(_URL_EXTRAS)
    if _is_unroutable_host(parsed.hostname):
        # The host alone is safe to name, and is the useful part.
        raise DiscoveryConfigError(
            f"PUBLIC_URL host {parsed.hostname!r} resolves only on this machine. "
            "Set the address callers actually use, or leave public discovery disabled."
        )
    return url


def _raw_public_url() -> str | None:
    """PUBLIC_URL wins; the Railway domain is only a fallback for an unset one."""
    configured = (os.getenv("PUBLIC_URL") or "").strip()
    if configured:
        return configured
    if domain := (os.getenv("RAILWAY_PUBLIC_DOMAIN") or "").strip():
        return f"https://{domain}"
    return None


@dataclass(frozen=True)
class DiscoveryConfig:
    """Resolved discovery settings. ``public_url`` has no trailing slash."""

    enabled: bool
    nostr_private_key: str | None
    public_url: str | None

    def describe(self) -> str:
        return "enabled" if self.enabled else "disabled"


def validate_discovery_config(config: DiscoveryConfig) -> DiscoveryConfig:
    """Return a validated, normalised config, or raise DiscoveryConfigError.

    The single validator: both load_discovery_config() and the discovery manager
    accessor come through here, so a DiscoveryConfig built directly by any caller
    is checked on exactly the same terms as one read from the environment. A
    disabled config normalises to nothing configured; an enabled one has its key
    and URL revalidated every time.
    """
    if not config.enabled:
        return DiscoveryConfig(False, None, None)
    return DiscoveryConfig(
        enabled=True,
        nostr_private_key=_validated_key(config.nostr_private_key),
        public_url=_validated_public_url(config.public_url),
    )


def load_discovery_config() -> DiscoveryConfig:
    """Resolve discovery configuration from the environment.

    Disabled is the default. Enabled requires a persistent key and a routable
    public URL, and raises DiscoveryConfigError before any network operation when
    either is missing or malformed.
    """
    return validate_discovery_config(
        DiscoveryConfig(
            enabled=discovery_enabled(),
            nostr_private_key=os.getenv("NOSTR_PRIVATE_KEY"),
            public_url=_raw_public_url(),
        )
    )
