"""Small helpers for front matter values."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

MISSING = object()


def parse_instant(value: Any) -> datetime | None:
    """ISO 8601 datetime with an explicit UTC offset (e.g. 2026-06-30T14:00:00Z), else None."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text[-1:] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def parse_now(text: str) -> datetime:
    """`--now` argument: an ISO datetime with offset, or a date meaning its midnight UTC."""
    instant = parse_instant(text)
    if instant is not None:
        return instant
    return datetime.combine(date.fromisoformat(text), datetime.min.time(), tzinfo=timezone.utc)


def describe(value: Any) -> str:
    """YAML-ish name of a value's type, for error messages."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "mapping"
    return type(value).__name__


def show(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
