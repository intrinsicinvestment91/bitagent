"""Authentication for operational endpoints.

``GET /wallet/balance`` used to be public, which published the node's Lightning
balance to anyone who asked. Operational routes now require ``ADMIN_API_KEY``.

When no key is configured the routes are not registered at all, so an operator
who forgets to set one gets a 404 rather than an unprotected endpoint.
"""

from __future__ import annotations

import logging
import os
import secrets

from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)

MIN_KEY_LENGTH = 16


def admin_key() -> str | None:
    key = (os.getenv("ADMIN_API_KEY") or "").strip()
    if not key:
        return None
    if len(key) < MIN_KEY_LENGTH:
        logger.warning(
            "ADMIN_API_KEY is shorter than %d characters; admin routes stay disabled",
            MIN_KEY_LENGTH,
        )
        return None
    return key


def admin_enabled() -> bool:
    return admin_key() is not None


async def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    """FastAPI dependency guarding operational routes."""
    expected = admin_key()
    if expected is None:
        # Should be unreachable: routes are not mounted without a key.
        raise HTTPException(status_code=404, detail="Not found")
    if not x_admin_key or not secrets.compare_digest(x_admin_key, expected):
        logger.warning("Rejected admin request with a missing or incorrect key")
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Key")
