from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from app.database.database import engine
from app.utils.logger import log_access, log_error, log_event, logger


# ============================================================
# APPLICATION LIFESPAN
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    log_event(
        "Application startup",
        level=logging.INFO,
        application=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.APP_ENVIRONMENT,
    )

    try:
        yield
    finally:
        engine.dispose()
        log_event(
            "Application shutdown",
            level=logging.INFO,
            application=settings.APP_NAME,
        )


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "An AI-assisted health surveillance platform for "
        "health-report management, disease-trend analysis, "
        "and potential outbreak monitoring."
    ),
    debug=settings.APP_DEBUG,
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.APP_ENVIRONMENT != "production" else None,
    openapi_url="/openapi.json" if settings.APP_ENVIRONMENT != "production" else None,
)


# ============================================================
# SECURITY MIDDLEWARE
# ============================================================

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.TRUSTED_HOSTS,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)


# ============================================================
# REQUEST SIZE LIMIT
# ============================================================

class RequestBodyTooLarge(Exception):
    """Raised when a request exceeds the configured body limit."""


class RequestSizeLimitMiddleware:
    """Reject oversized request bodies before endpoint processing."""

    def __init__(self, app: Any, max_request_size: int) -> None:
        self.app = app
        self.max_request_size = max_request_size

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")

        if content_length is not None:
            try:
                declared_size = int(content_length)
            except (ValueError, TypeError):
                await self._send_error(
                    scope,
                    receive,
                    send,
                    status_code=400,
                    message="Invalid Content-Length header.",
                )
                return

            if declared_size < 0:
                await self._send_error(
                    scope,
                    receive,
                    send,
                    status_code=400,
                    message="Invalid Content-Length header.",
                )
                return

            if declared_size > self.max_request_size:
                await self._send_error(
                    scope,
                    receive,
                    send,
                    status_code=413,
                    message="Request body is too large.",
                )
                return

        received_size = 0
        response_started = False

        async def limited_receive():
            nonlocal received_size

            message = await receive()

            if message["type"] == "http.request":
                body = message.get("body", b"")
                received_size += len(body)

                if received_size > self.max_request_size:
                    raise RequestBodyTooLarge()

            return message

        async def tracked_send(message):
            nonlocal response_started

            if message["type"] == "http.response.start":
                response_started = True

            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except RequestBodyTooLarge:
            if response_started:
                raise

            await self._send_error(
                scope,
                receive,
                send,
                status_code=413,
                message="Request body is too large.",
            )

    @staticmethod
    async def _send_error(scope, receive, send, status_code: int, message: str) -> None:
        response = JSONResponse(
            status_code=status_code,
            content={
                "success": False,
                "error": {
                    "code": status_code,
                    "message": message,
                },
            },
        )

        await response(scope, receive, send)


app.add_middleware(
    RequestSizeLimitMiddleware,
    max_request_size=settings.MAX_REQUEST_SIZE,
)


# ============================================================
# RESPONSE SECURITY HEADERS AND REQUEST LOGGING
# ============================================================

@app.middleware("http")
async def request_middleware(request: Request, call_next):
    """Add security headers and measure request processing time."""
    start_time = time.perf_counter()
    request_id = request.headers.get("X-Request-ID", "")

    if (
        not request_id
        or len(request_id) > 64
        or not all(character.isalnum() or character in "-_" for character in request_id)
    ):
        request_id = ""

    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        log_error(
            "Unhandled request exception",
            error=exc,
            method=request.method,
            path=request.url.path,
            duration_ms=duration_ms,
            request_id=request_id or None,
        )

        response = JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": 500,
                    "message": "An unexpected server error occurred.",
                },
            },
        )

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Request-ID"] = request_id or "server-generated"

    if settings.APP_ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    log_access(
        "HTTP request completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
        request_id=request_id or None,
    )

    return response


# ============================================================
# STANDARDIZED ERROR RESPONSES
# ============================================================

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Preserve HTTP status codes and headers without exposing internals."""
    detail = exc.detail

    if isinstance(detail, str):
        message = detail
    else:
        message = "The request could not be completed."

    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "success": False,
            "error": {
                "code": exc.status_code,
                "message": message,
            },
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return safe validation errors without echoing submitted values."""
    errors = [
        {
            "field": ".".join(str(part) for part in error.get("loc", ())),
            "message": error.get("msg", "Invalid value."),
            "type": error.get("type", "validation_error"),
        }
        for error in exc.errors()
    ]

    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": 422,
                "message": "Request validation failed.",
                "details": errors,
            },
        },
    )


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception):
    """Fallback for unhandled exceptions."""
    log_error(
        "Unhandled application exception",
        error=exc,
        method=request.method,
        path=request.url.path,
    )

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": 500,
                "message": "An unexpected server error occurred.",
            },
        },
    )


# ============================================================
# ROOT ENDPOINT
# ============================================================

@app.get("/", tags=["System"], summary="Application information")
async def root():
    return {
        "success": True,
        "application": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "environment": settings.APP_ENVIRONMENT,
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health", tags=["System"], summary="Application health check")
async def health_check():
    """Lightweight liveness endpoint."""
    return {
        "success": True,
        "status": "healthy",
        "application": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


# ============================================================
# ROUTER REGISTRATION
# ============================================================

from app.api.routes_admin import router as admin_router
from app.api.routes_ai import router as ai_router
from app.api.routes_alerts import router as alerts_router
from app.api.routes_auth import router as auth_router
from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_reports import router as reports_router
from app.api.routes_users import router as users_router

for api_router in (
    auth_router,
    users_router,
    reports_router,
    ai_router,
    admin_router,
    alerts_router,
    dashboard_router,
):
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
