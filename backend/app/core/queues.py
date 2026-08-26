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


@dataclass(frozen=True)
class QueueStep:
    queue: JobQueue
    task_name: str
    stage: ProjectStage


PIPELINE: tuple[QueueStep, ...] = (
    QueueStep(JobQueue.TRANSCRIBE, "scenecraft.transcribe", ProjectStage.TRANSCRIBING),
    QueueStep(JobQueue.SCENE_PLANNING, "scenecraft.scene_planning", ProjectStage.SCENE_PLANNING),
    QueueStep(JobQueue.MEDIA_GEN, "scenecraft.media_gen", ProjectStage.GENERATING_MEDIA),
    QueueStep(JobQueue.AUDIO_GEN, "scenecraft.audio_gen", ProjectStage.AUDIO_STAGE),
    QueueStep(JobQueue.RENDER, "scenecraft.render", ProjectStage.RENDERING),
    QueueStep(JobQueue.THUMBNAIL, "scenecraft.thumbnail", ProjectStage.THUMBNAIL_STAGE),
    QueueStep(JobQueue.DESCRIPTION, "scenecraft.description", ProjectStage.DESCRIPTION_STAGE),
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
)

STAGE_TO_STEP: dict[ProjectStage, QueueStep] = {step.stage: step for step in PIPELINE}


def step_for_queue(queue: JobQueue | str) -> QueueStep:
    name = queue.value if isinstance(queue, JobQueue) else queue
    for step in PIPELINE:
        if step.queue.value == name:
            return step
    raise KeyError(f"fila desconhecida: {name}")


def step_for_stage(stage: ProjectStage) -> QueueStep | None:
    return STAGE_TO_STEP.get(stage)


def next_step(queue: JobQueue | str) -> QueueStep | None:
    current = step_for_queue(queue)
    index = PIPELINE.index(current)
    if index + 1 >= len(PIPELINE):
        return None
    return PIPELINE[index + 1]


def first_step() -> QueueStep:
    return PIPELINE[0]
