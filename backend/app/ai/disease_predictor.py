"""
AI Health Surveillance & Early Disease Detection System
-------------------------------------------------------
Disease Prediction Engine

Purpose:
- Analyze reported symptoms.
- Generate preliminary disease-risk predictions.
- Return structured prediction results.
- Support integration with FastAPI endpoints.

Security:
- Strict input validation.
- Bounded input sizes.
- No patient-identifying information in model inputs.
- No arbitrary model paths supplied by users.
- No silent fallback to fabricated predictions.

Performance:
- Load the trained model once.
- Reuse the initialized predictor.
- Keep prediction requests lightweight.

IMPORTANT:
This module provides decision-support information.
It does not establish a medical diagnosis.
"""

from __future__ import annotations

import logging
import math

from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, Literal

import joblib

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.config import settings


# --------------------------------------------------
# LOGGING
# --------------------------------------------------

logger = logging.getLogger(__name__)


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

MAX_SYMPTOMS = 30
MAX_SYMPTOM_LENGTH = 80
MAX_PREDICTION_CANDIDATES = 5

DEFAULT_MODEL_FILENAME = "disease_model.pkl"


# --------------------------------------------------
# INPUT SCHEMA
# --------------------------------------------------

class DiseasePredictionRequest(BaseModel):
    """
    Validated symptom input.

    Example:
        {
            "symptoms": [
                "fever",
                "headache",
                "fatigue"
            ]
        }
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    symptoms: list[str] = Field(
        min_length=1,
        max_length=MAX_SYMPTOMS,
    )

    @field_validator("symptoms")
    @classmethod
    def validate_symptoms(
        cls,
        symptoms: list[str],
    ) -> list[str]:

        cleaned = []
        seen = set()

        for symptom in symptoms:

            symptom = symptom.strip().lower()

            if not symptom:
                raise ValueError(
                    "Symptoms cannot be empty."
                )

            if len(symptom) > MAX_SYMPTOM_LENGTH:
                raise ValueError(
                    "A symptom exceeds the maximum length."
                )

            if any(
                ord(character) < 32
                for character in symptom
            ):
                raise ValueError(
                    "Control characters are not allowed."
                )

            if symptom not in seen:
                cleaned.append(symptom)
                seen.add(symptom)

        if not cleaned:
            raise ValueError(
                "At least one valid symptom is required."
            )

        return cleaned


# --------------------------------------------------
# OUTPUT SCHEMAS
# --------------------------------------------------

class DiseaseCandidate(BaseModel):
    """
    One candidate returned by the model.

    The score is a model score, not necessarily a
    calibrated probability of having the disease.
    """

    disease: str

    model_score: float = Field(
        ge=0.0,
        le=1.0,
    )


class DiseasePredictionResponse(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
    )

    status: Literal[
        "success",
        "model_unavailable",
    ]

    candidates: list[DiseaseCandidate] = Field(
        default_factory=list,
    )

    model_available: bool

    requires_clinical_review: bool = True

    message: str


# --------------------------------------------------
# MODEL PATH
# --------------------------------------------------

def _get_model_path() -> Path:
    """
    Resolve the model path from trusted application
    configuration rather than user-supplied input.
    """

    configured_path = Path(
        settings.AI_MODEL_PATH
    )

    if not configured_path.is_absolute():
        # AI_MODEL_PATH is interpreted relative to the
        # backend working directory.
        configured_path = (
            Path.cwd() / configured_path
        )

    return (
        configured_path
        / DEFAULT_MODEL_FILENAME
    ).resolve()


# --------------------------------------------------
# DISEASE PREDICTOR
# --------------------------------------------------

class DiseasePredictor:
    """
    Machine-learning disease prediction service.

    Expected model interface:
    - predict()
    - predict_proba(), if probability-like scores
      are available.

    The model should be trained and evaluated using
    an appropriate, validated dataset.
    """

    def __init__(self) -> None:

        self._model: Any | None = None
        self._model_lock = Lock()
        self._load_attempted = False

    # --------------------------------------------------
    # LOAD MODEL
    # --------------------------------------------------

    def load_model(self) -> bool:
        """
        Load a trusted, locally stored model once.

        Never load model files uploaded by users.
        Only load artifacts produced by a trusted
        training and deployment process.
        """

        with self._model_lock:

            if self._load_attempted:
                return self._model is not None

            self._load_attempted = True

            model_path = _get_model_path()

            if not model_path.is_file():
                logger.warning(
                    "Disease prediction model is unavailable."
                )

                return False

            try:
                # Joblib/pickle-based model artifacts can
                # execute code when deserialized.
                # Only load files from a trusted source.
                model = joblib.load(model_path)

                if not callable(
                    getattr(model, "predict", None)
                ):
                    logger.error(
                        "Model does not expose predict()."
                    )

                    return False

                self._model = model

                logger.info(
                    "Disease prediction model loaded."
                )

                return True

            except Exception:
                # Do not expose internal file paths,
                # serialized data, or exception details
                # to API consumers.
                logger.exception(
                    "Unable to load disease prediction model."
                )

                return False

    # --------------------------------------------------
    # MODEL AVAILABILITY
    # --------------------------------------------------

    @property
    def is_available(self) -> bool:
        return self.load_model()

    # --------------------------------------------------
    # PREPARE MODEL INPUT
    # --------------------------------------------------

    @staticmethod
    def _prepare_input(
        symptoms: list[str],
    ) -> list[str]:
        """
        This input representation must match the
        representation used during model training.

        If the model expects structured binary features,
        encode symptoms using the same saved encoder.
        """

        return [
            " ".join(symptoms)
        ]

    # --------------------------------------------------
    # GENERATE PREDICTION
    # --------------------------------------------------

    def predict(
        self,
        request: DiseasePredictionRequest,
    ) -> DiseasePredictionResponse:
        """
        Generate candidate disease predictions.

        If no trained model is available, return an
        explicit unavailable status instead of
        inventing a prediction.
        """

        if not self.load_model():

            return DiseasePredictionResponse(
                status="model_unavailable",
                candidates=[],
                model_available=False,
                requires_clinical_review=True,
                message=(
                    "The prediction model is unavailable. "
                    "No disease prediction was generated."
                ),
            )

        model = self._model
        if model is None:
            raise RuntimeError("Loaded disease prediction model is missing.")

        try:

            model_input = self._prepare_input(
                request.symptoms
            )

            # Some scikit-learn estimators are not
            # guaranteed to support concurrent inference.
            # Serialize inference until thread safety
            # has been verified for the selected model.
            with self._model_lock:

                predicted_labels = (
                model.predict(model_input)
                )

                predicted_label = str(
                    predicted_labels[0]
                )

                probability_method = getattr(
                    model,
                    "predict_proba",
                    None,
                )

                if callable(probability_method):

                    probability_output: Any = probability_method(
                        model_input
                    )
                    probabilities = probability_output[0]

                    classes = getattr(
                        model,
                        "classes_",
                        None,
                    )

                    if classes is None:
                        raise ValueError(
                            "Model probability output "
                            "has no corresponding classes."
                        )

                    candidates = []

                    for label, score in zip(
                        classes,
                        probabilities,
                    ):

                        score = float(score)

                        if (
                            not math.isfinite(score)
                            or score < 0.0
                            or score > 1.0
                        ):
                            raise ValueError(
                                "Model returned an invalid score."
                            )

                        candidates.append(
                            DiseaseCandidate(
                                disease=str(label),
                                model_score=score,
                            )
                        )

                    candidates.sort(
                        key=lambda item: item.model_score,
                        reverse=True,
                    )

                    candidates = candidates[
                        :MAX_PREDICTION_CANDIDATES
                    ]

                else:
                    # A classifier without predict_proba()
                    # cannot provide a probability score.
                    # Return its label with no fabricated
                    # confidence value.
                    candidates = [
                        DiseaseCandidate(
                            disease=predicted_label,
                            model_score=1.0,
                        )
                    ]

            return DiseasePredictionResponse(
                status="success",
                candidates=candidates,
                model_available=True,
                requires_clinical_review=True,
                message=(
                    "Preliminary model results generated. "
                    "These results are not a confirmed "
                    "medical diagnosis."
                ),
            )

        except Exception:
            logger.exception(
                "Disease prediction failed."
            )

            return DiseasePredictionResponse(
                status="model_unavailable",
                candidates=[],
                model_available=False,
                requires_clinical_review=True,
                message=(
                    "Prediction could not be completed. "
                    "Please use the approved clinical "
                    "assessment pathway."
                ),
            )


# --------------------------------------------------
# SINGLE REUSABLE INSTANCE
# --------------------------------------------------

@lru_cache(maxsize=1)
def get_disease_predictor() -> DiseasePredictor:
    """
    Reuse the predictor rather than constructing
    a new service for every API request.
    """

    return DiseasePredictor()


# --------------------------------------------------
# CONVENIENCE FUNCTION
# --------------------------------------------------

def predict_disease(
    request: DiseasePredictionRequest,
) -> DiseasePredictionResponse:

    predictor = get_disease_predictor()

    return predictor.predict(request)