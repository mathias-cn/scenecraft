from celery import Celery
from kombu import Exchange, Queue

from app.core.config import settings
from app.core.queues import QUEUE_NAMES, TASK_MODULES

celery_app = Celery(
    "scenecraft",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=list(TASK_MODULES),
)

exchange = Exchange("scenecraft", type="direct")

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue=QUEUE_NAMES[0],
    task_default_exchange="scenecraft",
    task_default_routing_key=QUEUE_NAMES[0],
    task_queues=tuple(Queue(name, exchange=exchange, routing_key=name) for name in QUEUE_NAMES),
    task_routes={
        "scenecraft.transcribe": {"queue": "transcribe"},
        "scenecraft.scene_planning": {"queue": "scene_planning"},
        "scenecraft.media_gen": {"queue": "media_gen"},
        "scenecraft.audio_gen": {"queue": "audio_gen"},
        "scenecraft.render": {"queue": "render"},
        "scenecraft.thumbnail": {"queue": "thumbnail"},
        "scenecraft.description": {"queue": "description"},
        "scenecraft.upload": {"queue": "upload"},
    },
    result_expires=86400,
)
