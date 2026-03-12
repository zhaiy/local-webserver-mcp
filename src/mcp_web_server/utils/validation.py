"""Input validation helpers."""

from __future__ import annotations

from urllib.parse import urlparse


ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}


def validate_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def validate_range(name: str, value: int, min_value: int, max_value: int) -> str | None:
    if not (min_value <= value <= max_value):
        return f"{name} must be between {min_value} and {max_value}"
    return None
