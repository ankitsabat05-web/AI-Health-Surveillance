from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)


class TrendForecastRequest(BaseModel):
    """Historical disease-count input for a short-term forecast."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    region: str = Field(..., min_length=2, max_length=80)
    disease: str = Field(..., min_length=2, max_length=80)
    historical_cases: list[int] = Field(
        ...,
        min_length=2,
        max_length=24,
        description="Daily, weekly, or monthly counts ordered from oldest to newest.",
    )
    forecast_weeks: int = Field(default=4, ge=1, le=52)

    @field_validator("historical_cases")
    @classmethod
    def validate_historical_cases(cls, values: list[int]) -> list[int]:
        cleaned: list[int] = []

        for value in values:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("Historical cases must be integers.")
            if value < 0:
                raise ValueError("Historical cases cannot be negative.")
            cleaned.append(value)

        if len(cleaned) < 2:
            raise ValueError("At least two historical case counts are required.")

        return cleaned


class TrendForecastResult(BaseModel):
    """Simple short-term forecast result."""

    model_config = ConfigDict(extra="forbid")

    region: str
    disease: str
    current_cases: int
    projected_cases: int
    trend_direction: Literal["rising", "stable", "declining"]
    confidence: Literal["low", "medium", "high"]
    summary: str


def forecast_disease_trend(
    request: TrendForecastRequest,
) -> TrendForecastResult:
    """Project recent disease counts forward using a basic linear trend."""

    if not request.historical_cases:
        raise ValueError("Historical case counts are required.")

    current_cases = request.historical_cases[-1]

    if len(request.historical_cases) > 1:
        recent_changes = [
            current - previous
            for previous, current in zip(
                request.historical_cases,
                request.historical_cases[1:],
            )
        ]
        average_change = sum(recent_changes) / len(recent_changes)
    else:
        average_change = 0.0

    projected_cases = max(0, round(current_cases + (average_change * request.forecast_weeks)))

    if average_change > 0:
        trend_direction = "rising"
    elif average_change < 0:
        trend_direction = "declining"
    else:
        trend_direction = "stable"

    if len(request.historical_cases) >= 6 and abs(average_change) > 0:
        confidence = "high"
    elif len(request.historical_cases) >= 3:
        confidence = "medium"
    else:
        confidence = "low"

    summary = (
        f"{request.region} shows a {trend_direction} trend for {request.disease} with "
        f"an estimated {projected_cases} cases in {request.forecast_weeks} weeks."
    )

    return TrendForecastResult(
        region=request.region,
        disease=request.disease,
        current_cases=current_cases,
        projected_cases=projected_cases,
        trend_direction=trend_direction,
        confidence=confidence,
        summary=summary,
    )
