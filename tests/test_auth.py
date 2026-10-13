from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.api import routes_auth
from app.database.database import Base
from app.models.user import User


class AuthRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_registration_creates_normal_user_and_returns_profile(self) -> None:
        request = routes_auth.RegisterRequest(
            full_name="  Test User  ",
            email="Test.User@example.com",
            password="a-strong-test-password",
        )
        with patch.object(routes_auth.password_hash, "hash", return_value="hashed"):
            result = routes_auth.register_user(request, self.db)

        self.assertEqual(result.email, "test.user@example.com")
        self.assertEqual(result.role, "user")
        self.assertTrue(result.is_active)
        saved_user = self.db.scalar(
            select(User).where(User.email == "test.user@example.com")
        )
        self.assertIsNotNone(saved_user)
        assert saved_user is not None
        self.assertEqual(saved_user.hashed_password, "hashed")

    def test_registration_rejects_duplicate_email(self) -> None:
        request = routes_auth.RegisterRequest(
            full_name="Test User",
            email="taken@example.com",
            password="a-strong-test-password",
        )
        self.db.add(
            User(
                full_name="Existing User",
                email="taken@example.com",
                hashed_password="hashed",
            )
        )
        self.db.commit()

        with self.assertRaises(HTTPException) as raised:
            routes_auth.register_user(request, self.db)

        self.assertEqual(raised.exception.status_code, 409)

    def test_registration_rejects_short_password(self) -> None:
        with self.assertRaises(ValidationError):
            routes_auth.RegisterRequest(
                full_name="Test User",
                email="test@example.com",
                password="short",
            )

    def test_login_returns_bearer_token_for_valid_credentials(self) -> None:
        user = SimpleNamespace(
            id=7,
            hashed_password="hashed",
            is_active=True,
        )
        form = OAuth2PasswordRequestForm(
            username="USER@example.com",
            password="correct-password",
        )
        self.db.add(
            User(
                id=user.id,
                full_name="Test User",
                email="user@example.com",
                hashed_password=user.hashed_password,
                is_active=user.is_active,
            )
        )
        self.db.commit()

        with (
            patch.object(routes_auth.password_hash, "verify", return_value=True),
            patch.object(
                routes_auth,
                "create_access_token",
                return_value=("signed-token", 900),
            ),
        ):
            result = routes_auth.login_user(form, self.db)

        self.assertEqual(result.access_token, "signed-token")
        self.assertEqual(result.token_type, "bearer")
        self.assertEqual(result.expires_in, 900)

    def test_login_rejects_invalid_credentials(self) -> None:
        form = OAuth2PasswordRequestForm(
            username="missing@example.com",
            password="wrong-password",
        )
        with self.assertRaises(HTTPException) as raised:
            routes_auth.login_user(form, self.db)

        self.assertEqual(raised.exception.status_code, 401)

    def test_current_user_rejects_invalid_token(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            routes_auth.get_current_user("not-a-jwt", self.db)

        self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
