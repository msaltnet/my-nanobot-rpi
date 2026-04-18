"""TrackedItem 관리: CRUD + 검증 + 기본 시드."""
from __future__ import annotations

import re
from typing import Final

from msalt.storage import Storage


VALID_SCHEMAS: Final = ("freetext", "duration", "quantity", "boolean")
TIME_RE: Final = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

DEFAULT_SEEDS: Final = [
    {"name": "수면", "schema": "duration", "unit": None, "schedule_time": "08:00"},
    {"name": "음주", "schema": "quantity", "unit": "잔", "schedule_time": "22:00"},
    {"name": "영어공부", "schema": "duration", "unit": None, "schedule_time": "22:00"},
]


class ItemAlreadyExists(Exception):
    pass


class ItemNotFound(Exception):
    pass


class TrackedItemManager:
    def __init__(self, storage: Storage):
        self.storage = storage

    @staticmethod
    def _validate(name: str, schema: str, unit: str | None,
                  schedule_time: str) -> None:
        if not name:
            raise ValueError("name must be non-empty")
        if schema not in VALID_SCHEMAS:
            raise ValueError(
                f"schema must be one of {VALID_SCHEMAS}, got {schema!r}"
            )
        if not TIME_RE.match(schedule_time):
            raise ValueError(
                f"schedule_time must be 'HH:MM' (00-23:00-59), got {schedule_time!r}"
            )
        if schema == "quantity" and not unit:
            raise ValueError("schema=quantity requires unit")
        if schema != "quantity" and unit is not None:
            raise ValueError("unit only allowed for schema=quantity")

    def add(self, name: str, schema: str, unit: str | None,
            schedule_time: str, frequency: str = "daily") -> int:
        self._validate(name, schema, unit, schedule_time)
        if self.storage.get_tracked_item_by_name(name) is not None:
            raise ItemAlreadyExists(name)
        return self.storage.insert_tracked_item(
            name, schema, unit, schedule_time, frequency
        )

    def get(self, name: str) -> dict | None:
        return self.storage.get_tracked_item_by_name(name)

    def list_all(self) -> list[dict]:
        return self.storage.list_tracked_items()

    def delete(self, name: str) -> None:
        if self.storage.get_tracked_item_by_name(name) is None:
            raise ItemNotFound(name)
        self.storage.delete_tracked_item(name)

    def seed_defaults(self) -> int:
        """빈 테이블이면 기본 항목들 삽입. 그렇지 않으면 no-op. 삽입 수 반환."""
        if self.list_all():
            return 0
        for seed in DEFAULT_SEEDS:
            self.storage.insert_tracked_item(
                seed["name"], seed["schema"], seed["unit"],
                seed["schedule_time"], "daily",
            )
        return len(DEFAULT_SEEDS)
