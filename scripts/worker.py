from __future__ import annotations

import os
import sys
import time


def main() -> None:
    loglevel = os.getenv("SOUL_CELERY_LOGLEVEL", "info")
    concurrency = os.getenv("SOUL_CELERY_CONCURRENCY")

    try:
        import celery  # noqa: F401
    except ImportError:
        _fallback_worker()
        return

    command = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "soul.tasks",
        "worker",
        "--loglevel",
        loglevel,
    ]
    if concurrency:
        command.extend(["--concurrency", concurrency])
    os.execv(command[0], command)


def _fallback_worker() -> None:
    from soul import db
    from soul.config import get_settings
    from soul.evolution.reflection import generate_monthly_reflection
    from soul.tasks.consolidate import consolidate_pending_sessions
    from soul.tasks.drift_weekly import derive_resonance_signals, run_drift_task

    settings = get_settings()
    db.init_db(settings.database_url)

    interval_seconds = int(os.getenv("SOUL_WORKER_INTERVAL_SECONDS", "300"))
    print(f"SOUL worker fallback starting with interval={interval_seconds}s", flush=True)

    while True:
        results = consolidate_pending_sessions(
            database_url=settings.database_url,
            story_path=settings.user_story_file,
            memory_path=settings.episodic_memory_file,
            shared_language_path=settings.shared_language_file,
            ledger_path=settings.consolidation_ledger_file,
            source="worker-fallback",
            settings=settings,
        )
        drift_signals = derive_resonance_signals(settings.database_url)
        run_drift_task(settings.personality_file, settings.drift_log_file, drift_signals)
        reflection_entry = generate_monthly_reflection(settings)
        print(
            "worker cycle complete: "
            f"sessions={len(results)} "
            f"memories={sum(int(item['memories_added']) for item in results)} "
            f"story_updates={sum(1 for item in results if item['story_updated'])} "
            f"reflection={'1' if reflection_entry else '0'}",
            flush=True,
        )
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
