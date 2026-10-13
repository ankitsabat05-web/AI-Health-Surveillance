from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "raw" / "regional_health_data.csv"
PROCESSED_PATH = ROOT / "processed" / "regional_health_data_clean.csv"


def build_records() -> list[dict[str, str | int]]:
    return [
        {
            "region_id": "IN-MH-MUM",
            "region_name": "Mumbai",
            "region_type": "district",
            "disease": "Dengue",
            "observation_date": "2026-10-13",
            "current_cases": 82,
            "population": 3350000,
            "historical_cases": "18;20;23;21;25;29;34",
            "historical_population": "3300000;3320000;3340000;3345000;3350000;3355000;3360000",
        },
        {
            "region_id": "IN-MH-PUN",
            "region_name": "Pune",
            "region_type": "district",
            "disease": "Dengue",
            "observation_date": "2026-10-13",
            "current_cases": 38,
            "population": 1800000,
            "historical_cases": "10;12;15;14;16;18;22",
            "historical_population": "1760000;1770000;1780000;1785000;1790000;1795000;1800000",
        },
        {
            "region_id": "IN-KA-BLR",
            "region_name": "Bengaluru",
            "region_type": "district",
            "disease": "Dengue",
            "observation_date": "2026-10-13",
            "current_cases": 54,
            "population": 2500000,
            "historical_cases": "12;16;18;19;17;21;28",
            "historical_population": "2460000;2470000;2480000;2485000;2490000;2495000;2500000",
        },
        {
            "region_id": "IN-DL-ND",
            "region_name": "New Delhi",
            "region_type": "district",
            "disease": "Dengue",
            "observation_date": "2026-10-13",
            "current_cases": 66,
            "population": 2200000,
            "historical_cases": "15;17;19;18;21;24;27",
            "historical_population": "2150000;2160000;2170000;2175000;2180000;2190000;2200000",
        },
        {
            "region_id": "IN-MH-MUM",
            "region_name": "Mumbai",
            "region_type": "district",
            "disease": "Malaria",
            "observation_date": "2026-10-13",
            "current_cases": 22,
            "population": 3350000,
            "historical_cases": "8;9;7;10;11;9;12",
            "historical_population": "3300000;3320000;3340000;3345000;3350000;3355000;3360000",
        },
        {
            "region_id": "IN-TN-CHN",
            "region_name": "Chennai",
            "region_type": "district",
            "disease": "Malaria",
            "observation_date": "2026-10-13",
            "current_cases": 31,
            "population": 2900000,
            "historical_cases": "9;11;10;12;13;15;16",
            "historical_population": "2860000;2875000;2880000;2885000;2890000;2895000;2900000",
        },
        {
            "region_id": "IN-UP-LKO",
            "region_name": "Lucknow",
            "region_type": "district",
            "disease": "Influenza",
            "observation_date": "2026-10-13",
            "current_cases": 45,
            "population": 1900000,
            "historical_cases": "18;16;15;20;22;19;24",
            "historical_population": "1860000;1870000;1880000;1885000;1890000;1895000;1900000",
        },
        {
            "region_id": "IN-GJ-AHM",
            "region_name": "Ahmedabad",
            "region_type": "district",
            "disease": "Influenza",
            "observation_date": "2026-10-13",
            "current_cases": 52,
            "population": 2100000,
            "historical_cases": "17;18;20;19;24;25;22",
            "historical_population": "2060000;2070000;2080000;2085000;2090000;2095000;2100000",
        },
        {
            "region_id": "IN-KL-TVM",
            "region_name": "Thiruvananthapuram",
            "region_type": "district",
            "disease": "Influenza",
            "observation_date": "2026-10-13",
            "current_cases": 29,
            "population": 1200000,
            "historical_cases": "11;10;13;12;14;15;17",
            "historical_population": "1180000;1185000;1190000;1195000;1200000;1205000;1210000",
        },
        {
            "region_id": "IN-WB-KOL",
            "region_name": "Kolkata",
            "region_type": "district",
            "disease": "Dengue",
            "observation_date": "2026-10-13",
            "current_cases": 48,
            "population": 2400000,
            "historical_cases": "12;13;15;16;17;18;20",
            "historical_population": "2360000;2370000;2380000;2385000;2390000;2395000;2400000",
        },
        {
            "region_id": "IN-TG-HYD",
            "region_name": "Hyderabad",
            "region_type": "district",
            "disease": "Chikungunya",
            "observation_date": "2026-10-13",
            "current_cases": 33,
            "population": 2000000,
            "historical_cases": "7;8;9;10;12;13;15",
            "historical_population": "1960000;1970000;1980000;1985000;1990000;1995000;2000000",
        },
        {
            "region_id": "IN-RJ-JAI",
            "region_name": "Jaipur",
            "region_type": "district",
            "disease": "Chikungunya",
            "observation_date": "2026-10-13",
            "current_cases": 27,
            "population": 1700000,
            "historical_cases": "6;7;8;9;10;11;12",
            "historical_population": "1670000;1680000;1685000;1690000;1695000;1700000;1705000",
        },
    ]


def write_dataset(path: Path, records: list[dict[str, str | int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "region_id",
        "region_name",
        "region_type",
        "disease",
        "observation_date",
        "current_cases",
        "population",
        "historical_cases",
        "historical_population",
    ]

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def main() -> None:
    records = build_records()
    write_dataset(RAW_PATH, records)
    write_dataset(PROCESSED_PATH, records)
    print(f"Wrote {len(records)} rows to {RAW_PATH}")
    print(f"Wrote {len(records)} rows to {PROCESSED_PATH}")


if __name__ == "__main__":
    main()
