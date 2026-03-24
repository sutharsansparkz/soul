from __future__ import annotations

from datetime import datetime as real_datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from soul import db
from soul.config import Settings
from soul.memory.episodic import EpisodicMemoryRepository
import soul.cli as cli
from typer.testing import CliRunner


def _settings(tmp_path) -> Settings:  # noqa: ANN001
    return Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )


@pytest.mark.parametrize(
    ("iso_value", "expected"),
    [
        ("2026-03-20T11:30:00+00:00", "30m ago"),
        ("2026-03-19T12:00:00+00:00", "yesterday"),
        ("2026-03-17T12:00:00+00:00", "3 days ago"),
        ("2026-03-06T12:00:00+00:00", "2 weeks ago"),
        ("2026-01-19T12:00:00+00:00", "2 months ago"),
        ("2025-03-20T12:00:00+00:00", "1 year ago"),
    ],
)
def test_relative_time_formats_expected_labels(monkeypatch, iso_value: str, expected: str):
    fixed_now = real_datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        cli,
        "datetime",
        SimpleNamespace(now=lambda tz: fixed_now, fromisoformat=real_datetime.fromisoformat),
    )

    assert cli._relative_time(iso_value) == expected


def test_memories_list_uses_relative_timestamps(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)
    settings.soul_data_dir.mkdir(parents=True, exist_ok=True)

    fixed_now = real_datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        cli,
        "datetime",
        SimpleNamespace(now=lambda tz: fixed_now, fromisoformat=real_datetime.fromisoformat),
    )

    episodic_repo = EpisodicMemoryRepository(settings=settings)
    episodic_repo.add_text(
        "I launched the beta and felt alive.",
        emotional_tag="celebrating",
        metadata={
            "session_id": "s1",
            "user_id": settings.user_id,
            "timestamp": (fixed_now - timedelta(minutes=30)).isoformat(),
        },
    )
    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, SimpleNamespace(name="Ara")))

    result = CliRunner().invoke(cli.app, ["memories"])

    assert result.exit_code == 0
    assert "30m ago" in result.stdout
    assert "2026-03-20T11:30:00+00:00" not in result.stdout


def test_memories_cold_uses_relative_timestamps(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)
    settings.soul_data_dir.mkdir(parents=True, exist_ok=True)

    fixed_now = real_datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        cli,
        "datetime",
        SimpleNamespace(now=lambda tz: fixed_now, fromisoformat=real_datetime.fromisoformat),
    )

    episodic_repo = EpisodicMemoryRepository(settings=settings)
    created = episodic_repo.add_text(
        "small weather remark",
        emotional_tag="neutral",
        metadata={
            "session_id": "s1",
            "user_id": settings.user_id,
            "timestamp": (fixed_now - timedelta(days=60)).isoformat(),
        },
    )
    db.update_episodic_memory_fields(
        settings.database_url,
        str(created.metadata.get("memory_id", created.id)),
        tier="cold",
    )
    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, SimpleNamespace(name="Ara")))

    result = CliRunner().invoke(cli.app, ["memories", "cold"])

    assert result.exit_code == 0
    assert "2 months ago" in result.stdout
    assert "2026-01-19T12:00:00+00:00" not in result.stdout
