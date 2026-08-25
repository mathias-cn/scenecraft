"""Tasks Celery de geração de personagem (fila media_gen)."""

from __future__ import annotations

from typing import Any

from celery.exceptions import Retry

from app.celery_app import celery_app
from app.core.config import settings
from app.core.generate_character import (
    CharacterNotFound,
    generate_character_asset as run_generate_character_asset,
    generate_character_base_image as run_generate_character_base_image,
    generate_character_set as run_generate_character_set,
)
from app.core.retries import retry_countdown


def _retry_or_raise(task, exc: BaseException) -> None:
    if isinstance(exc, CharacterNotFound) or getattr(exc, "permanent", False):
        raise exc
    retries_left = int(task.max_retries) - int(task.request.retries)
    if retries_left <= 0:
        raise exc
    raise task.retry(
        exc=exc,
        countdown=retry_countdown(int(task.request.retries), settings.celery_retry_backoff_base),
    )


@celery_app.task(
    bind=True,
    name="scenecraft.generate_character_base_image",
    max_retries=settings.celery_task_max_retries,
    track_started=True,
    throws=(Retry,),
)
def generate_character_base_image(self, character_id: str) -> dict[str, Any]:
    try:
        return run_generate_character_base_image(character_id)
    except Exception as exc:
        _retry_or_raise(self, exc)
        raise


@celery_app.task(
    bind=True,
    name="scenecraft.generate_character_set",
    max_retries=settings.celery_task_max_retries,
    track_started=True,
    throws=(Retry,),
)
def generate_character_set(self, character_id: str) -> dict[str, Any]:
    try:
        return run_generate_character_set(character_id)
    except Exception as exc:
        _retry_or_raise(self, exc)
        raise


@celery_app.task(
    bind=True,
    name="scenecraft.generate_character_asset",
    max_retries=settings.celery_task_max_retries,
    track_started=True,
    throws=(Retry,),
)
def generate_character_asset(self, character_id: str, asset_type: str) -> dict[str, Any]:
    try:
        return run_generate_character_asset(character_id, asset_type)
    except Exception as exc:
        _retry_or_raise(self, exc)
        raise
