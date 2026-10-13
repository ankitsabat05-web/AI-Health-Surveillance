from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------
# Configuration
# ---------------------------------------

APP_LOGGER_NAME = "health_surveillance"

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_DIRECTORY = "logs"
DEFAULT_LOG_FILE = "application.log"

MAX_LOG_FILE_BYTES = 5 * 1024 * 1024  # 5 MB
LOG_BACKUP_COUNT = 5

SENSITIVE_FIELD_NAMES = {
    "password",
    "hashed_password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "secret_key",
    "authorization",
    "cookie",
    "email",
    "phone",
    "phone_number",
    "address",
    "symptoms",
    "diagnosis",
    "medical_history",
    "patient_name",
    "date_of_birth",
}

LOG_DIRECTORY = Path(os.getenv("LOG_DIRECTORY", DEFAULT_LOG_DIRECTORY))
LOG_LEVEL_NAME = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()


# ---------------------------------------
# Sensitive Data Redaction
# ---------------------------------------

def _redact_value(value: Any, *, field_name: str = "") -> Any:
    """Redact known sensitive fields before they reach a log record."""
    normalized_name = field_name.lower()

    if normalized_name in SENSITIVE_FIELD_NAMES:
        return "[REDACTED]"

    if isinstance(value, dict):
        return {
            str(key): _redact_value(item, field_name=str(key))
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return f"[COLLECTION: {len(value)} ITEMS]"

    if isinstance(value, str):
        cleaned = re.sub(r"[\r\n\t]+", " ", value)
        return cleaned[:1000]

    if value is None or isinstance(value, (bool, int, float)):
        return value

    return f"<{type(value).__name__}>"


# ---------------------------------------
# JSON Log Formatter
# ---------------------------------------

class JSONLogFormatter(logging.Formatter):
    """Format log records as structured JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(
            record.created,
            tz=timezone.utc,
        ).isoformat()

        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": _redact_value(record.getMessage()),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        reserved_fields = set(logging.makeLogRecord({}).__dict__.keys())

        for key, value in record.__dict__.items():
            if key in reserved_fields or key.startswith("_"):
                continue

            if key in {"message", "asctime"}:
                continue

            payload[key] = _redact_value(value, field_name=key)

        if record.exc_info:
            exception_type = record.exc_info[0]
            payload["exception_type"] = (
                exception_type.__name__ if exception_type is not None else "Exception"
            )

        return json.dumps(payload, ensure_ascii=False, default=str)


# ---------------------------------------
# Logger Setup
# ---------------------------------------

def setup_logger(
    name: str = APP_LOGGER_NAME,
    *,
    level: str | None = None,
    log_to_file: bool = True,
) -> logging.Logger:
    """Configure a reusable application logger."""
    selected_level_name = (level or LOG_LEVEL_NAME).upper()
    selected_level = getattr(logging, selected_level_name, None)

    if not isinstance(selected_level, int):
        raise ValueError(f"Invalid log level: {selected_level_name}")

    logger = logging.getLogger(name)
    logger.setLevel(selected_level)
    logger.propagate = False

    if getattr(logger, "_health_logger_configured", False):
        for handler in logger.handlers:
            handler.setLevel(selected_level)
        return logger

    formatter = JSONLogFormatter()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(selected_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_to_file:
        try:
            LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)

            file_handler = logging.handlers.RotatingFileHandler(
                filename=LOG_DIRECTORY / DEFAULT_LOG_FILE,
                maxBytes=MAX_LOG_FILE_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding="utf-8",
                delay=True,
            )

            file_handler.setLevel(selected_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        except OSError:
            logger.warning(
                "File logging could not be initialized; console logging remains enabled."
            )

    setattr(logger, "_health_logger_configured", True)
    return logger


# ---------------------------------------
# Application Logger
# ---------------------------------------

logger = setup_logger()


# ---------------------------------------
# Safe Logging Helpers
# ---------------------------------------

def log_event(event: str, *, level: int = logging.INFO, **context: Any) -> None:
    """Log a short event with optional structured context."""
    safe_event = _redact_value(event)

    safe_context = {
        key: _redact_value(value, field_name=key)
        for key, value in context.items()
    }

    logger.log(level, "%s", safe_event, extra=safe_context)


def log_error(event: str, *, error: Exception | None = None, **context: Any) -> None:
    """Log an error without exposing exception messages or raw tracebacks."""
    safe_context = {
        key: _redact_value(value, field_name=key)
        for key, value in context.items()
    }

    if error is not None:
        safe_context["exception_type"] = type(error).__name__

    logger.error("%s", _redact_value(event), extra=safe_context)