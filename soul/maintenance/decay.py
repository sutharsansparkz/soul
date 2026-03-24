"""HMS decay maintenance."""

from __future__ import annotations

from soul.config import get_settings
from soul.memory.episodic import EpisodicMemoryRepository


def run_hms_decay(*, settings=None) -> dict[str, int]:
    resolved_settings = settings or get_settings()
    return EpisodicMemoryRepository(settings=resolved_settings).decay_all()
