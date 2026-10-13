"""
AI Health Surveillance & Early Disease Detection System
-------------------------------------------------------
Geographical Disease Hotspot Detection Engine

Purpose:
- Identify regions with elevated disease-report rates.
- Compare current reports with historical baselines.
- Adjust rates for population size.
- Generate explainable regional risk classifications.
- Supply aggregate results to government dashboards.

Security:
- Strict input validation.
- Bounded data inputs.
- No patient-identifying information.
- Duplicate-region detection.
- No arbitrary file loading.

Performance:
- Lightweight statistical calculations.
- No model training during API requests.
- Reusable detector instance.

IMPORTANT:
A statistical hotspot is a signal for investigation,
not confirmation of an outbreak or disease transmission.
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

MAX_REGIONS_PER_BATCH = 10_000
MAX_HISTORY_DAYS = 365

MIN_HISTORY_POINTS = 7
MIN_REPORTS_FOR_REVIEW = 5

RATE_SCALE = 100_000

# These are initial screening thresholds, not
# clinically or epidemiologically validated limits.
DEFAULT_ELEVATED_RATE = 10.0
DEFAULT_HIGH_RATE = 25.0
DEFAULT_CRITICAL_RATE = 50.0

DEFAULT_RATE_RATIO_THRESHOLD = 2.0


# --------------------------------------------------
# INPUT SCHEMA
# --------------------------------------------------

class RegionalHealthData(BaseModel):
    """
    Aggregate health statistics for one region.

    disease:
        Disease or syndrome being monitored.

    region_id:
        Stable administrative identifier.

    region_name:
        Display name of the geographical region.

    observation_date:
        Date represented by the current count.

    current_cases:
        Number of reported cases during the period.

    population:
        Population represented by the region.

    historical_cases:
        Historical counts for comparable periods.

    historical_population:
        Population estimates corresponding to
        historical counts, if available.
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

    current_cases: int = Field(
        ge=0,
        le=1_000_000_000,
    )

    population: int = Field(
        gt=0,
        le=2_000_000_000,
    )

    historical_cases: list[int] = Field(
        min_length=MIN_HISTORY_POINTS,
        max_length=MAX_HISTORY_DAYS,
    )

    historical_population: list[int] | None = None

    @field_validator(
        "disease",
        "region_id",
        "region_name",
    )
    @classmethod
    def validate_text_fields(
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

    @field_validator("historical_cases")
    @classmethod
    def validate_historical_cases(
        cls,
        values: list[int],
    ) -> list[int]:

        for value in values:

            if (
                not isinstance(value, int)
                or isinstance(value, bool)
            ):
                raise ValueError(
                    "Historical case counts must be integers."
                )

            if value < 0 or value > 1_000_000_000:
                raise ValueError(
                    "Historical case count is outside "
                    "the permitted range."
                )

        return values

    @field_validator("historical_population")
    @classmethod
    def validate_historical_population(
        cls,
        values: list[int] | None,
    ) -> list[int] | None:

        if values is None:
            return None

        if not (
            MIN_HISTORY_POINTS
            <= len(values)
            <= MAX_HISTORY_DAYS
        ):
            raise ValueError(
                "Historical population data must contain "
                "between 7 and 365 observations."
            )

        for value in values:

            if (
                not isinstance(value, int)
                or isinstance(value, bool)
            ):
                raise ValueError(
                    "Historical population values "
                    "must be integers."
                )

            if value <= 0 or value > 2_000_000_000:
                raise ValueError(
                    "Historical population is invalid."
                )

        return values

    @model_validator(mode="after")
    def validate_history(self):

        if (
            self.historical_population is not None
            and len(self.historical_population)
            != len(self.historical_cases)
        ):
            raise ValueError(
                "Historical case and population arrays "
                "must have equal lengths."
            )

        return self


# --------------------------------------------------
# OUTPUT SCHEMA
# --------------------------------------------------

class HotspotResult(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
    )

    disease: str

    region_id: str

    region_name: str

    observation_date: date

    current_cases: int

    population: int

    current_rate_per_100k: float

    historical_average_rate_per_100k: float

    rate_ratio: float | None

    percentage_change: float | None

    hotspot_detected: bool

    severity: Literal[
        "normal",
        "watch",
        "elevated",
        "high",
        "critical",
        "insufficient_data",
    ]

    explanation: str

    requires_official_review: bool = True


# --------------------------------------------------
# HOTSPOT DETECTOR
# --------------------------------------------------

class HotspotDetector:
    """
    Detect potentially elevated geographical disease
    reporting patterns using aggregate data.

    This initial implementation compares rates and
    historical averages. It does not perform spatial
    clustering, calculate transmission probabilities,
    or establish causation.
    """

    def __init__(
        self,
        elevated_rate: float = DEFAULT_ELEVATED_RATE,
        high_rate: float = DEFAULT_HIGH_RATE,
        critical_rate: float = DEFAULT_CRITICAL_RATE,
        rate_ratio_threshold: float = (
            DEFAULT_RATE_RATIO_THRESHOLD
        ),
        min_reports: int = MIN_REPORTS_FOR_REVIEW,
    ) -> None:

        thresholds = [
            elevated_rate,
            high_rate,
            critical_rate,
            rate_ratio_threshold,
        ]

        if not all(
            math.isfinite(value) and value > 0
            for value in thresholds
        ):
            raise ValueError(
                "All thresholds must be positive "
                "and finite."
            )

        if not (
            elevated_rate <= high_rate <= critical_rate
        ):
            raise ValueError(
                "Rate thresholds must be ordered: "
                "elevated <= high <= critical."
            )

        if (
            not isinstance(min_reports, int)
            or isinstance(min_reports, bool)
            or min_reports < 1
        ):
            raise ValueError(
                "Minimum reports must be a positive integer."
            )

        self.elevated_rate = elevated_rate
        self.high_rate = high_rate
        self.critical_rate = critical_rate

        self.rate_ratio_threshold = (
            rate_ratio_threshold
        )

        self.min_reports = min_reports

    # --------------------------------------------------
    # RATE CALCULATION
    # --------------------------------------------------

    @staticmethod
    def _rate_per_100k(
        cases: int,
        population: int,
    ) -> float:

        if population <= 0:
            raise ValueError(
                "Population must be positive."
            )

        return (
            cases / population
        ) * RATE_SCALE

    # --------------------------------------------------
    # HISTORICAL BASELINE
    # --------------------------------------------------

    def _historical_rates(
        self,
        data: RegionalHealthData,
    ) -> list[float]:

        rates = []

        if data.historical_population is not None:

            for cases, population in zip(
                data.historical_cases,
                data.historical_population,
            ):

                rates.append(
                    self._rate_per_100k(
                        cases,
                        population,
                    )
                )

        else:
            # When historical population estimates are
            # unavailable, the current population is
            # used as an approximation.
            #
            # This assumes the population did not
            # change substantially during the period.
            # Production systems should prefer historical
            # population estimates where available.

            rates = [
                self._rate_per_100k(
                    cases,
                    data.population,
                )
                for cases in data.historical_cases
            ]

        return rates

    # --------------------------------------------------
    # SEVERITY CLASSIFICATION
    # --------------------------------------------------

    def _classify_severity(
        self,
        current_rate: float,
        rate_ratio: float | None,
        current_cases: int,
    ) -> Literal[
        "normal",
        "watch",
        "elevated",
        "high",
        "critical",
        "insufficient_data",
    ]:

        if current_cases < self.min_reports:
            return "insufficient_data"

        ratio_is_high = (
            rate_ratio is not None
            and rate_ratio >= self.rate_ratio_threshold
        )

        if current_rate >= self.critical_rate:
            return "critical"

        if current_rate >= self.high_rate:
            return "high"

        if (
            current_rate >= self.elevated_rate
            or ratio_is_high
        ):
            return "elevated"

        if rate_ratio is not None and rate_ratio >= 1.5:
            return "watch"

        return "normal"

    # --------------------------------------------------
    # DETECT ONE HOTSPOT
    # --------------------------------------------------

    def detect(
        self,
        data: RegionalHealthData,
    ) -> HotspotResult:

        # Current population-adjusted reporting rate.
        current_rate = self._rate_per_100k(
            data.current_cases,
            data.population,
        )

        historical_rates = self._historical_rates(
            data
        )

        historical_average = (
            sum(historical_rates)
            / len(historical_rates)
        )

        historical_median = median(
            historical_rates
        )

        # Compare against the historical average.
        #
        # A zero baseline does not permit a finite
        # rate ratio, so report it as unavailable.

        if historical_average > 0:

            rate_ratio = (
                current_rate / historical_average
            )

            percentage_change = (
                (
                    current_rate
                    - historical_average
                )
                / historical_average
            ) * 100.0

        elif current_rate == 0:

            rate_ratio = 1.0
            percentage_change = 0.0

        else:

            rate_ratio = None
            percentage_change = None

        severity = self._classify_severity(
            current_rate=current_rate,
            rate_ratio=rate_ratio,
            current_cases=data.current_cases,
        )

        # A hotspot requires enough reports and
        # a meaningful elevation in the current rate.
        hotspot_detected = (
            data.current_cases >= self.min_reports
            and severity in {
                "elevated",
                "high",
                "critical",
            }
        )

        # --------------------------------------------------
        # EXPLANATION
        # --------------------------------------------------

        if severity == "insufficient_data":

            explanation = (
                "The report count is below the configured "
                "minimum for hotspot classification. "
                "Continue monitoring and assess reporting "
                "completeness."
            )

        elif hotspot_detected:

            if rate_ratio is None:

                baseline_message = (
                    "The historical average rate was zero, "
                    "so a finite rate ratio cannot be "
                    "calculated."
                )

            else:

                baseline_message = (
                    f"The current rate is {rate_ratio:.2f} "
                    "times the historical average."
                )

            explanation = (
                f"Potential {severity} disease-reporting "
                f"hotspot identified in {data.region_name} "
                f"for {data.disease}. "
                f"Current reports: {data.current_cases}; "
                f"population-adjusted rate: "
                f"{current_rate:.2f} per 100,000. "
                f"{baseline_message} "
                "Official review is recommended."
            )

        elif severity == "watch":

            explanation = (
                f"The reporting rate for {data.disease} "
                f"in {data.region_name} is above its "
                "historical baseline but does not meet "
                "the configured hotspot threshold."
            )

        else:

            explanation = (
                f"No hotspot was identified for "
                f"{data.disease} in {data.region_name} "
                "under the configured screening rules."
            )

        return HotspotResult(
            disease=data.disease,
            region_id=data.region_id,
            region_name=data.region_name,
            observation_date=data.observation_date,
            current_cases=data.current_cases,
            population=data.population,
            current_rate_per_100k=round(
                current_rate,
                3,
            ),
            historical_average_rate_per_100k=round(
                historical_average,
                3,
            ),
            rate_ratio=(
                round(rate_ratio, 3)
                if rate_ratio is not None
                else None
            ),
            percentage_change=(
                round(percentage_change, 2)
                if percentage_change is not None
                else None
            ),
            hotspot_detected=hotspot_detected,
            severity=severity,
            explanation=explanation,
            requires_official_review=True,
        )

    # --------------------------------------------------
    # DETECT MULTIPLE REGIONS
    # --------------------------------------------------

    def detect_batch(
        self,
        observations: Sequence[RegionalHealthData],
    ) -> list[HotspotResult]:
        """
        Analyze multiple regions.

        Duplicate region/disease/date combinations are
        rejected to avoid accidentally counting the same
        aggregate observation multiple times.
        """

        if len(observations) > MAX_REGIONS_PER_BATCH:
            raise ValueError(
                "Batch exceeds the maximum permitted size."
            )

        seen = set()
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

        # Present the highest-severity results first.
        severity_order = {
            "critical": 0,
            "high": 1,
            "elevated": 2,
            "watch": 3,
            "normal": 4,
            "insufficient_data": 5,
        }

        results.sort(
            key=lambda result: (
                severity_order[result.severity],
                -result.current_rate_per_100k,
            )
        )

        return results


# --------------------------------------------------
# REUSABLE DETECTOR INSTANCE
# --------------------------------------------------

hotspot_detector = HotspotDetector()


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def detect_hotspot(
    data: RegionalHealthData,
) -> HotspotResult:

    return hotspot_detector.detect(data)


def detect_hotspots(
    observations: Sequence[RegionalHealthData],
) -> list[HotspotResult]:

    return hotspot_detector.detect_batch(
        observations
    )