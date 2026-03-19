from __future__ import annotations

from datetime import datetime, timezone

from soul import db
from soul.config import get_settings
from soul.memory.episodic import EpisodicMemoryRepository
from soul.tasks import celery_app


def run_hms_decay() -> dict[str, int]:
    settings = get_settings()
    db.init_db(settings.database_url)
    repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)
    return repo.decay_all(now=datetime.now(timezone.utc))


if celery_app is not None:

    @celery_app.task(name="soul.tasks.hms_decay.nightly_hms_decay_task")
    def nightly_hms_decay_task() -> dict[str, int]:
        return run_hms_decay()
