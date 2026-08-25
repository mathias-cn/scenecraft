"""Filas Celery por tipo de job."""

from __future__ import annotations

import enum
from dataclasses import dataclass

from app.models.enums import ProjectStage


class JobQueue(str, enum.Enum):
    TRANSCRIBE = "transcribe"
    SCENE_PLANNING = "scene_planning"
    MEDIA_GEN = "media_gen"
    AUDIO_GEN = "audio_gen"
    RENDER = "render"
    THUMBNAIL = "thumbnail"
    DESCRIPTION = "description"
    UPLOAD = "upload"


@dataclass(frozen=True)
class QueueStep:
    queue: JobQueue
    task_name: str
    stage: ProjectStage


PIPELINE: tuple[QueueStep, ...] = (
    QueueStep(JobQueue.TRANSCRIBE, "scenecraft.transcribe", ProjectStage.TRANSCRIBE),
    QueueStep(JobQueue.SCENE_PLANNING, "scenecraft.scene_planning", ProjectStage.SCENE),
    QueueStep(JobQueue.MEDIA_GEN, "scenecraft.media_gen", ProjectStage.SCENE),
    QueueStep(JobQueue.AUDIO_GEN, "scenecraft.audio_gen", ProjectStage.AUDIO),
    QueueStep(JobQueue.RENDER, "scenecraft.render", ProjectStage.ASSEMBLE),
    QueueStep(JobQueue.THUMBNAIL, "scenecraft.thumbnail", ProjectStage.THUMBNAIL),
    QueueStep(JobQueue.DESCRIPTION, "scenecraft.description", ProjectStage.DESCRIBE),
    QueueStep(JobQueue.UPLOAD, "scenecraft.upload", ProjectStage.UPLOAD),
)

QUEUE_NAMES: tuple[str, ...] = tuple(step.queue.value for step in PIPELINE)

TASK_MODULES: tuple[str, ...] = (
    "app.tasks.transcribe",
    "app.tasks.scene_planning",
    "app.tasks.media_gen",
    "app.tasks.audio_gen",
    "app.tasks.render",
    "app.tasks.thumbnail",
    "app.tasks.description",
    "app.tasks.upload",
)


def step_for_queue(queue: JobQueue | str) -> QueueStep:
    name = queue.value if isinstance(queue, JobQueue) else queue
    for step in PIPELINE:
        if step.queue.value == name:
            return step
    raise KeyError(f"fila desconhecida: {name}")


def next_step(queue: JobQueue | str) -> QueueStep | None:
    current = step_for_queue(queue)
    index = PIPELINE.index(current)
    if index + 1 >= len(PIPELINE):
        return None
    return PIPELINE[index + 1]


def first_step() -> QueueStep:
    return PIPELINE[0]
