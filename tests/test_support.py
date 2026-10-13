from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))


class FakeSession:
    """Small database-session double for route unit tests."""

    def __init__(
        self,
        *,
        scalar_results: list[Any] | None = None,
        scalar_rows: list[Any] | None = None,
        objects: dict[int, Any] | None = None,
    ) -> None:
        self.scalar_results = list(scalar_results or [])
        self.scalar_rows = list(scalar_rows or [])
        self.objects = dict(objects or {})
        self.added: list[Any] = []
        self.commits = 0
        self.rollbacks = 0

    def scalar(self, statement: Any) -> Any:
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    def scalars(self, statement: Any) -> FakeScalarResult:
        return FakeScalarResult(self.scalar_rows)

    def add(self, instance: Any) -> None:
        self.added.append(instance)
        if getattr(instance, "id", None) is None:
            instance.id = 101

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def refresh(self, instance: Any) -> None:
        return None

    def get(self, model: type, object_id: int) -> Any:
        return self.objects.get(object_id)


class FakeScalarResult:
    def __init__(self, values: list[Any]) -> None:
        self.values = values

    def first(self) -> Any:
        return self.values[0] if self.values else None

    def all(self) -> list[Any]:
        return list(self.values)
