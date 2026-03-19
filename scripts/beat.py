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
    from soul.memory.user_story import UserStoryRepository
    from soul.tasks.proactive import build_reach_out_candidates, dispatch_reach_out_candidates, save_reach_out_candidates

    settings = get_settings()
    db.init_db(settings.database_url)
    story_repo = UserStoryRepository(settings.user_story_file)

    interval_seconds = int(os.getenv("SOUL_BEAT_INTERVAL_SECONDS", "900"))
    print(f"SOUL beat fallback starting with interval={interval_seconds}s", flush=True)

    while True:
        last_message_at = db.get_last_message_timestamp(settings.database_url)
        days_since_last_chat = None
        if last_message_at:
            timestamp = datetime.fromisoformat(last_message_at)
            delta = datetime.now(timezone.utc) - timestamp
            days_since_last_chat = delta.days
        candidates = build_reach_out_candidates(
            days_since_last_chat=days_since_last_chat,
            story=story_repo.load(),
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
