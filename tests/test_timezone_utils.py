from __future__ import annotations

from datetime import timezone
from zoneinfo import ZoneInfoNotFoundError

import pytest

import soul.core.timezone_utils as timezone_utils


def test_load_timezone_accepts_utc_when_zoneinfo_database_is_missing(monkeypatch):
    monkeypatch.setattr(
        timezone_utils,
        "ZoneInfo",
        lambda name: (_ for _ in ()).throw(ZoneInfoNotFoundError(name)),
    )

    assert timezone_utils.load_timezone("UTC") is timezone.utc


def test_load_timezone_re_raises_for_non_utc_name_when_zoneinfo_database_is_missing(monkeypatch):
    monkeypatch.setattr(
        timezone_utils,
        "ZoneInfo",
        lambda name: (_ for _ in ()).throw(ZoneInfoNotFoundError(name)),
    )

    with pytest.raises(ZoneInfoNotFoundError):
        timezone_utils.load_timezone("Asia/Kolkata")


def test_load_timezone_or_utc_falls_back_to_utc_for_runtime_use(monkeypatch):
    monkeypatch.setattr(
        timezone_utils,
        "ZoneInfo",
        lambda name: (_ for _ in ()).throw(ZoneInfoNotFoundError(name)),
    )

    assert timezone_utils.load_timezone_or_utc("Asia/Kolkata") is timezone.utc
