from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

DATA_DIRECTORY = Path(__file__).resolve().parents[1]
RAW_DIRECTORY = DATA_DIRECTORY / "raw"
SAMPLE_DIRECTORY = DATA_DIRECTORY / "sample"

DATASETS = {
    "health_reports.csv": (
        "report_id",
        "report_date",
        "region_id",
        "symptoms",
        "disease_name",
        "status",
        "data_source",
    ),
    "disease_symptoms.csv": (
        "record_id",
        "fever",
        "cough",
        "headache",
        "fatigue",
        "body_pain",
        "sore_throat",
        "runny_nose",
        "sneezing",
        "chills",
        "joint_pain",
        "nausea",
        "vomiting",
        "diarrhea",
        "abdominal_pain",
        "skin_rash",
        "disease_name",
        "data_source",
    ),
    "disease_outbreaks.csv": (
        "outbreak_id",
        "disease_name",
        "region_id",
        "reported_cases",
        "confirmed_cases",
        "recovered_cases",
        "deaths",
        "report_date",
        "outbreak_status",
        "severity",
        "data_source",
    ),
    "regional_health_data.csv": (
        "region_id",
        "region_name",
        "region_type",
        "disease",
        "observation_date",
        "current_cases",
        "population",
        "historical_cases",
        "historical_population",
    ),
}


def copy_dataset(filename: str, expected_headers: tuple[str, ...]) -> int:
    """Validate a raw CSV's schema and write its rows to data/sample."""
    source_path = RAW_DIRECTORY / filename
    destination_path = SAMPLE_DIRECTORY / filename

    if not source_path.is_file():
        raise FileNotFoundError(f"Required source dataset not found: {source_path}")

    source_text = source_path.read_text(encoding="utf-8-sig")
    lines = source_text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]

    reader = csv.DictReader(StringIO("\n".join(lines), newline=""))
    actual_headers = tuple(reader.fieldnames or ())
    if actual_headers != expected_headers:
        raise ValueError(
            f"Unexpected columns in {source_path}: {actual_headers!r}"
        )

    rows = list(reader)
    if not rows:
        raise ValueError(f"Source dataset contains no records: {source_path}")

    SAMPLE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    with destination_path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(
            destination,
            fieldnames=expected_headers,
            extrasaction="raise",
        )
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def main() -> None:
    for filename, expected_headers in DATASETS.items():
        row_count = copy_dataset(filename, expected_headers)
        print(f"Created {SAMPLE_DIRECTORY / filename} ({row_count} records)")

    print("Sample datasets are copied from data/raw; records may be synthetic.")


if __name__ == "__main__":
    main()
