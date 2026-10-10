"""Validated public Watch condition data and literal normalization."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass


def normalize(value: str) -> str:
    """The single NFKC + casefold comparison rule; preserve originals for display."""
    return unicodedata.normalize("NFKC", value).casefold()


def validate_text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or not 1 <= len(value) <= maximum:
        raise ValueError(f"{field} must be a nonblank string of 1–{maximum} characters")
    return value


def validate_keywords(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 20:
        raise ValueError(f"{field} must be a list of at most 20 strings")
    return [validate_text(keyword, field, 100) for keyword in value]


def validate_positive_int(value: object, field: str) -> int:
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise ValueError(f"{field} must be a positive SQLite integer")
    return value


@dataclass(frozen=True)
class WatchCondition:
    id: int
    name: str
    description: str
    keywords: list[str]
    excluded_keywords: list[str]
    active: bool
    revision: int
    start_article_id: int
    created_at: str
    updated_at: str
    deleted_at: str | None
