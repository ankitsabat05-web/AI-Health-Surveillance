from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

DATA_DIRECTORY = Path(__file__).resolve().parents[1]
RAW_PATH = DATA_DIRECTORY / "raw" / "health_reports.csv"
TRAINING_PATH = DATA_DIRECTORY / "processed" / "health_reports_training.csv"

REPORT_DATE = "2026-10-13"
REGIONS = ("IN-MH-MUM", "IN-MH-PUN", "IN-KA-BLR", "IN-DL-ND", "IN-TN-CHN")

# Synthetic examples for development and model-pipeline testing only.
EXAMPLES: dict[str, tuple[str, ...]] = {
    "Dengue": (
        "high fever; severe headache; pain behind the eyes; muscle pain; skin rash",
        "fever; joint pain; headache; nausea; skin rash",
        "high fever; chills; muscle pain; fatigue; pain behind the eyes",
        "fever; severe headache; body pain; skin rash; nausea",
        "headache; high fever; joint pain; fatigue; pain behind the eyes",
    ),
    "Malaria": (
        "recurrent fever; chills; sweating; headache; fatigue",
        "fever; shaking chills; muscle pain; nausea; sweating",
        "high fever; chills; headache; vomiting; fatigue",
        "fever; sweating; body pain; nausea; chills",
        "recurrent fever; headache; weakness; chills; muscle pain",
    ),
    "Influenza": (
        "fever; dry cough; sore throat; muscle pain; fatigue",
        "cough; fever; headache; chills; runny nose",
        "sore throat; dry cough; fatigue; body pain; fever",
        "fever; cough; congestion; headache; chills",
        "muscle pain; cough; sore throat; fatigue; runny nose",
    ),
    "COVID-19": (
        "fever; persistent cough; fatigue; loss of smell; shortness of breath",
        "dry cough; fever; loss of taste; headache; fatigue",
        "sore throat; cough; congestion; loss of smell; fever",
        "fever; shortness of breath; fatigue; muscle pain; dry cough",
        "headache; cough; loss of taste; sore throat; fatigue",
    ),
    "Typhoid": (
        "prolonged fever; abdominal pain; weakness; headache; diarrhea",
        "fever; nausea; abdominal discomfort; fatigue; loss of appetite",
        "prolonged fever; diarrhea; headache; weakness; nausea",
        "abdominal pain; fever; vomiting; fatigue; loss of appetite",
        "fever; weakness; constipation; headache; abdominal discomfort",
    ),
    "Chikungunya": (
        "fever; severe joint pain; muscle pain; headache; skin rash",
        "joint pain; fever; fatigue; swelling; headache",
        "high fever; joint pain; rash; muscle pain; nausea",
        "fever; swollen joints; fatigue; headache; body pain",
        "joint pain; rash; chills; muscle pain; fever",
    ),
}

RAW_FIELDS = (
    "report_id",
    "report_date",
    "region_id",
    "symptoms",
    "disease_name",
    "status",
    "data_source",
)
TRAINING_FIELDS = ("text", "label")


def build_records() -> list[dict[str, str]]:
    """Build synthetic reports without patient-identifying information."""
    records: list[dict[str, str]] = []
    counts: Counter[str] = Counter()

    for disease, symptom_sets in EXAMPLES.items():
        for symptoms in symptom_sets:
            counts[disease] += 1
            records.append(
                {
                    "report_id": f"HR-{len(records) + 1:04d}",
                    "report_date": REPORT_DATE,
                    "region_id": REGIONS[(len(records)) % len(REGIONS)],
                    "symptoms": symptoms,
                    "disease_name": disease,
                    "status": "pending",
                    "data_source": "synthetic_demo",
                }
            )

    if len(records) < 20 or len(counts) < 2 or min(counts.values()) < 2:
        raise ValueError(
            "Training data requires at least 20 records and at least two "
            "examples for every disease."
        )

    return records


def write_csv(
    path: Path,
    fieldnames: tuple[str, ...],
    records: list[dict[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def build_training_records(
    records: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Convert raw symptom reports to the text,label format used by train.py."""
    return [
        {
            "text": f"Reported symptoms: {record['symptoms'].replace('; ', ', ')}",
            "label": record["disease_name"],
        }
        for record in records
    ]


def main() -> None:
    records = build_records()
    write_csv(RAW_PATH, RAW_FIELDS, records)
    write_csv(TRAINING_PATH, TRAINING_FIELDS, build_training_records(records))
    print(f"Wrote {len(records)} synthetic reports to {RAW_PATH}")
    print(f"Wrote {len(records)} training examples to {TRAINING_PATH}")
    print("These demonstration records are not real patient data or diagnoses.")


if __name__ == "__main__":
    main()
