"""
Security Middleware
===================
CORS, CSP, security headers, and request logging.
"""

import time
import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()

        response = await call_next(request)

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(self), microphone=(), geolocation=(), payment=()"
        )

        # Content Security Policy
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: blob:; "
            "media-src 'self' blob:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        response.headers["Content-Security-Policy"] = csp

        # Request timing
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.3f}"

        # Log request
        logger.debug(
            f"{request.method} {request.url.path} "
            f"→ {response.status_code} ({process_time:.3f}s)"
        )

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all API requests for monitoring."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Only log API requests
        if request.url.path.startswith("/api/"):
            client_ip = request.client.host if request.client else "unknown"
            logger.info(
                f"[{request.method}] {request.url.path} "
                f"from {client_ip}"
            )

        response = await call_next(request)
        return response
