from __future__ import annotations

from datetime import timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_UTC_ZONE_NAMES = {"utc", "etc/utc", "z", "gmt", "etc/gmt"}


def load_timezone(name: str) -> tzinfo:
    normalized = name.strip()
    try:
        return ZoneInfo(normalized)
    except ZoneInfoNotFoundError:
        if normalized.casefold() in _UTC_ZONE_NAMES:
            return timezone.utc
        raise


def load_timezone_or_utc(name: str) -> tzinfo:
    try:
        return load_timezone(name)
    except ZoneInfoNotFoundError:
        return timezone.utc
