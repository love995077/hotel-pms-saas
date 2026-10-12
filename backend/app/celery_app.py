"""The Celery application object.

Kept apart from the task definitions in `app.worker` so that services can
queue a task by name without importing the worker (which imports the services).
"""

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery("hotel_pms", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    timezone="UTC",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,
    beat_schedule={
        "dispatch-night-audits": {"task": "night_audit.dispatch", "schedule": crontab(minute=5)},
    },
)
