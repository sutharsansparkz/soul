"""Milestone state helpers."""

from __future__ import annotations

from soul.config import Settings
from soul.memory.repositories.milestones import MilestonesRepository


def list_milestones(settings: Settings, *, limit: int = 200) -> list[dict[str, object]]:
    return MilestonesRepository(settings.database_url).list(limit=limit)
