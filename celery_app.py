from __future__ import annotations

from functools import lru_cache

from soul.config import Settings, get_settings


def _create_celery_app(settings: Settings):
    try:
        from celery import Celery
        from celery.schedules import crontab
    except ImportError:
        return None

    app = Celery("soul", broker=settings.redis_url, backend=settings.redis_url)
    app.conf.update(
        timezone=settings.timezone_name,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        imports=(
            "soul.tasks.consolidate",
            "soul.tasks.drift_weekly",
            "soul.tasks.proactive",
            "soul.evolution.reflection",
        ),
        beat_schedule={
            "nightly-consolidation": {
                "task": "soul.tasks.consolidate.nightly_consolidation_task",
                "schedule": crontab(hour=2, minute=0),
            },
            "weekly-drift": {
                "task": "soul.tasks.drift_weekly.weekly_drift_task",
                "schedule": crontab(day_of_week="sun", hour=3, minute=0),
            },
            "proactive-presence": {
                "task": "soul.tasks.proactive.proactive_presence_task",
                "schedule": crontab(hour="9", minute=0),
            },
            "monthly-reflection": {
                "task": "soul.evolution.reflection.monthly_reflection_task",
                "schedule": crontab(day_of_month="1", hour=4, minute=0),
            },
        },
    )
    return app


@lru_cache(maxsize=1)
def get_celery_app():
    return _create_celery_app(get_settings())
