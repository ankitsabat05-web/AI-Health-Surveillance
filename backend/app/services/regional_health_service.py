from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from app.ai.hotspot_detector import (
    RegionalHealthData,
    detect_hotspots,
)

DEFAULT_CSV_PATH = Path(__file__).resolve().parents[3] / "data" / "raw" / "regional_health_data.csv"


def _parse_history(value: str) -> list[int]:
    if not value:
        raise ValueError("Historical values are required.")

    cleaned = [part.strip() for part in value.split(";") if part.strip()]
    if not cleaned:
        raise ValueError("Historical values are required.")

    return [int(item) for item in cleaned]


def load_regional_health_data(csv_path: Path | str = DEFAULT_CSV_PATH) -> list[RegionalHealthData]:
    """Load and validate regional disease data from the project CSV source."""
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Regional health data not found: {path}")

    records: list[RegionalHealthData] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            try:
                historical_cases = _parse_history(row["historical_cases"])
                historical_population = _parse_history(row["historical_population"])
                records.append(
                    RegionalHealthData(
                        disease=row["disease"].strip(),
                        region_id=row["region_id"].strip(),
                        region_name=row["region_name"].strip(),
                        observation_date=date.fromisoformat(
                            row["observation_date"].strip()
                        ),
                        current_cases=int(row["current_cases"]),
                        population=int(row["population"]),
                        historical_cases=historical_cases,
                        historical_population=historical_population,
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid regional health data at row {row_number}: {exc}") from exc

    return records


def get_hotspot_summary(csv_path: Path | str = DEFAULT_CSV_PATH) -> list[dict]:
    """Return hotspot analysis results derived from the dataset."""
    observations = load_regional_health_data(csv_path)
    results = detect_hotspots(observations)
    return [result.model_dump() for result in results]
