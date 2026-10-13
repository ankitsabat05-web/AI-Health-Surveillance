from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

DEFAULT_DATASET_PATH = PROJECT_ROOT / "datasets" / "health_reports.csv"
DEFAULT_MODEL_DIRECTORY = PROJECT_ROOT / "models"
DEFAULT_MODEL_PATH = DEFAULT_MODEL_DIRECTORY / "disease_detection_model.pkl"
DEFAULT_REPORT_DIRECTORY = PROJECT_ROOT / "evaluation"

TEXT_COLUMN = "text"
LABEL_COLUMN = "label"

TEST_SIZE = 0.20
RANDOM_STATE = 42

MIN_RECORDS = 20
MAX_FEATURES = 20_000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("health_ml_training")

# ============================================================
# DATASET LOADING
# ============================================================


def load_dataset(dataset_path: Path) -> pd.DataFrame:
    """Load and validate a labelled health-report dataset."""
    if not dataset_path.is_file():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    data = pd.read_csv(dataset_path)

    required_columns = {TEXT_COLUMN, LABEL_COLUMN}
    missing_columns = required_columns - set(data.columns)

    if missing_columns:
        raise ValueError(
            "Dataset is missing required columns: " f"{sorted(missing_columns)}"
        )

    data = data[[TEXT_COLUMN, LABEL_COLUMN]].copy()

    data[TEXT_COLUMN] = data[TEXT_COLUMN].astype("string").str.strip()
    data[LABEL_COLUMN] = data[LABEL_COLUMN].astype("string").str.strip()

    data[TEXT_COLUMN] = data[TEXT_COLUMN].mask(data[TEXT_COLUMN] == "", pd.NA)
    data[LABEL_COLUMN] = data[LABEL_COLUMN].mask(data[LABEL_COLUMN] == "", pd.NA)

    data = data.dropna(subset=[TEXT_COLUMN, LABEL_COLUMN])

    data = data.drop_duplicates(subset=[TEXT_COLUMN, LABEL_COLUMN]).reset_index(drop=True)

    if len(data) < MIN_RECORDS:
        raise ValueError(
            f"At least {MIN_RECORDS} labelled records are required for this training "
            "configuration. More data is normally needed for meaningful evaluation."
        )

    class_counts = data[LABEL_COLUMN].value_counts()

    if len(class_counts) < 2:
        raise ValueError("At least two distinct label categories are required.")

    if class_counts.min() < 2:
        raise ValueError(
            "Every category needs at least two examples for a stratified train/test split."
        )

    logger.info("Loaded %s valid records.", len(data))
    logger.info("Detected %s distinct categories.", len(class_counts))

    for label, count in class_counts.items():
        logger.info("Category '%s': %s records", label, count)

    return data


# ============================================================
# TRAINING AND TEST SPLIT
# ============================================================


def split_dataset(
    data: pd.DataFrame,
    test_size: float = TEST_SIZE,
    random_state: int = RANDOM_STATE,
):
    """Split the labelled dataset into training and testing sets."""
    if not 0.0 < test_size < 1.0:
        raise ValueError("test_size must be between 0 and 1.")

    class_counts = data[LABEL_COLUMN].value_counts()

    if class_counts.min() < 2:
        raise ValueError("Each class must contain at least two examples.")

    train_text, test_text, train_labels, test_labels = train_test_split(
        data[TEXT_COLUMN],
        data[LABEL_COLUMN],
        test_size=test_size,
        random_state=random_state,
        stratify=data[LABEL_COLUMN],
    )

    return train_text, test_text, train_labels, test_labels


# ============================================================
# MODEL PIPELINE
# ============================================================


def build_model() -> Pipeline:
    """Build a text-classification pipeline."""
    return Pipeline(
        steps=[
            (
                "tfidf",
                TfidfVectorizer(
                    lowercase=True,
                    strip_accents="unicode",
                    ngram_range=(1, 2),
                    max_features=MAX_FEATURES,
                    sublinear_tf=True,
                    dtype="float32",
                ),
            ),
            (
                "classifier",
                LogisticRegression(
                    max_iter=1000,
                    class_weight="balanced",
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )


# ============================================================
# MODEL TRAINING
# ============================================================


def train_model(
    train_text: pd.Series,
    train_labels: pd.Series,
) -> Pipeline:
    """Fit the model pipeline using training records only."""
    model = build_model()

    logger.info("Starting model training.")
    model.fit(train_text, train_labels)
    logger.info("Model training completed.")

    return model


# ============================================================
# MODEL EVALUATION
# ============================================================


def evaluate_model(
    model: Pipeline,
    test_text: pd.Series,
    test_labels: pd.Series,
) -> dict[str, Any]:
    """Evaluate on the held-out test partition."""
    predictions = model.predict(test_text)

    report = classification_report(
        test_labels,
        predictions,
        output_dict=True,
        zero_division=0,
    )

    metrics: dict[str, Any] = {
        "test_samples": int(len(test_labels)),
        "accuracy": float(accuracy_score(test_labels, predictions)),
        "macro_f1": float(f1_score(test_labels, predictions, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(test_labels, predictions, average="weighted", zero_division=0)),
        "classification_report": report,
    }

    logger.info("Held-out accuracy: %.4f", metrics["accuracy"])
    logger.info("Held-out macro F1: %.4f", metrics["macro_f1"])

    return metrics


# ============================================================
# MODEL SAVING
# ============================================================


def save_model(
    model: Pipeline,
    model_path: Path = DEFAULT_MODEL_PATH,
) -> Path:
    """Save the complete pipeline."""
    model_path.parent.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, model_path, compress=3)

    logger.info("Model saved to %s", model_path)
    return model_path


# ============================================================
# METADATA SAVING
# ============================================================


def save_training_metadata(
    model: Pipeline,
    metrics: dict[str, Any],
    dataset_path: Path,
    metadata_path: Path,
    random_state: int,
    test_size: float,
) -> Path:
    """Save non-sensitive training metadata and evaluation metrics."""
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    classifier = model.named_steps["classifier"]
    vectorizer = model.named_steps["tfidf"]

    metadata = {
        "model_name": "health_report_text_classifier",
        "model_version": "1.0.0",
        "algorithm": "TF-IDF + Logistic Regression",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_filename": dataset_path.name,
        "training_configuration": {
            "random_state": random_state,
            "test_size": test_size,
            "max_features": MAX_FEATURES,
            "class_weight": "balanced",
        },
        "model_classes": [str(label) for label in classifier.classes_],
        "vocabulary_size": len(vectorizer.vocabulary_),
        "metrics": metrics,
    }

    with metadata_path.open("w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=2, allow_nan=False)

    logger.info("Training metadata saved to %s", metadata_path)
    return metadata_path


# ============================================================
# MAIN TRAINING WORKFLOW
# ============================================================


def run_training(
    dataset_path: Path = DEFAULT_DATASET_PATH,
    model_path: Path = DEFAULT_MODEL_PATH,
    test_size: float = TEST_SIZE,
    random_state: int = RANDOM_STATE,
) -> dict[str, Any]:
    """Execute the complete training workflow."""
    data = load_dataset(dataset_path)

    train_text, test_text, train_labels, test_labels = split_dataset(
        data,
        test_size=test_size,
        random_state=random_state,
    )

    model = train_model(train_text, train_labels)
    metrics = evaluate_model(model, test_text, test_labels)
    saved_model_path = save_model(model, model_path)

    metadata_path = DEFAULT_REPORT_DIRECTORY / "training_metadata.json"
    save_training_metadata(
        model=model,
        metrics=metrics,
        dataset_path=dataset_path,
        metadata_path=metadata_path,
        random_state=random_state,
        test_size=test_size,
    )

    print("\n" + "=" * 55)
    print("HEALTH SURVEILLANCE MODEL TRAINING")
    print("=" * 55)
    print(f"Training records : {len(train_text)}")
    print(f"Testing records  : {len(test_text)}")
    print(f"Model classes    : {list(model.classes_)}")
    print(f"Accuracy         : {metrics['accuracy']:.4f}")
    print(f"Macro F1         : {metrics['macro_f1']:.4f}")
    print(f"Weighted F1      : {metrics['weighted_f1']:.4f}")
    print(f"Saved model      : {saved_model_path}")
    print(f"Metadata         : {metadata_path}")
    print("=" * 55)

    return metrics


# ============================================================
# COMMAND-LINE ENTRY POINT
# ============================================================


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train a machine-learning model for health-report text classification."
    )

    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
        help="Path to the labelled CSV dataset.",
    )
    parser.add_argument(
        "--model-output",
        type=Path,
        default=DEFAULT_MODEL_PATH,
        help="Destination for the trained model.",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=TEST_SIZE,
        help="Fraction of data reserved for testing.",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=RANDOM_STATE,
        help="Random seed for reproducibility.",
    )

    args = parser.parse_args()

    try:
        run_training(
            dataset_path=args.dataset,
            model_path=args.model_output,
            test_size=args.test_size,
            random_state=args.random_state,
        )
    except (
        FileNotFoundError,
        ValueError,
        OSError,
        pd.errors.ParserError,
    ) as exc:
        logger.error("Training could not be completed: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())