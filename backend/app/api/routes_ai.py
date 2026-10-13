from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from app.ai.symptom_analyzer import (
    SymptomAnalysisRequest,
    SymptomAnalysisResponse,
    analyze_symptoms,
)

from app.ai.trend_forecaster import (
    TrendForecastRequest,
    TrendForecastResult,
    forecast_disease_trend,
)

from app.ai.outbreak_detector import (
    OutbreakDetectionRequest,
    OutbreakDetectionResult,
    detect_outbreak,
)

from app.ai.hotspot_detector import (
    RegionalHealthData,
    HotspotResult,
    detect_hotspot,
)

from app.ai.risk_engine import (
    RiskAssessmentRequest,
    RiskAssessmentResult,
    assess_risk,
)

from app.ai.recommendation_engine import (
    RecommendationRequest,
    RecommendationResponse,
    generate_recommendations,
)

# Adapt these imports to the actual security modules in your project.
from app.security.authentication import get_current_user
from app.security.authorization import require_health_official

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/ai",
    tags=["AI Health Intelligence"],
)

AuthenticatedUser = Annotated[
    object,
    Depends(get_current_user),
]

HealthOfficial = Annotated[
    object,
    Depends(require_health_official),
]


# ============================================================
# RESPONSE SCHEMAS
# ============================================================

class AIHealthResponse(BaseModel):
    """Basic response for checking AI service availability."""

    model_config = ConfigDict(extra="forbid")

    service: str
    status: str
    available_modules: list[str]


class AIErrorResponse(BaseModel):
    """Safe API error response."""

    model_config = ConfigDict(extra="forbid")

    detail: str


class AIInputSummary(BaseModel):
    """Non-identifying summary of an AI operation."""

    model_config = ConfigDict(extra="forbid")

    operation: str
    status: str
    requires_human_review: bool = True


# ============================================================
# SERVICE HEALTH
# ============================================================

@router.get(
    "/health",
    response_model=AIHealthResponse,
)
def get_ai_health(
    current_user: AuthenticatedUser,
) -> AIHealthResponse:
    """
    Report whether the AI API layer is reachable.

    This does not guarantee that an external model or database
    is loaded and healthy.
    """

    return AIHealthResponse(
        service="AI Health Surveillance",
        status="available",
        available_modules=[
            "symptom_analyzer",
            "trend_forecaster",
            "outbreak_detector",
            "hotspot_detector",
            "risk_engine",
            "recommendation_engine",
        ],
    )


# ============================================================
# 1. SYMPTOM ANALYSIS
# ============================================================

@router.post(
    "/symptoms/analyze",
    response_model=SymptomAnalysisResponse,
)
def analyze_user_symptoms(
    request: SymptomAnalysisRequest,
    current_user: AuthenticatedUser,
) -> SymptomAnalysisResponse:
    """
    Analyze submitted symptoms.

    This provides preliminary screening, not a diagnosis.
    """

    try:
        return analyze_symptoms(request)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception("Symptom analysis failed.")

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Symptom analysis is temporarily unavailable.",
        ) from exc


# ============================================================
# 2. HISTORICAL DISEASE TREND FORECASTING
# ============================================================

@router.post(
    "/trends/forecast",
    response_model=TrendForecastResult,
)
def forecast_health_trend(
    request: TrendForecastRequest,
    current_user: HealthOfficial,
) -> TrendForecastResult:
    """
    Forecast a trend from historical disease counts.

    Restricted to authorized health officials because the
    endpoint accepts regional public-health surveillance data.
    """

    try:
        return forecast_disease_trend(request)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception("Disease trend forecasting failed.")

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Disease trend forecasting is temporarily unavailable.",
        ) from exc


# ============================================================
# 3. OUTBREAK SIGNAL DETECTION
# ============================================================

@router.post(
    "/outbreaks/analyze",
    response_model=OutbreakDetectionResult,
)
def analyze_outbreak_signals(
    request: OutbreakDetectionRequest,
    current_user: HealthOfficial,
) -> OutbreakDetectionResult:
    """
    Identify possible unusual increases in reported disease cases.

    The result is a screening signal, not a confirmed outbreak.
    """

    try:
        return detect_outbreak(request)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception("Outbreak signal analysis failed.")

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Outbreak analysis is temporarily unavailable.",
        ) from exc


# ============================================================
# 4. REGIONAL HOTSPOT DETECTION
# ============================================================

@router.post(
    "/hotspots/analyze",
    response_model=HotspotResult,
)
def analyze_health_hotspot(
    request: RegionalHealthData,
    current_user: HealthOfficial,
) -> HotspotResult:
    """
    Screen regional case counts for potential hotspots.

    Only authorized officials may submit regional surveillance
    data to this endpoint.
    """

    try:
        return detect_hotspot(request)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception("Hotspot analysis failed.")

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hotspot analysis is temporarily unavailable.",
        ) from exc


# ============================================================
# 5. RISK ASSESSMENT
# ============================================================

@router.post(
    "/risk/assess",
    response_model=RiskAssessmentResult,
)
def assess_public_health_risk(
    request: RiskAssessmentRequest,
    current_user: HealthOfficial,
) -> RiskAssessmentResult:
    """
    Assess preliminary public-health risk using component scores.

    IMPORTANT:
    In production, do not accept trusted component scores or
    data-quality flags directly from an untrusted client.

    The backend should assemble this request using validated
    outputs from the outbreak, hotspot, anomaly, and trend
    analysis services.
    """

    try:
        return assess_risk(request)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception("Public-health risk assessment failed.")

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Risk assessment is temporarily unavailable.",
        ) from exc


# ============================================================
# 6. HEALTH RESPONSE RECOMMENDATIONS
# ============================================================

@router.post(
    "/recommendations",
    response_model=RecommendationResponse,
)
def get_health_recommendations(
    request: RecommendationRequest,
    current_user: HealthOfficial,
) -> RecommendationResponse:
    """
    Generate preliminary recommendations for official review.

    Recommendations should be based on validated backend analysis,
    not on unverified risk scores supplied by a frontend client.
    """

    try:
        return generate_recommendations(request)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception("Recommendation generation failed.")

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Recommendation generation is temporarily unavailable.",
        ) from exc