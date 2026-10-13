from __future__ import annotations

import json
import logging
import logging.handlers
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings

# ---------------------------------------
# Configuration
# ---------------------------------------

APP_LOGGER_NAME = "health_surveillance"

DEFAULT_LOG_LEVEL = settings.LOG_LEVEL
DEFAULT_LOG_DIRECTORY = settings.LOG_DIRECTORY
DEFAULT_LOG_FILE = "app.log"

MAX_LOG_FILE_BYTES = 5 * 1024 * 1024  # 5 MB
LOG_BACKUP_COUNT = 5
ERROR_LOGGER_NAME = "app"
ACCESS_LOGGER_NAME = "app.access"
SECURITY_LOGGER_NAME = "app.security_events"
AI_PREDICTION_LOGGER_NAME = "app.ai.predictions"

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

LOG_DIRECTORY = Path(DEFAULT_LOG_DIRECTORY)
LOG_LEVEL_NAME = DEFAULT_LOG_LEVEL.upper()


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
        _configure_category_loggers(selected_level, log_to_file=log_to_file)
        return logger

    formatter = JSONLogFormatter()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(selected_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_to_file:
        try:
            LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
            _add_file_handler(logger, DEFAULT_LOG_FILE, selected_level, formatter)
            _add_file_handler(logger, "error.log", logging.ERROR, formatter)

            application_logger = logging.getLogger(ERROR_LOGGER_NAME)
            application_logger.setLevel(selected_level)
            application_logger.propagate = False
            _add_file_handler(
                application_logger,
                DEFAULT_LOG_FILE,
                selected_level,
                formatter,
            )
            _add_file_handler(
                application_logger,
                "error.log",
                logging.ERROR,
                formatter,
            )
            _configure_category_loggers(
                selected_level,
                log_to_file=True,
                formatter=formatter,
            )

        except OSError:
            logger.warning(
                "One or more file logs could not be initialized; console logging remains enabled."
            )
    else:
        _configure_category_loggers(selected_level, log_to_file=False)

    setattr(logger, "_health_logger_configured", True)
    return logger


def _add_file_handler(
    target_logger: logging.Logger,
    filename: str,
    level: int,
    formatter: logging.Formatter,
) -> None:
    """Attach a rotating JSON-lines file handler once per destination."""
    destination = (LOG_DIRECTORY / filename).resolve()
    for handler in target_logger.handlers:
        if (
            isinstance(handler, logging.handlers.RotatingFileHandler)
            and Path(handler.baseFilename).resolve() == destination
        ):
            handler.setLevel(level)
            return

    file_handler = logging.handlers.RotatingFileHandler(
        filename=destination,
        maxBytes=MAX_LOG_FILE_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
        delay=False,
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    target_logger.addHandler(file_handler)


def _configure_category_loggers(
    level: int,
    *,
    log_to_file: bool,
    formatter: logging.Formatter | None = None,
) -> None:
    """Configure application namespace and dedicated category log files."""
    app_logger = logging.getLogger(ERROR_LOGGER_NAME)
    app_logger.setLevel(level)
    app_logger.propagate = False

    access_logger = logging.getLogger(ACCESS_LOGGER_NAME)
    security_logger = logging.getLogger(SECURITY_LOGGER_NAME)
    ai_logger = logging.getLogger(AI_PREDICTION_LOGGER_NAME)

    for category_logger in (access_logger, security_logger, ai_logger):
        category_logger.setLevel(level)

    if not log_to_file or formatter is None:
        return

    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    _add_file_handler(access_logger, "access.log", level, formatter)
    _add_file_handler(security_logger, "security.log", level, formatter)
    _add_file_handler(ai_logger, "ai_prediction.log", level, formatter)


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


def _log_category(
    logger_name: str,
    event: str,
    *,
    level: int = logging.INFO,
    **context: Any,
) -> None:
    safe_context = {
        key: _redact_value(value, field_name=key)
        for key, value in context.items()
    }
    logging.getLogger(logger_name).log(
        level,
        "%s",
        _redact_value(event),
        extra=safe_context,
    )


def log_access(event: str, **context: Any) -> None:
    """Write a request/access event without including request bodies."""
    _log_category(ACCESS_LOGGER_NAME, event, **context)


def log_security(event: str, **context: Any) -> None:
    """Write an authentication or authorization event safely."""
    _log_category(SECURITY_LOGGER_NAME, event, **context)


def log_ai_prediction(operation: str, result_type: str) -> None:
    """Record an AI operation without logging symptoms or health inputs."""
    _log_category(
        AI_PREDICTION_LOGGER_NAME,
        "AI analysis completed",
        operation=operation,
        result_type=result_type,
        requires_human_review=True,
    )