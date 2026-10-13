from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.api import routes_alerts
from app.database.database import Base
from app.models.alert import Alert


class AlertRouteTests(unittest.TestCase):
    alert_id = 8

    def setUp(self) -> None:
        self.official = SimpleNamespace(id=23)
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def make_alert(self, status: str = "new") -> Alert:
        alert = Alert(
            id=self.alert_id,
            title="Dengue signal",
            description="Synthetic signal for review.",
            severity="high",
            status=status,
            disease_name="Dengue",
            region_id="IN-MH-MUM",
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(alert)
        self.db.commit()
        return alert

    def test_get_alert_returns_requested_alert(self) -> None:
        self.make_alert()

        result = routes_alerts.get_alert(
            self.alert_id,
            self.db,
        )

        self.assertEqual(result.id, self.alert_id)

    def test_get_missing_alert_returns_not_found(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            routes_alerts.get_alert(404, self.db)

        self.assertEqual(raised.exception.status_code, 404)

    def test_acknowledge_sets_status_and_authenticated_official(self) -> None:
        alert = self.make_alert()

        result = routes_alerts.acknowledge_alert(
            self.alert_id,
            self.db,
            self.official,
        )

        self.assertEqual(result.status, "acknowledged")
        self.assertEqual(alert.acknowledged_by, str(self.official.id))
        self.assertIsNotNone(alert.acknowledged_at)
        saved_alert = self.db.get(Alert, self.alert_id)
        assert saved_alert is not None
        self.assertEqual(saved_alert.status, "acknowledged")

    def test_resolved_alert_cannot_be_acknowledged(self) -> None:
        self.make_alert(status="resolved")

        with self.assertRaises(HTTPException) as raised:
            routes_alerts.acknowledge_alert(
                self.alert_id,
                self.db,
                self.official,
            )

        self.assertEqual(raised.exception.status_code, 409)

    def test_resolve_marks_alert_resolved(self) -> None:
        self.make_alert(status="acknowledged")

        result = routes_alerts.resolve_alert(
            self.alert_id,
            self.db,
            self.official,
        )

        self.assertEqual(result.status, "resolved")
        saved_alert = self.db.get(Alert, self.alert_id)
        assert saved_alert is not None
        self.assertEqual(saved_alert.status, "resolved")


if __name__ == "__main__":
    unittest.main()
