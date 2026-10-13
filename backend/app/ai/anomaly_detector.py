"""
AI Health Surveillance & Early Disease Detection System
-------------------------------------------------------
Anomaly Detection Engine

Purpose:
- Detect unusual increases in disease reports.
- Identify unexpected changes in regional case counts.
- Compare current counts against historical baselines.
- Generate explainable anomaly alerts.
- Provide structured output for the government dashboard.

Security:
- Strict input validation.
- No patient-identifying information in outputs.
- Bounded historical data.
- Safe handling of invalid numeric values.

Performance:
- NumPy-based statistical calculations.
- No model training during API requests.
- Lightweight calculations suitable for frequent execution.

IMPORTANT:
An anomaly indicates unusual reporting activity.
It does not establish a confirmed disease outbreak.
"""

from __future__ import annotations

import logging
import math

from collections.abc import Sequence
from datetime import date
from statistics import median
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# --------------------------------------------------
# LOGGING
# --------------------------------------------------

logger = logging.getLogger(__name__)


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

MIN_HISTORY_POINTS = 7
MAX_HISTORY_POINTS = 365

DEFAULT_MIN_CASE_COUNT = 5
DEFAULT_Z_SCORE_THRESHOLD = 3.5

MAX_CASE_COUNT = 1_000_000_000


# --------------------------------------------------
# INPUT SCHEMAS
# --------------------------------------------------

class DiseaseObservation(BaseModel):
    """
    Aggregate disease-report counts for a region.

    Example:
        disease = "dengue"
        region = "District A"
        current_cases = 42
        historical_cases = [8, 10, 9, 11, 12, 10, 9]
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    disease: str = Field(
        min_length=2,
        max_length=100,
    )

    region: str = Field(
        min_length=2,
        max_length=150,
    )

    observation_date: date

    current_cases: int = Field(
        ge=0,
        le=MAX_CASE_COUNT,
    )

    historical_cases: list[int] = Field(
        min_length=MIN_HISTORY_POINTS,
        max_length=MAX_HISTORY_POINTS,
    )

    @field_validator("disease", "region")
    @classmethod
    def validate_text(
        cls,
        value: str,
    ) -> str:

        if not value.strip():
            raise ValueError(
                "This field cannot be empty."
            )

        if any(ord(character) < 32 for character in value):
            raise ValueError(
                "Control characters are not permitted."
            )

        return value

    @field_validator("historical_cases")
    @classmethod
    def validate_historical_counts(
        cls,
        values: list[int],
    ) -> list[int]:

        for value in values:
            if not isinstance(value, int) or isinstance(
                value, bool
            ):
                raise ValueError(
                    "Historical case counts must be integers."
                )

            if value < 0 or value > MAX_CASE_COUNT:
                raise ValueError(
                    "Historical case count is outside "
                    "the permitted range."
                )

        return values

    @model_validator(mode="after")
    def validate_history(self):
        if not self.historical_cases:
            raise ValueError(
                "Historical observations are required."
            )

        return self


# --------------------------------------------------
# OUTPUT SCHEMA
# --------------------------------------------------

class AnomalyResult(BaseModel):
    """
    Explainable anomaly result for a dashboard or
    downstream alerting service.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    disease: str
    region: str
    observation_date: date

    current_cases: int
    historical_average: float
    historical_median: float
    historical_std_dev: float

    absolute_z_score: float
    modified_z_score: float

    increase_percentage: float | None

    anomaly_detected: bool

    severity: Literal[
        "normal",
        "watch",
        "elevated",
        "high",
        "critical",
    ]

    explanation: str

    requires_review: bool = True


# --------------------------------------------------
# ANOMALY DETECTOR
# --------------------------------------------------

class AnomalyDetector:
    """
    Statistical anomaly detector for aggregate
    public-health surveillance data.

    The detector does not diagnose individuals.

    A result should be reviewed alongside:
    - Reporting completeness.
    - Population size.
    - Historical seasonality.
    - Laboratory confirmation.
    - Data quality.
    """

    def __init__(
        self,
        z_score_threshold: float = (
            DEFAULT_Z_SCORE_THRESHOLD
        ),
        min_case_count: int = (
            DEFAULT_MIN_CASE_COUNT
        ),
    ) -> None:

        if (
            not math.isfinite(z_score_threshold)
            or z_score_threshold <= 0
        ):
            raise ValueError(
                "Z-score threshold must be positive "
                "and finite."
            )

        if (
            not isinstance(min_case_count, int)
            or isinstance(min_case_count, bool)
            or min_case_count < 1
        ):
            raise ValueError(
                "Minimum case count must be a "
                "positive integer."
            )

        self.z_score_threshold = z_score_threshold
        self.min_case_count = min_case_count

    # --------------------------------------------------
    # SAFE NUMERIC HELPERS
    # --------------------------------------------------

    @staticmethod
    def _safe_round(
        value: float,
        digits: int = 3,
    ) -> float:

        if not math.isfinite(value):
            return 0.0

        return round(value, digits)

    @staticmethod
    def _calculate_mean(
        values: Sequence[int],
    ) -> float:

        if not values:
            return 0.0

        return sum(values) / len(values)

    @staticmethod
    def _calculate_std_dev(
        values: Sequence[int],
    ) -> float:
        """
        Calculate population standard deviation.

        Population standard deviation is used here
        because the historical observations represent
        the supplied reference period.
        """

        if not values:
            return 0.0

        mean_value = sum(values) / len(values)

        variance = sum(
            (value - mean_value) ** 2
            for value in values
        ) / len(values)

        return math.sqrt(variance)

    @staticmethod
    def _calculate_mad(
        values: Sequence[int],
    ) -> float:
        """
        Median absolute deviation.

        MAD is less sensitive to historical outliers
        than standard deviation.
        """

        if not values:
            return 0.0

        median_value = median(values)

        deviations = [
            abs(value - median_value)
            for value in values
        ]

        return float(median(deviations))

    # --------------------------------------------------
    # SEVERITY CLASSIFICATION
    # --------------------------------------------------

    @staticmethod
    def _classify_severity(
        anomaly_detected: bool,
        z_score: float,
        current_cases: int,
    ) -> Literal[
        "normal",
        "watch",
        "elevated",
        "high",
        "critical",
    ]:
        """
        Classify statistical deviations.

        These are operational screening categories,
        not validated medical severity classifications.
        """

        if not anomaly_detected:
            if z_score >= 2.0:
                return "watch"

            return "normal"

        if z_score >= 8.0 and current_cases >= 20:
            return "critical"

        if z_score >= 6.0:
            return "high"

        if z_score >= 4.5:
            return "elevated"

        return "watch"

    # --------------------------------------------------
    # CORE DETECTION
    # --------------------------------------------------

    def detect(
        self,
        observation: DiseaseObservation,
    ) -> AnomalyResult:
        """
        Analyze one regional disease observation.

        Returns an explainable result based on
        historical aggregate counts.
        """

        history = observation.historical_cases
        current = observation.current_cases

        historical_average = self._calculate_mean(
            history
        )

        historical_median = float(
            median(history)
        )

        standard_deviation = self._calculate_std_dev(
            history
        )

        mad = self._calculate_mad(history)

        # --------------------------------------------------
        # STANDARD Z-SCORE
        # --------------------------------------------------

        if standard_deviation > 0:
            z_score = (
                current - historical_average
            ) / standard_deviation

        else:
            z_score = (
                0.0
                if current == historical_average
                else math.inf
            )

        # --------------------------------------------------
        # MODIFIED Z-SCORE
        # --------------------------------------------------

        # For normally distributed observations,
        # 0.6745 is the standard MAD adjustment factor.
        #
        # When MAD is zero, the modified Z-score is
        # undefined. We handle this explicitly rather
        # than silently dividing by zero.

        if mad > 0:
            modified_z_score = (
                0.6745
                * (current - historical_median)
                / mad
            )

        else:
            modified_z_score = (
                0.0
                if current == historical_median
                else math.inf
            )

        # --------------------------------------------------
        # HANDLE DEGENERATE HISTORICAL BASELINES
        # --------------------------------------------------

        baseline_is_degenerate = (
            standard_deviation == 0
            and mad == 0
        )

        if baseline_is_degenerate:
            # A change from a constant historical count
            # is unusual, but the score is not a calibrated
            # probability or statistical significance test.
            anomaly_detected = (
                current != historical_median
                and current >= self.min_case_count
            )

        else:
            anomaly_detected = (
                current >= self.min_case_count
                and (
                    abs(z_score)
                    >= self.z_score_threshold
                    or abs(modified_z_score)
                    >= self.z_score_threshold
                )
            )

        # --------------------------------------------------
        # PERCENTAGE CHANGE
        # --------------------------------------------------

        if historical_average > 0:
            increase_percentage = (
                (
                    current - historical_average
                )
                / historical_average
            ) * 100.0

        elif current == 0:
            increase_percentage = 0.0

        else:
            # A percentage increase from zero has
            # no finite mathematical value.
            increase_percentage = None

        # --------------------------------------------------
        # NORMALIZE SCORES FOR JSON OUTPUT
        # --------------------------------------------------

        if not math.isfinite(z_score):
            reported_z_score = 0.0
        else:
            reported_z_score = self._safe_round(
                abs(z_score)
            )

        if not math.isfinite(modified_z_score):
            reported_modified_z_score = 0.0
        else:
            reported_modified_z_score = (
                self._safe_round(
                    abs(modified_z_score)
                )
            )

        # Use the larger finite score for the
        # operational severity classification.
        effective_score = max(
            reported_z_score,
            reported_modified_z_score,
        )

        severity = self._classify_severity(
            anomaly_detected=anomaly_detected,
            z_score=effective_score,
            current_cases=current,
        )

        # --------------------------------------------------
        # EXPLANATION
        # --------------------------------------------------

        if anomaly_detected:

            if increase_percentage is None:
                change_description = (
                    "The historical average was zero."
                )

            elif increase_percentage >= 0:
                change_description = (
                    f"Reports are {increase_percentage:.1f}% "
                    "above the historical average."
                )

            else:
                change_description = (
                    f"Reports are "
                    f"{abs(increase_percentage):.1f}% "
                    "below the historical average."
                )

            explanation = (
                f"An unusual reporting pattern was detected "
                f"for {observation.disease} in "
                f"{observation.region}. "
                f"Current reports: {current}; "
                f"historical average: "
                f"{historical_average:.2f}. "
                f"{change_description} "
                "Review reporting completeness, "
                "seasonality, and clinical evidence."
            )

        elif severity == "watch":

            explanation = (
                f"Reports for {observation.disease} in "
                f"{observation.region} are approaching "
                "the configured anomaly threshold. "
                "Continue monitoring."
            )

        else:

            explanation = (
                f"No statistical anomaly was detected "
                f"for {observation.disease} in "
                f"{observation.region} using the "
                "configured baseline and thresholds."
            )

        # Do not log patient-level information.
        # This detector only accepts aggregate counts.

        return AnomalyResult(
            disease=observation.disease,
            region=observation.region,
            observation_date=(
                observation.observation_date
            ),
            current_cases=current,
            historical_average=self._safe_round(
                historical_average
            ),
            historical_median=self._safe_round(
                historical_median
            ),
            historical_std_dev=self._safe_round(
                standard_deviation
            ),
            absolute_z_score=reported_z_score,
            modified_z_score=(
                reported_modified_z_score
            ),
            increase_percentage=(
                self._safe_round(
                    increase_percentage
                )
                if increase_percentage is not None
                else None
            ),
            anomaly_detected=anomaly_detected,
            severity=severity,
            explanation=explanation,
            requires_review=anomaly_detected,
        )


# --------------------------------------------------
# REUSABLE DETECTOR INSTANCE
# --------------------------------------------------

anomaly_detector = AnomalyDetector()


# --------------------------------------------------
# SIMPLE HELPER FUNCTION
# --------------------------------------------------

def detect_disease_anomaly(
    observation: DiseaseObservation,
) -> AnomalyResult:
    """
    Convenience function for API routes and services.

    Example:
        result = detect_disease_anomaly(observation)
    """

    return anomaly_detector.detect(observation)