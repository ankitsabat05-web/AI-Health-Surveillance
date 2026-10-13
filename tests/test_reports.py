from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
import sys

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))
from app.api import routes_reports
from app.database.database import Base
from app.models.health_report import HealthReport
from app.models.user import User


class ReportRouteTests(unittest.TestCase):
    report_id = 5

    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(
            id=12,
            full_name="Test User",
            email="test@example.com",
            hashed_password="hashed",
            role="user",
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_create_report_normalizes_and_deduplicates_symptoms(self) -> None:
        request = routes_reports.HealthReportCreate(
            disease_name=" Dengue ",
            symptoms=[" Fever ", "fever", "Headache"],
            region_id=" IN-MH-MUM ",
            description=" Symptoms began yesterday. ",
        )
        result = routes_reports.create_health_report(
            request,
            self.db,
            self.user,
        )

        self.assertEqual(result.user_id, self.user.id)
        self.assertEqual(result.disease_name, "Dengue")
        self.assertEqual(result.symptoms, ["fever", "headache"])
        self.assertEqual(result.region_id, "IN-MH-MUM")
        self.assertEqual(result.status, "submitted")
        saved_report = self.db.get(HealthReport, result.id)
        self.assertIsNotNone(saved_report)
        assert saved_report is not None
        self.assertEqual(saved_report.status, "submitted")

    def test_create_report_rejects_blank_symptoms(self) -> None:
        request = routes_reports.HealthReportCreate(
            disease_name="Dengue",
            symptoms=["   "],
            region_id="IN-MH-MUM",
        )

        with self.assertRaises(HTTPException) as raised:
            routes_reports.create_health_report(
                request,
                self.db,
                self.user,
            )

        self.assertEqual(raised.exception.status_code, 422)

    def test_report_input_rejects_extra_fields(self) -> None:
        with self.assertRaises(ValidationError):
            routes_reports.HealthReportCreate.model_validate({
                "disease_name": "Dengue",
                "symptoms": ["fever"],
                "region_id": "IN-MH-MUM",
                "user_id": 999,
            })

    def test_owner_can_read_report(self) -> None:
        self.make_report(user_id=self.user.id)
        result = routes_reports.get_health_report(
            self.report_id,
            self.db,
            self.user,
        )

        self.assertEqual(result.id, self.report_id)
        self.assertEqual(result.disease_name, "Dengue")

    def test_other_user_cannot_read_report(self) -> None:
        other_user = User(
            id=99,
            full_name="Other User",
            email="other@example.com",
            hashed_password="hashed",
            role="user",
        )
        self.db.add(other_user)
        self.db.commit()
        self.make_report(user_id=other_user.id)

        with self.assertRaises(HTTPException) as raised:
            routes_reports.get_health_report(
                self.report_id,
                self.db,
                self.user,
            )

        self.assertEqual(raised.exception.status_code, 404)

    def test_official_status_update_persists_status(self) -> None:
        self.make_report(user_id=self.user.id)
        request = routes_reports.ReportStatusUpdate(
            status=routes_reports.ReportStatus.verified
        )

        result = routes_reports.update_report_status(
            self.report_id,
            request,
            self.db,
        )

        self.assertEqual(result.status, "verified")
        saved_report = self.db.get(HealthReport, self.report_id)
        self.assertIsNotNone(saved_report)
        assert saved_report is not None
        self.assertEqual(saved_report.status, "verified")

    def make_report(self, *, user_id: int) -> HealthReport:
        report = HealthReport(
            id=self.report_id,
            user_id=user_id,
            disease_name="Dengue",
            symptoms=["fever"],
            region_id="IN-MH-MUM",
            status="submitted",
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(report)
        self.db.commit()
        return report


if __name__ == "__main__":
    unittest.main()
