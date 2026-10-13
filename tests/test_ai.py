from __future__ import annotations

import unittest
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from pydantic import ValidationError

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.ai.hotspot_detector import RegionalHealthData
from app.ai.outbreak_detector import OutbreakDetectionRequest
from app.ai.symptom_analyzer import SymptomAnalysisRequest
from app.ai.trend_forecaster import TrendForecastRequest
from app.api import routes_ai


class AIRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.official = SimpleNamespace(id=3)

    def test_symptom_analysis_returns_screening_not_diagnosis(self) -> None:
        request = SymptomAnalysisRequest(
            symptoms=["fever", "shortness of breath"],
            duration_days=2,
        )

        result = routes_ai.analyze_user_symptoms(request, self.official)

        self.assertEqual(result.urgency, "urgent")
        self.assertTrue(result.requires_clinician_review)
        self.assertFalse(result.is_medical_diagnosis)

    def test_symptom_request_rejects_html(self) -> None:
        with self.assertRaises(ValidationError):
            SymptomAnalysisRequest(symptoms=["<script>alert(1)</script>"])

    def test_trend_forecast_reports_rising_cases(self) -> None:
        request = TrendForecastRequest(
            region="Mumbai",
            disease="Dengue",
            historical_cases=[10, 20, 30],
            forecast_weeks=2,
        )

        result = routes_ai.forecast_health_trend(request, self.official)

        self.assertEqual(result.trend_direction, "rising")
        self.assertEqual(result.current_cases, 30)
        self.assertEqual(result.projected_cases, 50)

    def test_trend_request_rejects_negative_counts(self) -> None:
        with self.assertRaises(ValidationError):
            TrendForecastRequest(
                region="Mumbai",
                disease="Dengue",
                historical_cases=[10, -1],
            )

    def test_outbreak_analysis_returns_review_signal(self) -> None:
        request = OutbreakDetectionRequest(
            disease="Dengue",
            region_id="IN-MH-MUM",
            region_name="Mumbai",
            observation_date=date(2026, 10, 13),
            historical_cases=[10, 11, 12, 10, 11, 12, 10],
            recent_cases=[30, 35, 40],
        )

        result = routes_ai.analyze_outbreak_signals(request, self.official)

        self.assertTrue(result.requires_public_health_review)
        self.assertIsInstance(result.potential_outbreak, bool)

    def test_hotspot_analysis_detects_elevated_rate(self) -> None:
        request = RegionalHealthData(
            disease="Dengue",
            region_id="IN-MH-MUM",
            region_name="Mumbai",
            observation_date=date(2026, 10, 13),
            current_cases=100,
            population=100_000,
            historical_cases=[10, 10, 10, 10, 10, 10, 10],
        )

        result = routes_ai.analyze_health_hotspot(request, self.official)

        self.assertTrue(result.hotspot_detected)
        self.assertTrue(result.requires_official_review)


if __name__ == "__main__":
    unittest.main()
