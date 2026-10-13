"""
AI Health Surveillance & Early Disease Detection System
-------------------------------------------------------
Regional Disease Risk Assessment Engine

Responsibilities:
- Combine validated surveillance signals.
- Calculate an explainable risk score.
- Classify regional risk.
- Identify missing or unreliable inputs.
- Provide structured results for the dashboard.
- Supply consistent outputs to the recommendation engine.

Security:
- Strict input validation.
- Bounded numeric values.
- No patient-identifying information.
- No arbitrary file loading.
- No automatic public-health orders.

IMPORTANT:
This is an initial decision-support implementation.
Its score is not a probability of infection, an estimate
of transmission, or a clinically validated risk measure.
"""

from __future__ import annotations

import logging
import math

from datetime import date
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


# --------------------------------------------------
# LOGGING
# --------------------------------------------------

logger = logging.getLogger(__name__)


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

# These weights are illustrative starting values.
# Calibrate them using appropriate surveillance data.

OUTBREAK_WEIGHT = 0.35
HOTSPOT_WEIGHT = 0.25
ANOMALY_WEIGHT = 0.20
TREND_WEIGHT = 0.20

RISK_WEIGHTS = {
    "outbreak": OUTBREAK_WEIGHT,
    "hotspot": HOTSPOT_WEIGHT,
    "anomaly": ANOMALY_WEIGHT,
    "trend": TREND_WEIGHT,
}

MAX_TEXT_LENGTH = 150


# --------------------------------------------------
# INPUT SCHEMA
# --------------------------------------------------

class RiskAssessmentRequest(BaseModel):
    """
    Aggregate signals from the surveillance pipeline.

    All component scores must use the same 0-100 scale.

    A score of 100 means the component has reached its
    maximum configured screening score. It does not mean
    a 100% probability of an outbreak.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    disease: str = Field(
        min_length=2,
        max_length=100,
    )

    region_id: str = Field(
        min_length=1,
        max_length=50,
    )

    region_name: str = Field(
        min_length=2,
        max_length=150,
    )

    observation_date: date

    outbreak_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    hotspot_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    anomaly_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    trend_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    outbreak_detected: bool = False

    hotspot_detected: bool = False

    anomaly_detected: bool = False

    trend_increasing: bool = False

    reporting_complete: bool = False

    minimum_data_requirements_met: bool = False

    laboratory_confirmation_available: bool = False

    @field_validator(
        "disease",
        "region_id",
        "region_name",
    )
    @classmethod
    def validate_text(
        cls,
        value: str,
    ) -> str:

        value = value.strip()

        if not value:
            raise ValueError(
                "Text fields cannot be empty."
            )

        if any(
            ord(character) < 32
            for character in value
        ):
            raise ValueError(
                "Control characters are not allowed."
            )

        return value

    @field_validator(
        "outbreak_score",
        "hotspot_score",
        "anomaly_score",
        "trend_score",
    )
    @classmethod
    def validate_finite_scores(
        cls,
        value: float | None,
    ) -> float | None:

        if value is None:
            return None

        if not math.isfinite(value):
            raise ValueError(
                "Scores must be finite numbers."
            )

        return value


# --------------------------------------------------
# OUTPUT SCHEMA
# --------------------------------------------------

class RiskAssessmentResult(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
    )

    disease: str

    region_id: str

    region_name: str

    observation_date: date

    risk_score: float | None

    risk_level: Literal[
        "low",
        "moderate",
        "high",
        "critical",
        "insufficient_data",
    ]

    outbreak_score: float | None

    hotspot_score: float | None

    anomaly_score: float | None

    trend_score: float | None

    signals_detected: list[str]

    contributing_factors: list[str]

    data_quality_warnings: list[str]

    explanation: str

    recommended_review: bool

    laboratory_confirmation_available: bool

    confirmed_outbreak: bool = False

    requires_human_review: bool = True


# --------------------------------------------------
# RISK ENGINE
# --------------------------------------------------

class RiskEngine:
    """
    Combines available surveillance component scores
    using a weighted average.

    Missing scores are not silently replaced with zero.
    Instead, the engine checks data sufficiency before
    producing a numerical result.
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
    ) -> None:

        selected_weights = (
            dict(RISK_WEIGHTS)
            if weights is None
            else dict(weights)
        )

        expected_keys = {
            "outbreak",
            "hotspot",
            "anomaly",
            "trend",
        }

        if set(selected_weights) != expected_keys:
            raise ValueError(
                "Weights must contain exactly: "
                "outbreak, hotspot, anomaly, trend."
            )

        for name, weight in selected_weights.items():

            if (
                not isinstance(weight, (int, float))
                or isinstance(weight, bool)
                or not math.isfinite(weight)
                or weight < 0
            ):
                raise ValueError(
                    f"Invalid weight for {name}."
                )

        total_weight = sum(
            selected_weights.values()
        )

        if total_weight <= 0:
            raise ValueError(
                "At least one risk weight must be positive."
            )

        # Normalize weights so their sum equals 1.
        self.weights = {
            name: weight / total_weight
            for name, weight in selected_weights.items()
        }

    # --------------------------------------------------
    # DATA SUFFICIENCY
    # --------------------------------------------------

    @staticmethod
    def _available_scores(
        data: RiskAssessmentRequest,
    ) -> dict[str, float]:

        scores: dict[str, float] = {}

        candidate_scores = {
            "outbreak": data.outbreak_score,
            "hotspot": data.hotspot_score,
            "anomaly": data.anomaly_score,
            "trend": data.trend_score,
        }

        for name, score in candidate_scores.items():

            if score is not None:
                scores[name] = score

        return scores

    # --------------------------------------------------
    # CALCULATE WEIGHTED RISK
    # --------------------------------------------------

    def _calculate_score(
        self,
        scores: dict[str, float],
    ) -> float:

        available_weight = sum(
            self.weights[name]
            for name in scores
        )

        if available_weight <= 0:
            raise ValueError(
                "No usable risk scores are available."
            )

        weighted_total = sum(
            scores[name] * self.weights[name]
            for name in scores
        )

        # Renormalize using available weights.
        # This is appropriate only when data sufficiency
        # requirements have already been met.
        return weighted_total / available_weight

    # --------------------------------------------------
    # CLASSIFY RISK
    # --------------------------------------------------

    @staticmethod
    def _classify_risk(
        score: float,
    ) -> Literal[
        "low",
        "moderate",
        "high",
        "critical",
    ]:

        if score >= 80:
            return "critical"

        if score >= 60:
            return "high"

        if score >= 35:
            return "moderate"

        return "low"

    # --------------------------------------------------
    # ASSESS ONE REGION
    # --------------------------------------------------

    def assess(
        self,
        data: RiskAssessmentRequest,
    ) -> RiskAssessmentResult:

        scores = self._available_scores(data)

        warnings: list[str] = []

        signals: list[str] = []

        contributing_factors: list[str] = []

        # --------------------------------------------------
        # DATA QUALITY CHECKS
        # --------------------------------------------------

        if not data.reporting_complete:

            warnings.append(
                "Reporting completeness has not been verified."
            )

        if not data.minimum_data_requirements_met:

            warnings.append(
                "Minimum data requirements have not "
                "been confirmed."
            )

        missing_scores = (
            set(self.weights.keys())
            - set(scores.keys())
        )

        if missing_scores:

            warnings.append(
                "Missing component scores: "
                + ", ".join(sorted(missing_scores))
                + "."
            )

        # --------------------------------------------------
        # IDENTIFY DETECTED SIGNALS
        # --------------------------------------------------

        signal_flags = {
            "outbreak": data.outbreak_detected,
            "hotspot": data.hotspot_detected,
            "anomaly": data.anomaly_detected,
            "increasing_trend": data.trend_increasing,
        }

        for signal_name, detected in signal_flags.items():

            if detected:
                signals.append(signal_name)

        # --------------------------------------------------
        # INSUFFICIENT DATA
        # --------------------------------------------------

        # Require at least two independent numerical
        # component scores and confirmation that the
        # pipeline's minimum data requirements are met.
        #
        # These are initial engineering safeguards;
        # production requirements should be calibrated.

        enough_scores = len(scores) >= 2

        data_sufficient = (
            enough_scores
            and data.minimum_data_requirements_met
        )

        if not data_sufficient:

            explanation = (
                "A numerical risk assessment was not "
                "produced because the required data "
                "sufficiency checks were not satisfied. "
                "This does not mean that disease risk is low."
            )

            logger.warning(
                "Risk assessment unavailable: "
                "region_id=%s disease=%s",
                data.region_id,
                data.disease,
            )

            return RiskAssessmentResult(
                disease=data.disease,
                region_id=data.region_id,
                region_name=data.region_name,
                observation_date=data.observation_date,
                risk_score=None,
                risk_level="insufficient_data",
                outbreak_score=data.outbreak_score,
                hotspot_score=data.hotspot_score,
                anomaly_score=data.anomaly_score,
                trend_score=data.trend_score,
                signals_detected=signals,
                contributing_factors=[],
                data_quality_warnings=warnings,
                explanation=explanation,
                recommended_review=True,
                laboratory_confirmation_available=(
                    data.laboratory_confirmation_available
                ),
                confirmed_outbreak=False,
                requires_human_review=True,
            )

        # --------------------------------------------------
        # CALCULATE RISK SCORE
        # --------------------------------------------------

        risk_score = self._calculate_score(
            scores
        )

        risk_level = self._classify_risk(
            risk_score
        )

        # --------------------------------------------------
        # EXPLAIN CONTRIBUTING FACTORS
        # --------------------------------------------------

        for name, score in scores.items():

            if score >= 60:

                contributing_factors.append(
                    f"{name.capitalize()} signal has an "
                    f"elevated component score ({score:.1f}/100)."
                )

        if data.outbreak_detected:

            contributing_factors.append(
                "The outbreak detector flagged a potential "
                "outbreak signal requiring verification."
            )

        if data.hotspot_detected:

            contributing_factors.append(
                "The hotspot detector flagged a potential "
                "geographical concentration of reports."
            )

        if data.anomaly_detected:

            contributing_factors.append(
                "The anomaly detector identified an unusual "
                "reporting pattern."
            )

        if data.trend_increasing:

            contributing_factors.append(
                "The trend analysis indicates increasing "
                "disease reporting."
            )

        if not contributing_factors:

            contributing_factors.append(
                "No individual component crossed the "
                "configured elevated-score threshold."
            )

        # --------------------------------------------------
        # OVERALL EXPLANATION
        # --------------------------------------------------

        explanation = (
            f"The calculated screening score is "
            f"{risk_score:.1f}/100, classified as "
            f"{risk_level.upper()}. "
            "This is a weighted combination of the "
            "available component scores, not a probability "
            "of infection or a confirmed outbreak."
        )

        if warnings:

            explanation += (
                " Data-quality limitations should be "
                "reviewed before interpreting the result."
            )

        # --------------------------------------------------
        # REVIEW DECISION
        # --------------------------------------------------

        # A high score or an explicit detection signal
        # warrants review. Missing reporting completeness
        # also requires attention.

        recommended_review = (
            risk_level in {"high", "critical"}
            or bool(signals)
            or not data.reporting_complete
        )

        logger.info(
            "Risk assessment completed: "
            "region_id=%s disease=%s level=%s",
            data.region_id,
            data.disease,
            risk_level,
        )

        return RiskAssessmentResult(
            disease=data.disease,
            region_id=data.region_id,
            region_name=data.region_name,
            observation_date=data.observation_date,
            risk_score=round(risk_score, 2),
            risk_level=risk_level,
            outbreak_score=data.outbreak_score,
            hotspot_score=data.hotspot_score,
            anomaly_score=data.anomaly_score,
            trend_score=data.trend_score,
            signals_detected=signals,
            contributing_factors=contributing_factors,
            data_quality_warnings=warnings,
            explanation=explanation,
            recommended_review=recommended_review,
            laboratory_confirmation_available=(
                data.laboratory_confirmation_available
            ),
            confirmed_outbreak=False,
            requires_human_review=True,
        )


# --------------------------------------------------
# SHARED ENGINE INSTANCE
# --------------------------------------------------

risk_engine = RiskEngine()


# --------------------------------------------------
# PUBLIC HELPER FUNCTION
# --------------------------------------------------

def assess_risk(
    data: RiskAssessmentRequest,
) -> RiskAssessmentResult:

    return risk_engine.assess(data)