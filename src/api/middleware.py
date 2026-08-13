"""HTTP middleware: request correlation, body size limits, and rate limiting.

None of these existed before. ``POST /a2a`` in particular parsed unbounded JSON
from anonymous callers, and nothing anywhere limited request rate — which matters
here because several endpoints spend money upstream (Brave, CoinGecko) or fetch
arbitrary URLs on the caller's behalf.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.security.authentication import RateLimiter

logger = logging.getLogger(__name__)

#: Endpoints that are cheap and safe to poll get a higher allowance than the
#: ones that cost us money or reach out to third parties.
DEFAULT_LIMIT = (120, 60)  # requests, window seconds
COSTLY_PREFIXES = ("/fetch", "/search", "/a2a", "/polyglot", "/coordinator")
COSTLY_LIMIT = (30, 60)
EXEMPT_PATHS = {"/health", "/", "/docs", "/openapi.json", "/redoc"}


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request id, log one structured line per request, time it."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "request failed request_id=%s method=%s path=%s duration_ms=%.1f",
                request_id,
                request.method,
                request.url.path,
                duration_ms,
            )
            raise

        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "request_id=%s method=%s path=%s status=%d duration_ms=%.1f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized request bodies before they are buffered into memory."""

    def __init__(self, app, max_bytes: int = 1024 * 1024, exempt_prefixes: tuple[str, ...] = ()):
        super().__init__(app)
        self.max_bytes = max_bytes
        # File-upload routes police their own (larger) limits.
        self.exempt_prefixes = exempt_prefixes

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if any(request.url.path.startswith(p) for p in self.exempt_prefixes):
            return await call_next(request)

        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > self.max_bytes:
                    return self._too_large()
            except ValueError:
                return JSONResponse(
                    status_code=400, content={"error": "Invalid Content-Length header"}
                )
        return await call_next(request)

    def _too_large(self) -> JSONResponse:
        return JSONResponse(
            status_code=413,
            content={
                "error": "request_too_large",
                "detail": f"Request body exceeds {self.max_bytes} bytes.",
            },
        )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client sliding-window rate limiting.

    State is in-process, so with multiple workers the effective limit is
    ``limit × workers``. That is an accepted tradeoff for a single-node
    deployment; a shared store would be needed to make it exact.
    """

    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
        self._default = RateLimiter(max_requests=DEFAULT_LIMIT[0], window_seconds=DEFAULT_LIMIT[1])
        self._costly = RateLimiter(max_requests=COSTLY_LIMIT[0], window_seconds=COSTLY_LIMIT[1])

    @staticmethod
    def _client_key(request: Request) -> str:
        # X-Forwarded-For is set by Railway's proxy; fall back to the socket peer.
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not self.enabled or request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        costly = request.url.path.startswith(COSTLY_PREFIXES)
        limiter = self._costly if costly else self._default
        window = COSTLY_LIMIT[1] if costly else DEFAULT_LIMIT[1]
        key = self._client_key(request)

        if not limiter.is_allowed(key):
            logger.warning("Rate limit exceeded for %s on %s", key, request.url.path)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limited",
                    "detail": "Too many requests. Slow down and try again.",
                },
                headers={"Retry-After": str(window)},
            )
        return await call_next(request)
