from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone


def main() -> None:
    loglevel = os.getenv("SOUL_CELERY_LOGLEVEL", "info")

    try:
        import celery  # noqa: F401
    except ImportError:
        _fallback_beat()
        return

    command = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "soul.tasks",
        "beat",
        "--loglevel",
        loglevel,
    ]
    os.execv(command[0], command)


def _fallback_beat() -> None:
    from soul import db
    from soul.config import get_settings
    from soul.core.presence_context import build_presence_context
    from soul.memory.user_story import UserStoryRepository
    from soul.tasks.proactive import build_reach_out_candidates, dispatch_reach_out_candidates, save_reach_out_candidates

    settings = get_settings()
    db.init_db(settings.database_url)
    story_repo = UserStoryRepository(settings.user_story_file)

    interval_seconds = int(os.getenv("SOUL_BEAT_INTERVAL_SECONDS", "900"))
    print(f"SOUL beat fallback starting with interval={interval_seconds}s", flush=True)

    while True:
        presence_context = build_presence_context(settings.database_url, settings)
        candidates = build_reach_out_candidates(
            days_since_last_chat=presence_context["days_since_last_chat"],
            story=story_repo.load(),
            today=datetime.now(timezone.utc),
            stress_signal_dates=presence_context["stress_signal_dates"],
            milestones_today=presence_context["milestones_today"],
        )
        save_reach_out_candidates(settings.reach_out_candidates_file, candidates)
        delivery = dispatch_reach_out_candidates(settings, candidates)
        print(
            f"beat cycle complete: candidates={len(candidates)} delivered={delivery['sent']}",
            flush=True,
        )
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
