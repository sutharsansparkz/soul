"""Mood state helpers."""

from __future__ import annotations

from soul.config import Settings
from soul.core.mood_engine import MoodEngine
from soul.memory.repositories.mood import MoodSnapshotsRepository


def current_mood_state(settings: Settings) -> dict[str, object] | None:
    return MoodSnapshotsRepository(settings.database_url, user_id=settings.user_id).latest()


def analyze_mood(settings: Settings, text: str) -> dict[str, object]:
    snapshot = MoodEngine(settings).analyze(text)
    return {
        "user_mood": snapshot.user_mood,
        "companion_state": snapshot.companion_state,
        "confidence": snapshot.confidence,
        "rationale": snapshot.rationale,
    }
