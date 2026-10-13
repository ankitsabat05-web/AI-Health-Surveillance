from __future__ import annotations

import argparse
import logging
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "disease_detection_model.pkl"
DEFAULT_CONFIDENCE_THRESHOLD = 0.80
MAX_TEXT_LENGTH = 5000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("health_ml_prediction")

# ============================================================
# INPUT SCHEMA
# ============================================================


class PredictionRequest(BaseModel):
    """Validated input for a health-report classification request."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        min_length=1,
        max_length=MAX_TEXT_LENGTH,
        description="Health-report text to classify.",
    )

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Health-report text cannot be empty.")

        if any(ord(character) < 32 and character not in "\t\n\r" for character in value):
            raise ValueError("Health-report text contains invalid characters.")

        return value


# ============================================================
# OUTPUT SCHEMA
# ============================================================


class PredictionResult(BaseModel):
    """Result of a health-report classification."""

    model_config = ConfigDict(extra="forbid")

    predicted_category: str | None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    status: str
    requires_review: bool
    model_version: str
    message: str


# ============================================================
# MODEL LOADING
# ============================================================


def _validate_model(model: Any) -> None:
    """Verify that the loaded object provides the required interface."""
    if not hasattr(model, "predict"):
        raise TypeError("The model must implement predict().")

    if not hasattr(model, "classes_"):
        raise TypeError("The model must expose classes_.")

    classes = list(model.classes_)

    if not classes:
        raise ValueError("The model has no trained classes.")

    if not all(isinstance(label, str) for label in classes):
        raise TypeError("Model classes must be strings. Check label encoding.")


@lru_cache(maxsize=2)
def _load_model_cached(model_path: str, model_version: str) -> Any:
    """Load and cache a trusted model."""
    path = Path(model_path).resolve()

    if not path.is_file():
        raise FileNotFoundError(f"Trained model file does not exist: {path}")

    model = joblib.load(path)
    _validate_model(model)

    logger.info("Prediction model loaded successfully. Version: %s", model_version)
    return model


def load_model(
    model_path: str | Path = DEFAULT_MODEL_PATH,
    model_version: str = "1.0.0",
) -> Any:
    """Load the trained model using an absolute path."""
    path = Path(model_path).resolve()
    return _load_model_cached(str(path), model_version)


# ============================================================
# PREDICTION ENGINE
# ============================================================


def predict_health_report(
    text: str,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    model_path: str | Path = DEFAULT_MODEL_PATH,
    model_version: str = "1.0.0",
) -> PredictionResult:
    """Classify a health report into a model-trained category."""
    request = PredictionRequest(text=text)

    if not 0.0 <= confidence_threshold <= 1.0:
        raise ValueError("Confidence threshold must be between 0 and 1.")

    model = load_model(model_path=model_path, model_version=model_version)

    try:
        predictions = model.predict([request.text])

        if len(predictions) != 1:
            raise ValueError("Model returned an unexpected number of predictions.")

        predicted_category = str(predictions[0])

        if predicted_category not in model.classes_:
            raise ValueError("Model returned a category outside its trained classes.")

        confidence: float | None = None

        if hasattr(model, "predict_proba"):
            probabilities = np.asarray(
                model.predict_proba([request.text]),
                dtype=float,
            )

            if (
                probabilities.ndim != 2
                or probabilities.shape != (1, len(model.classes_))
                or not np.isfinite(probabilities).all()
                or (probabilities < 0).any()
                or (probabilities > 1).any()
            ):
                raise ValueError("Model returned invalid prediction probabilities.")

            class_index = list(model.classes_).index(predicted_category)
            confidence = float(probabilities[0, class_index])

        if confidence is None:
            return PredictionResult(
                predicted_category=predicted_category,
                confidence=None,
                status="review_required",
                requires_review=True,
                model_version=model_version,
                message=(
                    "A category was predicted, but confidence scoring is unavailable. "
                    "Human review is required."
                ),
            )

        if confidence < confidence_threshold:
            return PredictionResult(
                predicted_category=None,
                confidence=confidence,
                status="uncertain",
                requires_review=True,
                model_version=model_version,
                message=(
                    "The prediction did not meet the configured confidence threshold. "
                    "Review the report manually."
                ),
            )

        return PredictionResult(
            predicted_category=predicted_category,
            confidence=confidence,
            status="predicted",
            requires_review=True,
            model_version=model_version,
            message=(
                "Preliminary classification completed. Review is required before operational use."
            ),
        )

    except (ValueError, TypeError):
        raise
    except Exception:
        logger.exception("Health-report prediction failed.")
        raise RuntimeError("Prediction could not be completed.") from None


# ============================================================
# BATCH PREDICTION
# ============================================================


def predict_health_reports(
    texts: list[str],
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    model_path: str | Path = DEFAULT_MODEL_PATH,
    model_version: str = "1.0.0",
) -> list[PredictionResult]:
    """Classify multiple health reports using one loaded model."""
    max_batch_size = 100

    if not texts:
        return []

    if len(texts) > max_batch_size:
        raise ValueError(f"Batch size cannot exceed {max_batch_size}.")

    validated_texts = [PredictionRequest(text=text).text for text in texts]

    if not 0.0 <= confidence_threshold <= 1.0:
        raise ValueError("Confidence threshold must be between 0 and 1.")

    model = load_model(model_path=model_path, model_version=model_version)

    try:
        predictions = model.predict(validated_texts)

        if len(predictions) != len(validated_texts):
            raise ValueError("Model returned an unexpected number of predictions.")

        probability_matrix: np.ndarray | None = None

        if hasattr(model, "predict_proba"):
            probability_matrix = np.asarray(
                model.predict_proba(validated_texts),
                dtype=float,
            )

            if (
                probability_matrix.ndim != 2
                or probability_matrix.shape != (len(validated_texts), len(model.classes_))
                or not np.isfinite(probability_matrix).all()
                or (probability_matrix < 0).any()
                or (probability_matrix > 1).any()
            ):
                raise ValueError("Model returned invalid prediction probabilities.")

        results: list[PredictionResult] = []

        for index, predicted in enumerate(predictions):
            category = str(predicted)

            if category not in model.classes_:
                raise ValueError("Model returned a category outside its trained classes.")

            if probability_matrix is None:
                results.append(
                    PredictionResult(
                        predicted_category=category,
                        confidence=None,
                        status="review_required",
                        requires_review=True,
                        model_version=model_version,
                        message=(
                            "Confidence scoring is unavailable. Human review is required."
                        ),
                    )
                )
                continue

            class_index = list(model.classes_).index(category)
            confidence = float(probability_matrix[index, class_index])

            if confidence < confidence_threshold:
                results.append(
                    PredictionResult(
                        predicted_category=None,
                        confidence=confidence,
                        status="uncertain",
                        requires_review=True,
                        model_version=model_version,
                        message="Low-confidence result; manual review required.",
                    )
                )
            else:
                results.append(
                    PredictionResult(
                        predicted_category=category,
                        confidence=confidence,
                        status="predicted",
                        requires_review=True,
                        model_version=model_version,
                        message="Preliminary classification completed; human review required.",
                    )
                )

        return results

    except (ValueError, TypeError):
        raise
    except Exception:
        logger.exception("Batch health-report prediction failed.")
        raise RuntimeError("Batch prediction could not be completed.") from None


# ============================================================
# COMMAND-LINE TEST
# ============================================================


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Classify a health report using a trained model."
    )

    parser.add_argument(
        "--text",
        required=True,
        help="Text to classify. Avoid real patient-identifying data.",
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_CONFIDENCE_THRESHOLD,
        help="Minimum confidence score for returning a category.",
    )

    args = parser.parse_args()

    try:
        result = predict_health_report(
            text=args.text,
            confidence_threshold=args.threshold,
        )
        print(result.model_dump_json(indent=2))
    except (ValueError, TypeError, FileNotFoundError, RuntimeError):
        print(
            "Prediction failed. Check the model, input, and configuration.",
            file=sys.stderr,
        )
        raise SystemExit(1)
