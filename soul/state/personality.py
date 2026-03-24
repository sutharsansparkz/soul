"""Personality state helpers."""

from __future__ import annotations

from soul.config import Settings
from soul.memory.repositories.personality import PersonalityStateRepository


def get_personality_state(settings: Settings) -> dict[str, float]:
    return PersonalityStateRepository(settings.database_url, user_id=settings.user_id).get_current_state()
