from celery import Celery
import os

# Get Redis connection URL from environment or default to local host
redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Initialize Celery app, referencing backend.tasks where tasks are defined
celery_app = Celery(
    "myphotos",
    broker=redis_url,
    backend=redis_url,
    include=["backend.tasks"]
)

# Configuration settings
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    worker_pool="threads",
    worker_concurrency=2
)
