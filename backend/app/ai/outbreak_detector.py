"""
AI Health Surveillance & Early Disease Detection System
-------------------------------------------------------
Potential Outbreak Detection Engine

Responsibilities:
- Analyze current disease-report counts.
- Compare current counts with historical observations.
- Calculate reporting-rate changes.
- Detect sustained increases across recent observations.
- Identify signals requiring public-health review.
- Return explainable, structured results.

Security:
- Strict Pydantic input validation.
- Bounded historical data.
- No patient-identifying information.
- No dynamic code execution or arbitrary file loading.

Performance:
- Lightweight statistical calculations.
- No model training during requests.
- No external API calls.

IMPORTANT:
This is a preliminary screening component.
Its output does not confirm an outbreak or establish
that disease transmission is occurring.
"""

from __future__ import annotations

import logging
import math

from collections.abc import Sequence
from datetime import date
from statistics import mean

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
MAX_HISTORY_POINTS = 90
MAX_BATCH_SIZE = 10_000

DEFAULT_MIN_CASES = 5
DEFAULT_SPIKE_RATIO = 2.0
DEFAULT_MIN_INCREASE_PERCENT = 50.0
DEFAULT_SUSTAINED_PERIODS = 3

# Initial screening thresholds only.
# Calibrate them against real epidemiological data
# before deployment in a public-health setting.


# --------------------------------------------------
# INPUT SCHEMA
# --------------------------------------------------

class OutbreakDetectionRequest(BaseModel):
    """
    Aggregate observations for one disease in one region.

    historical_cases:
        Historical counts from comparable time periods,
        ordered from oldest to newest.

    recent_cases:
        Recent observations, ordered from oldest to
        newest. The last value represents the latest
        completed observation period.

    historical_population:
        Optional population estimates corresponding
        to historical observations.

    recent_population:
        Optional population estimates corresponding
        to recent observations.
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

    historical_cases: list[int] = Field(
        min_length=MIN_HISTORY_POINTS,
        max_length=MAX_HISTORY_POINTS,
    )

    recent_cases: list[int] = Field(
        min_length=1,
        max_length=MAX_HISTORY_POINTS,
    )

    historical_population: list[int] | None = None

    recent_population: list[int] | None = None

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
                "This field cannot be empty."
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
        "historical_cases",
        "recent_cases",
    )
    @classmethod
    def validate_case_counts(
        cls,
        values: list[int],
    ) -> list[int]:

        for value in values:

            if (
                not isinstance(value, int)
                or isinstance(value, bool)
            ):
                raise ValueError(
                    "Case counts must be integers."
                )

            if value < 0 or value > 1_000_000_000:
                raise ValueError(
                    "Case count is outside the permitted range."
                )

        return values

    @field_validator(
        "historical_population",
        "recent_population",
    )
    @classmethod
    def validate_population(
        cls,
        values: list[int] | None,
    ) -> list[int] | None:

        if values is None:
            return None

        for value in values:

            if (
                not isinstance(value, int)
                or isinstance(value, bool)
            ):
                raise ValueError(
                    "Population values must be integers."
                )

            if value <= 0 or value > 2_000_000_000:
                raise ValueError(
                    "Population must be a positive, "
                    "valid integer."
                )

        return values

    @model_validator(mode="after")
    def validate_population_lengths(self):

        if (
            self.historical_population is not None
            and len(self.historical_population)
            != len(self.historical_cases)
        ):
            raise ValueError(
                "Historical population and case arrays "
                "must have the same length."
            )

        if (
            self.recent_population is not None
            and len(self.recent_population)
            != len(self.recent_cases)
        ):
            raise ValueError(
                "Recent population and case arrays "
                "must have the same length."
            )

        return self


# --------------------------------------------------
# OUTPUT SCHEMA
# --------------------------------------------------

class OutbreakDetectionResult(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
    )

    disease: str

    region_id: str

    region_name: str

    observation_date: date

    historical_average: float

    recent_average: float

    latest_cases: int

    increase_percentage: float | None

    latest_to_baseline_ratio: float | None

    sustained_increase: bool

    potential_outbreak: bool

    severity: str

    signal_reasons: list[str]

    recommendation: str

    requires_public_health_review: bool = True

    confirmed_outbreak: bool = False


# --------------------------------------------------
# DETECTOR
# --------------------------------------------------

class OutbreakDetector:
    """
    Rule-based screening for unusual disease-report
    increases within a geographical region.

    The detector examines:
    1. Recent average versus historical average.
    2. Latest observation versus historical baseline.
    3. Whether increases persist over recent periods.
    4. Whether the report count meets a minimum threshold.

    This implementation does not replace validated
    disease-specific surveillance methods.
    """

    def __init__(
        self,
        min_cases: int = DEFAULT_MIN_CASES,
        spike_ratio: float = DEFAULT_SPIKE_RATIO,
        min_increase_percent: float = (
            DEFAULT_MIN_INCREASE_PERCENT
        ),
        sustained_periods: int = (
            DEFAULT_SUSTAINED_PERIODS
        ),
    ) -> None:

        if (
            not isinstance(min_cases, int)
            or isinstance(min_cases, bool)
            or min_cases < 1
        ):
            raise ValueError(
                "min_cases must be a positive integer."
            )

        if (
            not math.isfinite(spike_ratio)
            or spike_ratio <= 1
        ):
            raise ValueError(
                "spike_ratio must be greater than 1."
            )

        if (
            not math.isfinite(min_increase_percent)
            or min_increase_percent <= 0
        ):
            raise ValueError(
                "min_increase_percent must be positive."
            )

        if (
            not isinstance(sustained_periods, int)
            or isinstance(sustained_periods, bool)
            or sustained_periods < 1
        ):
            raise ValueError(
                "sustained_periods must be positive."
            )

        self.min_cases = min_cases
        self.spike_ratio = spike_ratio

        self.min_increase_percent = (
            min_increase_percent
        )

        self.sustained_periods = sustained_periods

    # --------------------------------------------------
    # POPULATION-ADJUSTED RATE
    # --------------------------------------------------

    @staticmethod
    def _rate(
        cases: int,
        population: int,
    ) -> float:

        if population <= 0:
            raise ValueError(
                "Population must be positive."
            )

        return (
            cases / population
        ) * 100_000

    # --------------------------------------------------
    # PREPARE OBSERVATIONS
    # --------------------------------------------------

    def _prepare_rates(
        self,
        cases: list[int],
        populations: list[int] | None,
        fallback_population: int | None,
    ) -> list[float]:

        if populations is not None:

            return [
                self._rate(count, population)
                for count, population in zip(
                    cases,
                    populations,
                )
            ]

        if fallback_population is not None:

            return [
                self._rate(
                    count,
                    fallback_population,
                )
                for count in cases
            ]

        # If population information is unavailable,
        # use counts rather than pretending they are
        # population-adjusted rates.
        return [float(count) for count in cases]

    # --------------------------------------------------
    # DETECT AN OUTBREAK SIGNAL
    # --------------------------------------------------

    def detect(
        self,
        data: OutbreakDetectionRequest,
    ) -> OutbreakDetectionResult:

        historical_values = self._prepare_rates(
            cases=data.historical_cases,
            populations=data.historical_population,
            fallback_population=(
                data.recent_population[-1]
                if (
                    data.historical_population is None
                    and data.recent_population is not None
                )
                else None
            ),
        )

        recent_values = self._prepare_rates(
            cases=data.recent_cases,
            populations=data.recent_population,
            fallback_population=(
                data.recent_population[-1]
                if data.recent_population is not None
                else (
                    data.historical_population[-1]
                    if data.historical_population is not None
                    else None
                )
            ),
        )

        historical_average = mean(
            historical_values
        )

        recent_average = mean(
            recent_values
        )

        latest_cases = data.recent_cases[-1]

        # Determine the latest observation's value
        # on the same scale as the historical baseline.
        latest_value = recent_values[-1]

        signal_reasons: list[str] = []

        # --------------------------------------------------
        # BASELINE COMPARISON
        # --------------------------------------------------

        if historical_average > 0:

            latest_ratio = (
                latest_value / historical_average
            )

            increase_percentage = (
                (
                    recent_average
                    - historical_average
                )
                / historical_average
            ) * 100

        elif recent_average == 0:

            latest_ratio = 1.0
            increase_percentage = 0.0

        else:

            # A zero baseline makes the ratio undefined.
            latest_ratio = None
            increase_percentage = None

            signal_reasons.append(
                "Historical observations contain no "
                "reported cases, while recent observations "
                "contain one or more reports."
            )

        # --------------------------------------------------
        # SUSTAINED INCREASE
        # --------------------------------------------------

        recent_window = recent_values[
            -self.sustained_periods:
        ]

        sustained_increase = (
            len(recent_window) >= self.sustained_periods
            and historical_average > 0
            and all(
                value > historical_average
                for value in recent_window
            )
        )

        if sustained_increase:

            signal_reasons.append(
                "Recent reporting levels remained above "
                "the historical average across the "
                "configured number of observations."
            )

        # --------------------------------------------------
        # SPIKE DETECTION
        # --------------------------------------------------

        spike_detected = (
            latest_ratio is not None
            and latest_ratio >= self.spike_ratio
        )

        if spike_detected:

            signal_reasons.append(
                "The latest reporting rate exceeded "
                "the configured historical-baseline ratio."
            )

        # --------------------------------------------------
        # INCREASE DETECTION
        # --------------------------------------------------

        increase_detected = (
            increase_percentage is not None
            and increase_percentage
            >= self.min_increase_percent
        )

        if increase_detected:

            signal_reasons.append(
                "The recent average exceeded the configured "
                "percentage-increase threshold."
            )

        # --------------------------------------------------
        # POTENTIAL OUTBREAK CLASSIFICATION
        # --------------------------------------------------

        sufficient_reports = (
            latest_cases >= self.min_cases
        )

        potential_outbreak = (
            sufficient_reports
            and (
                spike_detected
                or increase_detected
                or sustained_increase
                or (
                    historical_average == 0
                    and recent_average > 0
                )
            )
        )

        # --------------------------------------------------
        # SEVERITY
        # --------------------------------------------------

        if not sufficient_reports:

            severity = "insufficient_data"

            recommendation = (
                "Continue monitoring. The latest count "
                "is below the configured minimum for "
                "automated outbreak screening. This does "
                "not establish that the region is safe."
            )

        elif potential_outbreak:

            if (
                latest_ratio is not None
                and latest_ratio >= 3.0
            ):

                severity = "high"

            elif (
                latest_ratio is not None
                and latest_ratio >= self.spike_ratio
            ):

                severity = "elevated"

            elif sustained_increase:

                severity = "elevated"

            else:

                severity = "watch"

            recommendation = (
                "Refer this signal to an authorized "
                "public-health professional. Verify case "
                "definitions, reporting completeness, "
                "laboratory evidence, and local trends "
                "before declaring an outbreak."
            )

        else:

            severity = "normal"

            recommendation = (
                "No configured outbreak signal was "
                "detected. Continue routine surveillance "
                "and monitor data quality."
            )

        logger.info(
            "Outbreak screening completed: "
            "region_id=%s disease=%s severity=%s",
            data.region_id,
            data.disease,
            severity,
        )

        return OutbreakDetectionResult(
            disease=data.disease,
            region_id=data.region_id,
            region_name=data.region_name,
            observation_date=data.observation_date,
            historical_average=round(
                historical_average,
                4,
            ),
            recent_average=round(
                recent_average,
                4,
            ),
            latest_cases=latest_cases,
            increase_percentage=(
                round(increase_percentage, 2)
                if increase_percentage is not None
                else None
            ),
            latest_to_baseline_ratio=(
                round(latest_ratio, 3)
                if latest_ratio is not None
                else None
            ),
            sustained_increase=sustained_increase,
            potential_outbreak=potential_outbreak,
            severity=severity,
            signal_reasons=signal_reasons,
            recommendation=recommendation,
            requires_public_health_review=True,
            confirmed_outbreak=False,
        )

    # --------------------------------------------------
    # PROCESS MULTIPLE REGIONS
    # --------------------------------------------------

    def detect_batch(
        self,
        observations: Sequence[
            OutbreakDetectionRequest
        ],
    ) -> list[OutbreakDetectionResult]:

        if len(observations) > MAX_BATCH_SIZE:
            raise ValueError(
                "Batch exceeds the maximum permitted size."
            )

        seen: set[tuple[str, str, date]] = set()

        results = []

        for observation in observations:

            key = (
                observation.region_id,
                observation.disease.casefold(),
                observation.observation_date,
            )

            if key in seen:
                raise ValueError(
                    "Duplicate region/disease/date "
                    "observation detected."
                )

            seen.add(key)

            results.append(
                self.detect(observation)
            )

        severity_order = {
            "high": 0,
            "elevated": 1,
            "watch": 2,
            "normal": 3,
            "insufficient_data": 4,
        }

        results.sort(
            key=lambda result: (
                severity_order[result.severity],
                -(
                    result.increase_percentage
                    if result.increase_percentage is not None
                    else -1
                ),
            )
        )

        return results


# --------------------------------------------------
# SHARED DETECTOR INSTANCE
# --------------------------------------------------

outbreak_detector = OutbreakDetector()


# --------------------------------------------------
# PUBLIC HELPER FUNCTIONS
# --------------------------------------------------

def detect_outbreak(
    data: OutbreakDetectionRequest,
) -> OutbreakDetectionResult:

    return outbreak_detector.detect(data)


def detect_outbreaks(
    observations: Sequence[
        OutbreakDetectionRequest
    ],
) -> list[OutbreakDetectionResult]:

    return outbreak_detector.detect_batch(
        observations
    )