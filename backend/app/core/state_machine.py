"""Máquina de estados do projeto e encadeamento das filas Celery."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.queues import JobQueue, QueueStep, first_step, next_step, step_for_queue
from app.models.enums import JobStatus, ProjectStage, ProjectStatus
from app.models.job import Job
from app.models.project import Project


class IllegalTransition(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def mark_running(db: Session, job: Job, project: Project, step: QueueStep) -> None:
    job.status = JobStatus.RUNNING
    job.started_at = _now()
    job.attempt_count += 1
    job.stage = step.stage
    project.current_stage = step.stage
    project.status = ProjectStatus.RUNNING
    project.updated_at = _now()
    db.commit()


def fail(db: Session, job: Job, project: Project | None, error: str) -> None:
    job.status = JobStatus.FAILED
    job.error = error
    job.finished_at = _now()
    if project is not None:
        project.status = ProjectStatus.FAILED
        project.updated_at = _now()
    db.commit()


def _enqueue(step: QueueStep, job_id: UUID) -> None:
    from app.celery_app import celery_app

    celery_app.send_task(step.task_name, args=[str(job_id)], queue=step.queue.value)


def start_pipeline(db: Session, project: Project, payload: dict[str, Any]) -> Job:
    step = first_step()
    job = Job(
        project_id=project.id,
        stage=step.stage,
        job_type=step.queue.value,
        status=JobStatus.PENDING,
        payload=payload,
    )
    project.current_stage = step.stage
    project.status = ProjectStatus.PENDING
    project.updated_at = _now()
    db.add(job)
    db.commit()
    db.refresh(job)
    _enqueue(step, job.id)
    return job


def complete_and_advance(
    db: Session,
    job: Job,
    project: Project,
    result: dict[str, Any] | None = None,
) -> Job | None:
    step = step_for_queue(job.job_type)
    job.status = JobStatus.COMPLETED
    job.result = result or {}
    job.finished_at = _now()

    following = next_step(step.queue)
    if following is None:
        project.current_stage = ProjectStage.COMPLETE
        project.status = ProjectStatus.COMPLETED
        project.updated_at = _now()
        db.commit()
        return None

    nxt = Job(
        project_id=project.id,
        stage=following.stage,
        job_type=following.queue.value,
        status=JobStatus.PENDING,
        payload=job.payload or {},
    )
    project.current_stage = following.stage
    project.status = ProjectStatus.RUNNING
    project.updated_at = _now()
    db.add(nxt)
    db.commit()
    db.refresh(nxt)
    _enqueue(following, nxt.id)
    return nxt
