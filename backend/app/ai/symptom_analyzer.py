from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

logger = logging.getLogger(__name__)


# ============================================================
# CONSTANTS
# ============================================================

MAX_SYMPTOMS = 30
MAX_SYMPTOM_LENGTH = 80
MAX_AGE = 120

# These are preliminary screening indicators, not diagnoses.
# A clinician should review and validate the rules before use.

SYMPTOM_GROUPS: dict[str, set[str]] = {
    "fever": {
        "fever",
        "high fever",
        "mild fever",
        "temperature",
        "chills",
    },
    "respiratory": {
        "cough",
        "dry cough",
        "sore throat",
        "runny nose",
        "nasal congestion",
        "shortness of breath",
        "difficulty breathing",
    },
    "gastrointestinal": {
        "nausea",
        "vomiting",
        "diarrhea",
        "loose stools",
        "abdominal pain",
        "stomach pain",
    },
    "neurological": {
        "headache",
        "dizziness",
        "confusion",
        "seizures",
        "fainting",
    },
    "pain": {
        "body ache",
        "muscle pain",
        "joint pain",
        "chest pain",
    },
    "skin": {
        "skin rash",
        "rash",
        "itching",
        "unusual bruising",
        "bleeding",
    },
    "general": {
        "fatigue",
        "weakness",
        "loss of appetite",
        "dehydration",
    },
}


# These symptoms may require urgent medical assessment.
# This list is intentionally conservative and should be reviewed
# by qualified clinicians before any real-world deployment.

URGENT_SYMPTOMS = {
    "difficulty breathing",
    "shortness of breath",
    "chest pain",
    "confusion",
    "seizures",
    "fainting",
    "unusual bruising",
    "bleeding",
}

EMERGENCY_SYMPTOMS = {
    "severe difficulty breathing",
    "severe chest pain",
    "unconsciousness",
    "blue lips",
    "severe confusion",
}


# ============================================================
# INPUT SCHEMA
# ============================================================

class SymptomAnalysisRequest(BaseModel):
    """Validated input for preliminary symptom analysis."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    symptoms: list[str] = Field(
        ...,
        min_length=1,
        max_length=MAX_SYMPTOMS,
        description="Symptoms reported by the user.",
    )

    age: int | None = Field(
        default=None,
        ge=0,
        le=MAX_AGE,
        description="Optional age in years.",
    )

    duration_days: int | None = Field(
        default=None,
        ge=0,
        le=365,
        description="Optional duration of symptoms in days.",
    )

    @field_validator("symptoms")
    @classmethod
    def validate_symptoms(cls, symptoms: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()

        for symptom in symptoms:
            if not isinstance(symptom, str):
                raise ValueError("Every symptom must be text.")

            symptom = symptom.strip().lower()

            if not symptom:
                continue

            if len(symptom) > MAX_SYMPTOM_LENGTH:
                raise ValueError(
                    f"Each symptom must be at most "
                    f"{MAX_SYMPTOM_LENGTH} characters."
                )

            # Only allow simple symptom text.
            # Reject control characters and HTML-like input.
            if re.search(r"[\x00-\x1f\x7f<>]", symptom):
                raise ValueError("A symptom contains invalid characters.")

            if not re.fullmatch(r"[a-z][a-z '\-]*", symptom):
                raise ValueError(
                    "Symptoms must contain ordinary English letters, "
                    "spaces, apostrophes, or hyphens."
                )

            if symptom not in seen:
                cleaned.append(symptom)
                seen.add(symptom)

        if not cleaned:
            raise ValueError("Provide at least one valid symptom.")

        return cleaned


# ============================================================
# OUTPUT SCHEMA
# ============================================================

class SymptomAnalysisResponse(BaseModel):
    """Result of preliminary symptom screening."""

    model_config = ConfigDict(extra="forbid")

    symptom_count: int

    matched_symptoms: list[str]

    symptom_groups: list[str]

    possible_patterns: list[str]

    urgency: Literal[
        "routine",
        "medical_review",
        "urgent",
        "emergency",
    ]

    guidance: list[str]

    duration_note: str | None = None

    requires_clinician_review: bool = True

    is_medical_diagnosis: bool = False


# ============================================================
# SYMPTOM ANALYZER
# ============================================================

class SymptomAnalyzer:
    """
    Lightweight rule-based symptom screening.

    This module identifies symptom groups and preliminary patterns.
    It does not diagnose diseases or calculate disease probabilities.
    """

    def __init__(self) -> None:
        # Build an index once for efficient symptom lookup.
        self._symptom_to_group: dict[str, str] = {}

        for group_name, symptoms in SYMPTOM_GROUPS.items():
            for symptom in symptoms:
                self._symptom_to_group[symptom] = group_name

    @staticmethod
    def _normalize(symptom: str) -> str:
        return " ".join(symptom.strip().lower().split())

    def analyze(
        self,
        request: SymptomAnalysisRequest,
    ) -> SymptomAnalysisResponse:
        """Analyze reported symptoms and return screening guidance."""

        symptoms = {
            self._normalize(symptom)
            for symptom in request.symptoms
        }

        matched_symptoms = sorted(
            symptom
            for symptom in symptoms
            if symptom in self._symptom_to_group
        )

        groups = sorted({
            self._symptom_to_group[symptom]
            for symptom in matched_symptoms
        })

        possible_patterns = self._identify_patterns(
            symptoms=symptoms,
            groups=set(groups),
        )

        urgency = self._assess_urgency(symptoms)

        guidance = self._build_guidance(
            urgency=urgency,
            groups=set(groups),
        )

        duration_note = self._duration_note(request.duration_days)

        return SymptomAnalysisResponse(
            symptom_count=len(symptoms),
            matched_symptoms=matched_symptoms,
            symptom_groups=groups,
            possible_patterns=possible_patterns,
            urgency=urgency,
            guidance=guidance,
            duration_note=duration_note,
            requires_clinician_review=True,
            is_medical_diagnosis=False,
        )

    @staticmethod
    def _identify_patterns(
        symptoms: set[str],
        groups: set[str],
    ) -> list[str]:
        """Identify broad symptom patterns without diagnosing illness."""

        patterns: list[str] = []

        if "fever" in groups and "respiratory" in groups:
            patterns.append(
                "Fever with respiratory symptoms"
            )

        if "fever" in groups and "gastrointestinal" in groups:
            patterns.append(
                "Fever with gastrointestinal symptoms"
            )

        if "fever" in groups and "pain" in groups:
            patterns.append(
                "Fever with body or joint pain"
            )

        if "fever" in groups and "skin" in groups:
            patterns.append(
                "Fever with skin symptoms"
            )

        if "respiratory" in groups:
            patterns.append(
                "Respiratory symptom pattern"
            )

        if "gastrointestinal" in groups:
            patterns.append(
                "Gastrointestinal symptom pattern"
            )

        if not patterns:
            patterns.append(
                "General symptom pattern requiring context"
            )

        return patterns

    @staticmethod
    def _assess_urgency(
        symptoms: set[str],
    ) -> Literal[
        "routine",
        "medical_review",
        "urgent",
        "emergency",
    ]:
        """Assign a preliminary urgency category."""

        if symptoms & EMERGENCY_SYMPTOMS:
            return "emergency"

        if symptoms & URGENT_SYMPTOMS:
            return "urgent"

        if "fever" in symptoms or "high fever" in symptoms:
            return "medical_review"

        return "routine"

    @staticmethod
    def _build_guidance(
        urgency: str,
        groups: set[str],
    ) -> list[str]:
        """Return general guidance based on urgency."""

        guidance: list[str] = []

        if urgency == "emergency":
            guidance.append(
                "Seek emergency medical care immediately."
            )
            guidance.append(
                "Do not delay care while using this application."
            )

        elif urgency == "urgent":
            guidance.append(
                "Obtain urgent medical assessment."
            )
            guidance.append(
                "If symptoms are severe or worsening, seek emergency care."
            )

        elif urgency == "medical_review":
            guidance.append(
                "Consider prompt assessment by a qualified healthcare professional."
            )
            guidance.append(
                "Monitor symptoms and seek care sooner if they worsen."
            )

        else:
            guidance.append(
                "Monitor symptoms and seek medical advice if they persist or worsen."
            )

        if "gastrointestinal" in groups:
            guidance.append(
                "If vomiting or diarrhea occurs, watch for signs of dehydration."
            )

        if "respiratory" in groups:
            guidance.append(
                "Seek urgent care if breathing becomes difficult."
            )

        guidance.append(
            "This screening result does not establish a medical diagnosis."
        )

        return guidance

    @staticmethod
    def _duration_note(
        duration_days: int | None,
    ) -> str | None:
        if duration_days is None:
            return None

        if duration_days == 0:
            return "The reported symptoms started today."

        if duration_days <= 3:
            return "The reported symptoms have lasted up to three days."

        if duration_days <= 7:
            return (
                "The reported symptoms have lasted several days; "
                "consider medical advice if they are not improving."
            )

        return (
            "Symptoms have persisted for more than seven days; "
            "consider assessment by a qualified healthcare professional."
        )


# ============================================================
# REUSABLE INSTANCE AND PUBLIC FUNCTION
# ============================================================

symptom_analyzer = SymptomAnalyzer()


def analyze_symptoms(
    request: SymptomAnalysisRequest,
) -> SymptomAnalysisResponse:
    """Public helper for use by FastAPI routes or other services."""

    return symptom_analyzer.analyze(request)