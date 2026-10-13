from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ============================================================
# APPLICATION SETTINGS
# ============================================================

class Settings(BaseSettings):
    """Central configuration for the AI Health Surveillance System."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )

    # --------------------------------------------------------
    # Application
    # --------------------------------------------------------

    APP_NAME: str = "AI Health Surveillance System"
    APP_VERSION: str = "1.0.0"
    APP_ENVIRONMENT: Literal["development", "testing", "production"] = "development"
    APP_DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # --------------------------------------------------------
    # Security and JWT
    # --------------------------------------------------------

    SECRET_KEY: SecretStr = Field(
        default_factory=lambda: SecretStr(secrets.token_urlsafe(48))
    )

    JWT_ALGORITHM: Literal["HS256"] = "HS256"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=15,
        ge=1,
        le=1440,
    )

    HEALTH_DATA_ENCRYPTION_KEY: SecretStr | None = None

    # --------------------------------------------------------
    # Rate Limiting
    # --------------------------------------------------------

    RATE_LIMIT_PER_MINUTE: int = Field(
        default=120,
        ge=1,
        le=10000,
    )

    LOGIN_RATE_LIMIT_PER_MINUTE: int = Field(
        default=5,
        ge=1,
        le=100,
    )

    MAX_REQUEST_SIZE: int = Field(
        default=1_048_576,
        ge=1024,
        le=10_485_760,
    )

    # --------------------------------------------------------
    # CORS
    # --------------------------------------------------------

    FRONTEND_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5500",
            "http://127.0.0.1:5500",
        ]
    )

    # --------------------------------------------------------
    # Trusted Hosts
    # --------------------------------------------------------

    TRUSTED_HOSTS: list[str] = Field(
        default_factory=lambda: [
            "localhost",
            "127.0.0.1",
            "testserver",
        ]
    )

    # --------------------------------------------------------
    # Database
    # --------------------------------------------------------

    DATABASE_URL: SecretStr = SecretStr("sqlite:///./health_surveillance.db")

    DATABASE_POOL_SIZE: int = Field(
        default=5,
        ge=1,
        le=100,
    )

    DATABASE_MAX_OVERFLOW: int = Field(
        default=10,
        ge=0,
        le=100,
    )

    DATABASE_POOL_TIMEOUT: int = Field(
        default=30,
        ge=1,
        le=300,
    )

    DATABASE_CONNECT_TIMEOUT: int = Field(
        default=10,
        ge=1,
        le=120,
    )

    # --------------------------------------------------------
    # Logging
    # --------------------------------------------------------

    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_DIRECTORY: str = "logs"
    LOG_TO_FILE: bool = True

    # --------------------------------------------------------
    # AI and Machine Learning
    # --------------------------------------------------------

    AI_MODEL_PATH: str = "ml/models"

    AI_CONFIDENCE_THRESHOLD: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
    )

    AI_MAX_BATCH_SIZE: int = Field(
        default=100,
        ge=1,
        le=1000,
    )

    # --------------------------------------------------------
    # Health Reporting
    # --------------------------------------------------------

    DEFAULT_TIMEZONE: str = "Asia/Kolkata"

    MAX_REPORT_RANGE_DAYS: int = Field(
        default=366,
        ge=1,
        le=3660,
    )

    MAX_PAGE_SIZE: int = Field(
        default=100,
        ge=1,
        le=500,
    )

    # --------------------------------------------------------
    # Validators
    # --------------------------------------------------------

    @field_validator("API_V1_PREFIX")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        value = value.strip()

        if not value.startswith("/"):
            raise ValueError("API_V1_PREFIX must start with '/'.")

        if value != "/" and value.endswith("/"):
            value = value.rstrip("/")

        if "//" in value or "?" in value or "#" in value:
            raise ValueError("API_V1_PREFIX contains invalid characters.")

        return value

    @field_validator("FRONTEND_ORIGINS")
    @classmethod
    def validate_frontend_origins(cls, origins: list[str]) -> list[str]:
        normalized: list[str] = []

        for origin in origins:
            origin = origin.strip().rstrip("/")

            if not origin:
                raise ValueError("Frontend origins cannot contain empty entries.")

            parsed = urlsplit(origin)

            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username is not None
                or parsed.password is not None
            ):
                raise ValueError(
                    "Each frontend origin must be an HTTP(S) origin without a path, query, or credentials."
                )

            if "*" in origin:
                raise ValueError("Wildcard origins are not permitted.")

            normalized.append(origin)

        return list(dict.fromkeys(normalized))

    @field_validator("TRUSTED_HOSTS")
    @classmethod
    def validate_trusted_hosts(cls, hosts: list[str]) -> list[str]:
        normalized: list[str] = []

        for host in hosts:
            host = host.strip().lower()

            if (
                not host
                or "/" in host
                or "://" in host
                or "@" in host
                or "*" in host
                or " " in host
            ):
                raise ValueError("Each trusted host must be a specific hostname.")

            normalized.append(host)

        return list(dict.fromkeys(normalized))

    @field_validator("LOG_DIRECTORY")
    @classmethod
    def validate_log_directory(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("LOG_DIRECTORY cannot be empty.")

        return value

    @model_validator(mode="after")
    def validate_environment_security(self) -> "Settings":
        """Enforce additional requirements for production deployments."""

        if self.APP_ENVIRONMENT == "production":
            secret = self.SECRET_KEY.get_secret_value()

            if len(secret) < 32:
                raise ValueError("Production SECRET_KEY must contain at least 32 characters.")

            if self.APP_DEBUG:
                raise ValueError("APP_DEBUG must be False in production.")

            if not self.TRUSTED_HOSTS:
                raise ValueError("Configure TRUSTED_HOSTS in production.")

            if not self.FRONTEND_ORIGINS:
                raise ValueError("Configure FRONTEND_ORIGINS in production.")

            for origin in self.FRONTEND_ORIGINS:
                if not origin.startswith("https://"):
                    raise ValueError("Production frontend origins must use HTTPS.")

            encryption_key = self.HEALTH_DATA_ENCRYPTION_KEY

            if encryption_key is None:
                raise ValueError("Configure HEALTH_DATA_ENCRYPTION_KEY in production.")

            if len(encryption_key.get_secret_value()) < 32:
                raise ValueError("HEALTH_DATA_ENCRYPTION_KEY is invalid.")

            database_url = self.DATABASE_URL.get_secret_value()

            if database_url.startswith("sqlite"):
                raise ValueError("Configure a production database instead of SQLite.")

        return self


# ============================================================
# SETTINGS ACCESS
# ============================================================

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Create and cache settings."""
    return Settings()


settings = get_settings()


# ============================================================
# COMPATIBILITY CONSTANTS
# ============================================================

APP_NAME = settings.APP_NAME
APP_VERSION = settings.APP_VERSION
APP_ENVIRONMENT = settings.APP_ENVIRONMENT
APP_DEBUG = settings.APP_DEBUG
API_V1_PREFIX = settings.API_V1_PREFIX
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
RATE_LIMIT_PER_MINUTE = settings.RATE_LIMIT_PER_MINUTE
LOGIN_RATE_LIMIT_PER_MINUTE = settings.LOGIN_RATE_LIMIT_PER_MINUTE
MAX_REQUEST_SIZE = settings.MAX_REQUEST_SIZE
DATABASE_POOL_SIZE = settings.DATABASE_POOL_SIZE
DATABASE_MAX_OVERFLOW = settings.DATABASE_MAX_OVERFLOW
DATABASE_POOL_TIMEOUT = settings.DATABASE_POOL_TIMEOUT
DATABASE_CONNECT_TIMEOUT = settings.DATABASE_CONNECT_TIMEOUT
LOG_LEVEL = settings.LOG_LEVEL
AI_MODEL_PATH = settings.AI_MODEL_PATH
AI_CONFIDENCE_THRESHOLD = settings.AI_CONFIDENCE_THRESHOLD
HEALTH_DATA_ENCRYPTION_KEY = settings.HEALTH_DATA_ENCRYPTION_KEY
