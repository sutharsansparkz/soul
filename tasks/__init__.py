"""Background tasks for SOUL."""

from soul.celery_app import get_celery_app

celery_app = get_celery_app()

__all__ = ["celery_app", "get_celery_app"]
