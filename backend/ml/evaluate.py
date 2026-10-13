from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split

# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

DATASET_PATH = PROJECT_ROOT / "datasets" / "health_reports.csv"
MODEL_PATH = PROJECT_ROOT / "models" / "disease_detection_model.pkl"
OUTPUT_DIRECTORY = PROJECT_ROOT / "evaluation"

TEXT_COLUMN = "text"
LABEL_COLUMN = "label"

TEST_SIZE = 0.20
RANDOM_STATE = 42

# Set this to a value between 0 and 1 to enable confidence-based
# abstention. Predictions below the threshold are marked uncertain.
# This is not a medically validated diagnostic threshold.
DEFAULT_CONFIDENCE_THRESHOLD = 0.80

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("health_ml_evaluation")

# ============================================================
# DATASET LOADING AND VALIDATION
# ============================================================


def load_dataset(dataset_path: Path) -> pd.DataFrame:
    """Load and validate the labelled evaluation dataset."""
    if not dataset_path.is_file():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    data = pd.read_csv(dataset_path)

    required_columns = {TEXT_COLUMN, LABEL_COLUMN}
    missing_columns = required_columns - set(data.columns)

    if missing_columns:
        raise ValueError(
            f"Dataset is missing required columns: {sorted(missing_columns)}"
        )

    data = data[[TEXT_COLUMN, LABEL_COLUMN]].copy()
    data[TEXT_COLUMN] = data[TEXT_COLUMN].astype("string").str.strip()
    data[LABEL_COLUMN] = data[LABEL_COLUMN].astype("string").str.strip()

    data[TEXT_COLUMN] = data[TEXT_COLUMN].mask(data[TEXT_COLUMN] == "", pd.NA)
    data[LABEL_COLUMN] = data[LABEL_COLUMN].mask(data[LABEL_COLUMN] == "", pd.NA)

    data = data.dropna(subset=[TEXT_COLUMN, LABEL_COLUMN])

    if data.empty:
        raise ValueError("The dataset contains no valid labelled records.")

    if data[LABEL_COLUMN].nunique() < 2:
        raise ValueError("Evaluation requires at least two distinct classes.")

    logger.info("Loaded %s labelled records.", len(data))
    logger.info("Number of distinct classes: %s", data[LABEL_COLUMN].nunique())

    return data


# ============================================================
# MODEL LOADING
# ============================================================


def load_model(model_path: Path) -> Any:
    """Load a previously trained scikit-learn model or pipeline."""
    if not model_path.is_file():
        raise FileNotFoundError(f"Trained model not found: {model_path}")

    model = joblib.load(model_path)

    if not hasattr(model, "predict"):
        raise TypeError("Loaded object does not provide a predict() method.")

    if not hasattr(model, "classes_"):
        raise TypeError("Model must expose classes_ to evaluate label mappings.")

    logger.info("Model loaded successfully.")
    return model


# ============================================================
# EVALUATION DATA SPLIT
# ============================================================


def split_dataset(
    data: pd.DataFrame,
    test_size: float = TEST_SIZE,
    random_state: int = RANDOM_STATE,
):
    """Create a stratified holdout split."""
    labels = data[LABEL_COLUMN]
    class_counts = labels.value_counts()

    if class_counts.min() < 2:
        raise ValueError(
            "Each class needs at least two records for a stratified "
            "train/test split. Provide more labelled examples."
        )

    features_train, features_test, labels_train, labels_test = train_test_split(
        data[TEXT_COLUMN],
        labels,
        test_size=test_size,
        random_state=random_state,
        stratify=labels,
    )

    return features_train, features_test, labels_train, labels_test


# ============================================================
# PREDICTION CONFIDENCE
# ============================================================


def get_prediction_confidence(
    model: Any,
    features: pd.Series,
) -> np.ndarray | None:
    """Return the maximum predicted class probability when supported."""
    if not hasattr(model, "predict_proba"):
        logger.warning(
            "Model does not support predict_proba(); "
            "confidence-based abstention will be unavailable."
        )
        return None

    probabilities = model.predict_proba(features)

    if (
        not isinstance(probabilities, np.ndarray)
        or probabilities.ndim != 2
        or probabilities.shape[0] != len(features)
    ):
        raise ValueError("Model returned an invalid probability array.")

    if not np.isfinite(probabilities).all():
        raise ValueError("Model returned non-finite prediction probabilities.")

    if (probabilities < 0).any() or (probabilities > 1).any():
        raise ValueError("Model returned probabilities outside the [0, 1] range.")

    return probabilities.max(axis=1)


# ============================================================
# METRICS
# ============================================================


def evaluate_predictions(
    true_labels: pd.Series,
    predicted_labels: np.ndarray,
    classes: list[str],
    confidence: np.ndarray | None = None,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> dict[str, Any]:
    """Calculate overall and per-class evaluation metrics."""
    if len(true_labels) != len(predicted_labels):
        raise ValueError("True labels and predictions have different lengths.")

    labels = np.asarray(true_labels, dtype=str)
    predictions = np.asarray(predicted_labels, dtype=str)

    all_labels = sorted(set(labels.tolist()) | set(predictions.tolist()))

    accuracy = accuracy_score(labels, predictions)

    results: dict[str, Any] = {
        "test_samples": int(len(labels)),
        "classes": classes,
        "accuracy": float(accuracy),
        "precision_macro": float(
            precision_score(
                labels,
                predictions,
                average="macro",
                zero_division=0,
            )
        ),
        "recall_macro": float(
            recall_score(
                labels,
                predictions,
                average="macro",
                zero_division=0,
            )
        ),
        "f1_macro": float(
            f1_score(
                labels,
                predictions,
                average="macro",
                zero_division=0,
            )
        ),
        "f1_weighted": float(
            f1_score(
                labels,
                predictions,
                average="weighted",
                zero_division=0,
            )
        ),
        "confusion_matrix": confusion_matrix(
            labels,
            predictions,
            labels=all_labels,
        ).tolist(),
        "confusion_matrix_labels": all_labels,
        "classification_report": classification_report(
            labels,
            predictions,
            labels=all_labels,
            output_dict=True,
            zero_division=0,
        ),
    }

    if confidence is not None:
        accepted = confidence >= confidence_threshold

        results["confidence_threshold"] = confidence_threshold
        results["accepted_predictions"] = int(accepted.sum())
        results["uncertain_predictions"] = int((~accepted).sum())
        results["coverage"] = float(accepted.mean())

        if accepted.any():
            results["accuracy_on_accepted_predictions"] = float(
                accuracy_score(
                    labels[accepted],
                    predictions[accepted],
                )
            )
        else:
            results["accuracy_on_accepted_predictions"] = None

    return results


# ============================================================
# REPORT SAVING
# ============================================================


def save_report(
    results: dict[str, Any],
    output_directory: Path = OUTPUT_DIRECTORY,
) -> Path:
    """Save evaluation metrics as a JSON report."""
    output_directory.mkdir(parents=True, exist_ok=True)

    output_path = output_directory / "evaluation_report.json"
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(results, file, indent=2, allow_nan=False)

    logger.info("Evaluation report saved to %s.", output_path)
    return output_path


# ============================================================
# MAIN EVALUATION
# ============================================================


def run_evaluation(
    dataset_path: Path = DATASET_PATH,
    model_path: Path = MODEL_PATH,
    test_size: float = TEST_SIZE,
    random_state: int = RANDOM_STATE,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> dict[str, Any]:
    """Run the full model evaluation process."""
    if not 0.0 < test_size < 1.0:
        raise ValueError("test_size must be between 0 and 1.")

    if not 0.0 <= confidence_threshold <= 1.0:
        raise ValueError("confidence_threshold must be between 0 and 1.")

    data = load_dataset(dataset_path)
    model = load_model(model_path)

    _, features_test, _, labels_test = split_dataset(
        data,
        test_size=test_size,
        random_state=random_state,
    )

    model_classes = [str(label) for label in model.classes_]
    dataset_classes = set(data[LABEL_COLUMN].astype(str).unique())

    if dataset_classes != set(model_classes):
        raise ValueError(
            "The dataset labels do not match the trained model's "
            "classes. Check label encoding and training data."
        )

    predictions = model.predict(features_test)

    if len(predictions) != len(features_test):
        raise ValueError("Model returned an unexpected number of predictions.")

    confidence = get_prediction_confidence(model, features_test)

    results = evaluate_predictions(
        true_labels=labels_test,
        predicted_labels=predictions,
        classes=model_classes,
        confidence=confidence,
        confidence_threshold=confidence_threshold,
    )

    results["model_path"] = str(model_path.name)
    results["evaluation_method"] = "stratified_holdout"
    results["random_state"] = random_state
    results["test_size"] = test_size

    report_path = save_report(results)

    print("\n" + "=" * 60)
    print("HEALTH SURVEILLANCE ML MODEL EVALUATION")
    print("=" * 60)
    print(f"Test samples : {results['test_samples']}")
    print(f"Accuracy     : {results['accuracy']:.4f}")
    print(f"Macro F1     : {results['f1_macro']:.4f}")
    print(f"Macro Recall : {results['recall_macro']:.4f}")
    print(f"Macro Precision: {results['precision_macro']:.4f}")

    if confidence is not None:
        print(f"Coverage     : {results['coverage']:.4f}")
        print("Uncertain predictions: " f"{results['uncertain_predictions']}")

    print(f"\nReport saved: {report_path}")
    print("=" * 60)

    return results


# ============================================================
# COMMAND-LINE ENTRY POINT
# ============================================================


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the health surveillance ML model."
    )

    parser.add_argument(
        "--dataset",
        type=Path,
        default=DATASET_PATH,
        help="Path to the labelled CSV dataset.",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=MODEL_PATH,
        help="Path to the trusted trained model.",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=TEST_SIZE,
        help="Fraction of records reserved for testing.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_CONFIDENCE_THRESHOLD,
        help="Optional confidence threshold for abstention.",
    )

    args = parser.parse_args()

    try:
        run_evaluation(
            dataset_path=args.dataset,
            model_path=args.model,
            test_size=args.test_size,
            confidence_threshold=args.threshold,
        )
    except (
        FileNotFoundError,
        ValueError,
        TypeError,
        OSError,
        pd.errors.ParserError,
    ) as exc:
        logger.error("Model evaluation could not be completed: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())