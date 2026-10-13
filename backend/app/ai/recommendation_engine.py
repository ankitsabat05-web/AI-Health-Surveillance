"""
AI Health Surveillance & Early Disease Detection System
-------------------------------------------------------
Public Health Recommendation Engine

Responsibilities:
- Generate recommendations from surveillance signals.
- Prioritize potential outbreak responses.
- Provide disease-specific prevention guidance.
- Produce structured recommendations for dashboards.
- Explain why each recommendation was generated.

Security:
- Strict input validation.
- No arbitrary code execution.
- No patient-identifying information.
- Bounded input sizes.
- No unrestricted LLM-generated medical advice.

IMPORTANT:
This module provides decision support only.
Recommendations require appropriate human review.
It does not diagnose patients or declare outbreaks.
"""

from __future__ import annotations

import logging

from collections.abc import Sequence
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

MAX_RECOMMENDATIONS = 10

MAX_TEXT_LENGTH = 150

SUPPORTED_SEVERITIES = {
    "normal",
    "watch",
    "elevated",
    "high",
    "critical",
    "insufficient_data",
}


# --------------------------------------------------
# INPUT SCHEMA
# --------------------------------------------------

class RecommendationRequest(BaseModel):
    """
    Aggregate surveillance information used to generate
    public-health recommendations.

    Do not pass names, phone numbers, addresses,
    patient IDs, or other identifying information.
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

    severity: Literal[
        "normal",
        "watch",
        "elevated",
        "high",
        "critical",
        "insufficient_data",
    ]

    potential_outbreak: bool = False

    hotspot_detected: bool = False

    increase_percentage: float | None = Field(
        default=None,
        ge=-100,
        le=1_000_000,
    )

    current_cases: int = Field(
        default=0,
        ge=0,
        le=1_000_000_000,
    )

    population: int | None = Field(
        default=None,
        gt=0,
        le=2_000_000_000,
    )

    reporting_complete: bool = False

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


# --------------------------------------------------
# OUTPUT SCHEMA
# --------------------------------------------------

class Recommendation(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
    )

    title: str = Field(
        max_length=150,
    )

    description: str = Field(
        max_length=1000,
    )

    priority: Literal[
        "low",
        "medium",
        "high",
        "urgent",
    ]

    category: Literal[
        "surveillance",
        "investigation",
        "prevention",
        "communication",
        "data_quality",
        "clinical_review",
    ]

    reason: str = Field(
        max_length=500,
    )

    requires_official_review: bool = True


class RecommendationResponse(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
    )

    disease: str

    region_id: str

    region_name: str

    overall_priority: Literal[
        "low",
        "medium",
        "high",
        "urgent",
    ]

    potential_outbreak: bool

    recommendations: list[Recommendation] = Field(
        max_length=MAX_RECOMMENDATIONS,
    )

    summary: str

    requires_human_review: bool = True

    automated_outbreak_declaration: bool = False


# --------------------------------------------------
# RECOMMENDATION ENGINE
# --------------------------------------------------

class RecommendationEngine:
    """
    Generates explainable recommendations using
    validated public-health surveillance rules.

    The engine does not independently diagnose diseases,
    prescribe medication, or authorize interventions.
    """

    def __init__(self) -> None:

        self._disease_rules = {
            "dengue": [
                {
                    "title": "Review mosquito-control measures",
                    "description": (
                        "Ask the responsible public-health "
                        "team to review local mosquito-breeding "
                        "prevention and vector-control activities."
                    ),
                    "category": "prevention",
                    "reason": (
                        "Dengue surveillance may warrant "
                        "review of mosquito exposure and "
                        "vector-control measures."
                    ),
                },
                {
                    "title": "Review local case distribution",
                    "description": (
                        "Review aggregate reports by locality "
                        "and observation period to identify "
                        "areas requiring further investigation."
                    ),
                    "category": "surveillance",
                    "reason": (
                        "Geographical concentration may help "
                        "officials prioritize surveillance."
                    ),
                },
            ],

            "malaria": [
                {
                    "title": "Review local vector-control activity",
                    "description": (
                        "Ask public-health officials to review "
                        "appropriate mosquito-control and "
                        "prevention activities."
                    ),
                    "category": "prevention",
                    "reason": (
                        "Elevated malaria reporting may warrant "
                        "review of local transmission risks."
                    ),
                },
                {
                    "title": "Verify reported cases",
                    "description": (
                        "Review case definitions, diagnostic "
                        "records, reporting dates, and available "
                        "laboratory evidence through authorized "
                        "public-health channels."
                    ),
                    "category": "investigation",
                    "reason": (
                        "Verified information supports more "
                        "reliable surveillance decisions."
                    ),
                },
            ],

            "influenza": [
                {
                    "title": "Review respiratory illness trends",
                    "description": (
                        "Review aggregate respiratory illness "
                        "reports and applicable local surveillance "
                        "guidance."
                    ),
                    "category": "surveillance",
                    "reason": (
                        "Increasing respiratory illness reports "
                        "may warrant closer monitoring."
                    ),
                },
                {
                    "title": "Review healthcare service readiness",
                    "description": (
                        "Ask responsible health services to review "
                        "staffing, supplies, and service capacity "
                        "against applicable local guidance."
                    ),
                    "category": "clinical_review",
                    "reason": (
                        "Changes in illness activity can affect "
                        "healthcare demand."
                    ),
                },
            ],

            "covid-19": [
                {
                    "title": "Review respiratory surveillance",
                    "description": (
                        "Review aggregate respiratory illness "
                        "reports, available laboratory results, "
                        "and current public-health guidance."
                    ),
                    "category": "surveillance",
                    "reason": (
                        "An increase in reports may require "
                        "additional surveillance."
                    ),
                },
                {
                    "title": "Review public communication",
                    "description": (
                        "Check whether locally approved infection "
                        "prevention guidance should be communicated "
                        "through official channels."
                    ),
                    "category": "communication",
                    "reason": (
                        "Accurate communication can help the "
                        "community follow current guidance."
                    ),
                },
            ],
        }

    # --------------------------------------------------
    # BUILD A RECOMMENDATION
    # --------------------------------------------------

    @staticmethod
    def _make_recommendation(
        title: str,
        description: str,
        priority: str,
        category: str,
        reason: str,
    ) -> Recommendation:

        return Recommendation(
            title=title,
            description=description,
            priority=priority,
            category=category,
            reason=reason,
            requires_official_review=True,
        )

    # --------------------------------------------------
    # GENERATE RECOMMENDATIONS
    # --------------------------------------------------

    def generate(
        self,
        data: RecommendationRequest,
    ) -> RecommendationResponse:

        recommendations: list[Recommendation] = []

        severity = data.severity

        # --------------------------------------------------
        # DETERMINE OVERALL PRIORITY
        # --------------------------------------------------

        if severity == "critical":

            overall_priority = "urgent"

        elif severity == "high":

            overall_priority = "high"

        elif severity in {"elevated", "watch"}:

            overall_priority = "medium"

        else:

            overall_priority = "low"

        if data.potential_outbreak and (
            overall_priority == "low"
        ):

            overall_priority = "medium"

        # --------------------------------------------------
        # DATA QUALITY
        # --------------------------------------------------

        if not data.reporting_complete:

            recommendations.append(
                self._make_recommendation(
                    title="Verify reporting completeness",
                    description=(
                        "Ask the authorized surveillance team "
                        "to check reporting delays, missing "
                        "submissions, duplicate records, and "
                        "consistency of the observation period."
                    ),
                    priority="high",
                    category="data_quality",
                    reason=(
                        "Incomplete data can distort trend "
                        "analysis and hotspot classification."
                    ),
                )
            )

        # --------------------------------------------------
        # OUTBREAK INVESTIGATION
        # --------------------------------------------------

        if data.potential_outbreak:

            recommendations.append(
                self._make_recommendation(
                    title="Initiate public-health review",
                    description=(
                        "Refer the signal to the authorized "
                        "public-health team for verification "
                        "and assessment under applicable "
                        "surveillance procedures."
                    ),
                    priority=(
                        "urgent"
                        if severity == "critical"
                        else "high"
                    ),
                    category="investigation",
                    reason=(
                        "The surveillance engine flagged a "
                        "potential outbreak signal. Automated "
                        "screening does not confirm an outbreak."
                    ),
                )
            )

        # --------------------------------------------------
        # HOTSPOT RESPONSE
        # --------------------------------------------------

        if data.hotspot_detected:

            recommendations.append(
                self._make_recommendation(
                    title="Review geographical disease concentration",
                    description=(
                        "Examine aggregate disease-reporting "
                        "patterns across affected and neighboring "
                        "areas, while checking population estimates "
                        "and reporting completeness."
                    ),
                    priority="high",
                    category="surveillance",
                    reason=(
                        "The hotspot detector identified a "
                        "potentially elevated regional reporting rate."
                    ),
                )
            )

        # --------------------------------------------------
        # SEVERITY-BASED ACTIONS
        # --------------------------------------------------

        if severity == "critical":

            recommendations.append(
                self._make_recommendation(
                    title="Escalate for urgent official assessment",
                    description=(
                        "Notify the designated surveillance "
                        "authority through the approved alerting "
                        "workflow. Follow established escalation "
                        "procedures and verify the underlying data."
                    ),
                    priority="urgent",
                    category="communication",
                    reason=(
                        "The surveillance system classified "
                        "the signal as critical. Human review "
                        "is required before action is authorized."
                    ),
                )
            )

        elif severity == "high":

            recommendations.append(
                self._make_recommendation(
                    title="Increase surveillance review",
                    description=(
                        "Ask the responsible team to review "
                        "recent reports more frequently and "
                        "assess whether additional investigation "
                        "is warranted."
                    ),
                    priority="high",
                    category="surveillance",
                    reason=(
                        "The observed signal meets the configured "
                        "high-severity screening criteria."
                    ),
                )
            )

        elif severity in {"elevated", "watch"}:

            recommendations.append(
                self._make_recommendation(
                    title="Continue enhanced monitoring",
                    description=(
                        "Monitor incoming aggregate reports "
                        "and compare them with historical "
                        "patterns using comparable time periods."
                    ),
                    priority="medium",
                    category="surveillance",
                    reason=(
                        "The current signal warrants monitoring "
                        "but does not independently establish "
                        "an outbreak."
                    ),
                )
            )

        elif severity == "insufficient_data":

            recommendations.append(
                self._make_recommendation(
                    title="Improve surveillance data coverage",
                    description=(
                        "Review whether the available number "
                        "of reports is sufficient for reliable "
                        "interpretation. Check reporting coverage "
                        "before concluding that risk is low."
                    ),
                    priority="medium",
                    category="data_quality",
                    reason=(
                        "Insufficient observations can limit "
                        "the reliability of automated screening."
                    ),
                )
            )

        # --------------------------------------------------
        # DISEASE-SPECIFIC GUIDANCE
        # --------------------------------------------------

        disease_key = data.disease.casefold().strip()

        disease_rules = self._disease_rules.get(
            disease_key,
            [],
        )

        for rule in disease_rules:

            recommendations.append(
                self._make_recommendation(
                    title=rule["title"],
                    description=rule["description"],
                    priority=(
                        "high"
                        if severity in {"high", "critical"}
                        else "medium"
                    ),
                    category=rule["category"],
                    reason=rule["reason"],
                )
            )

        # --------------------------------------------------
        # LABORATORY / CASE VERIFICATION
        # --------------------------------------------------

        if (
            data.potential_outbreak
            and not data.laboratory_confirmation_available
        ):

            recommendations.append(
                self._make_recommendation(
                    title="Review diagnostic confirmation status",
                    description=(
                        "Determine whether appropriate diagnostic "
                        "or laboratory confirmation is available "
                        "under the relevant disease-surveillance "
                        "protocol. Do not delay urgent assessment "
                        "when established protocols require it."
                    ),
                    priority="high",
                    category="investigation",
                    reason=(
                        "The system has flagged a potential "
                        "outbreak, but laboratory confirmation "
                        "is not recorded as available."
                    ),
                )
            )

        # --------------------------------------------------
        # COMMUNITY COMMUNICATION
        # --------------------------------------------------

        if (
            data.potential_outbreak
            or data.hotspot_detected
        ):

            recommendations.append(
                self._make_recommendation(
                    title="Review community communication needs",
                    description=(
                        "Ask authorized health officials whether "
                        "locally appropriate, evidence-based "
                        "prevention guidance should be shared "
                        "through verified public communication "
                        "channels."
                    ),
                    priority="medium",
                    category="communication",
                    reason=(
                        "A potential surveillance signal may "
                        "warrant clear and accurate public guidance."
                    ),
                )
            )

        # --------------------------------------------------
        # LIMIT OUTPUT SIZE
        # --------------------------------------------------

        priority_order = {
            "urgent": 0,
            "high": 1,
            "medium": 2,
            "low": 3,
        }

        recommendations.sort(
            key=lambda recommendation: (
                priority_order[recommendation.priority],
                recommendation.category,
                recommendation.title,
            )
        )

        recommendations = recommendations[
            :MAX_RECOMMENDATIONS
        ]

        # --------------------------------------------------
        # SUMMARY
        # --------------------------------------------------

        if data.potential_outbreak:

            summary = (
                f"A potential {data.disease} outbreak "
                f"signal was flagged for {data.region_name}. "
                "The signal requires verification and "
                "assessment by authorized public-health officials."
            )

        elif data.hotspot_detected:

            summary = (
                f"A potential geographical hotspot was "
                f"identified for {data.disease} in "
                f"{data.region_name}. Review the underlying "
                "data and local conditions."
            )

        elif severity == "insufficient_data":

            summary = (
                f"There is insufficient surveillance data "
                f"to confidently assess {data.disease} "
                f"reporting patterns in {data.region_name}."
            )

        else:

            summary = (
                f"No outbreak signal was supplied to the "
                f"recommendation engine for {data.disease} "
                f"in {data.region_name}. Continue routine "
                "surveillance and data-quality checks."
            )

        logger.info(
            "Recommendations generated: "
            "region_id=%s disease=%s priority=%s count=%d",
            data.region_id,
            data.disease,
            overall_priority,
            len(recommendations),
        )

        return RecommendationResponse(
            disease=data.disease,
            region_id=data.region_id,
            region_name=data.region_name,
            overall_priority=overall_priority,
            potential_outbreak=data.potential_outbreak,
            recommendations=recommendations,
            summary=summary,
            requires_human_review=True,
            automated_outbreak_declaration=False,
        )


# --------------------------------------------------
# REUSABLE ENGINE INSTANCE
# --------------------------------------------------

recommendation_engine = RecommendationEngine()


# --------------------------------------------------
# PUBLIC HELPER FUNCTION
# --------------------------------------------------

def generate_recommendations(
    data: RecommendationRequest,
) -> RecommendationResponse:

    return recommendation_engine.generate(data)