"""Máquina de estados de `projects.current_stage`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.queues import QueueStep, step_for_queue, step_for_stage
from app.models.enums import JobStatus, ProjectStage, ProjectStatus
from app.models.job import Job
from app.models.project import Project

LINEAR_STAGES: tuple[ProjectStage, ...] = (
    ProjectStage.CREATED,
    ProjectStage.TRANSCRIBING,
    ProjectStage.TRANSCRIPT_REVIEW,
    ProjectStage.SCENE_PLANNING,
    ProjectStage.SCENE_REVIEW,
    ProjectStage.GENERATING_MEDIA,
    ProjectStage.MEDIA_REVIEW,
    ProjectStage.AUDIO_STAGE,
    ProjectStage.AUDIO_REVIEW,
    ProjectStage.RENDERING,
    ProjectStage.RENDER_REVIEW,
    ProjectStage.THUMBNAIL_STAGE,
    ProjectStage.DESCRIPTION_STAGE,
    ProjectStage.READY_TO_PUBLISH,
    ProjectStage.UPLOADING,
    ProjectStage.PUBLISHED,
)

REVIEW_AUTO_FLAGS: dict[ProjectStage, str] = {
    ProjectStage.TRANSCRIPT_REVIEW: "auto_transcribe",
    ProjectStage.SCENE_REVIEW: "auto_scene_planning",
    ProjectStage.MEDIA_REVIEW: "auto_media",
    ProjectStage.AUDIO_REVIEW: "auto_audio",
    ProjectStage.RENDER_REVIEW: "auto_render",
    ProjectStage.READY_TO_PUBLISH: "auto_publish",
}

TERMINAL_STAGES = frozenset({ProjectStage.PUBLISHED, ProjectStage.FAILED})


class IllegalTransition(Exception):
    pass


class ProjectNotFound(Exception):
    pass


@dataclass(frozen=True)
class AdvanceResult:
    project_id: UUID
    from_stage: ProjectStage
    to_stage: ProjectStage
    status: ProjectStatus
    paused_for_review: bool
    dispatched_job_id: UUID | None = None
    auto_advanced: bool = False


def parse_stage(value: ProjectStage | str) -> ProjectStage:
    if isinstance(value, ProjectStage):
        return value
    raw = value.strip()
    try:
        return ProjectStage(raw.lower())
    except ValueError:
        return ProjectStage[raw.upper()]


def linear_next(stage: ProjectStage) -> ProjectStage | None:
    if stage not in LINEAR_STAGES or stage in TERMINAL_STAGES:
        return None
    index = LINEAR_STAGES.index(stage)
    if index + 1 >= len(LINEAR_STAGES):
        return None
    return LINEAR_STAGES[index + 1]


def is_valid_transition(from_stage: ProjectStage, to_stage: ProjectStage) -> bool:
    if to_stage is ProjectStage.FAILED:
        return from_stage not in TERMINAL_STAGES
    return linear_next(from_stage) is to_stage


def is_review_stage(stage: ProjectStage) -> bool:
    return stage in REVIEW_AUTO_FLAGS


def auto_flag_enabled(automation_config: dict[str, Any] | None, stage: ProjectStage) -> bool:
    flag = REVIEW_AUTO_FLAGS.get(stage)
    if not flag:
        return False
    value = (automation_config or {}).get(flag, False)
    return value in (True, 1, "1", "true", "True", "yes", "on")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enqueue_job(step: QueueStep, job_id: UUID) -> None:
    from app.celery_app import celery_app

    celery_app.send_task(step.task_name, args=[str(job_id)], queue=step.queue.value)


def _session(db: Session | None) -> tuple[Session, bool]:
    if db is not None:
        return db, False
    from app.db import SessionLocal

    return SessionLocal(), True


def _load_project(db: Session, project_id: UUID | str) -> Project:
    pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
    project = db.get(Project, pid)
    if project is None:
        raise ProjectNotFound(str(pid))
    return project


def _dispatch_work(db: Session, project: Project, stage: ProjectStage) -> Job:
    step = step_for_stage(stage)
    if step is None:
        raise IllegalTransition(f"{stage.value} não possui job associado")
    source_type = project.source_type.value if hasattr(project.source_type, "value") else str(project.source_type)
    job = Job(
        id=uuid4(),
        project_id=project.id,
        stage=stage,
        job_type=step.queue.value,
        status=JobStatus.PENDING,
        payload={"source_type": source_type, "source_ref": project.source_ref},
    )
    db.add(job)
    db.flush()
    enqueue_job(step, job.id)
    return job


def advance_stage(
    project_id: UUID | str,
    from_stage: ProjectStage | str,
    db: Session | None = None,
) -> AdvanceResult:
    """Valida a transição linear, atualiza o projeto e despacha o próximo job ou pausa para review."""
    expected = parse_stage(from_stage)
    session, owns = _session(db)
    try:
        project = _load_project(session, project_id)
        current = parse_stage(project.current_stage)
        if current is not expected:
            raise IllegalTransition(
                f"projeto em {current.value}, esperado {expected.value}"
            )
        nxt = linear_next(current)
        if nxt is None:
            raise IllegalTransition(f"não há estágio seguinte a partir de {current.value}")

        project.current_stage = nxt
        project.updated_at = _now()

        if nxt is ProjectStage.PUBLISHED:
            project.status = ProjectStatus.COMPLETED
            session.commit()
            return AdvanceResult(
                project_id=project.id,
                from_stage=expected,
                to_stage=nxt,
                status=project.status,
                paused_for_review=False,
            )

        if is_review_stage(nxt) and not auto_flag_enabled(project.automation_config, nxt):
            project.status = ProjectStatus.PAUSED_FOR_REVIEW
            session.commit()
            return AdvanceResult(
                project_id=project.id,
                from_stage=expected,
                to_stage=nxt,
                status=project.status,
                paused_for_review=True,
            )

        if is_review_stage(nxt) and auto_flag_enabled(project.automation_config, nxt):
            session.flush()
            nested = advance_stage(project.id, nxt, db=session)
            return AdvanceResult(
                project_id=nested.project_id,
                from_stage=expected,
                to_stage=nested.to_stage,
                status=nested.status,
                paused_for_review=nested.paused_for_review,
                dispatched_job_id=nested.dispatched_job_id,
                auto_advanced=True,
            )

        project.status = ProjectStatus.RUNNING
        job = _dispatch_work(session, project, nxt)
        session.commit()
        return AdvanceResult(
            project_id=project.id,
            from_stage=expected,
            to_stage=nxt,
            status=project.status,
            paused_for_review=False,
            dispatched_job_id=job.id,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        if owns:
            session.close()


def start_pipeline(db: Session, project: Project, payload: dict[str, Any] | None = None) -> AdvanceResult:
    _ = payload
    return advance_stage(project.id, ProjectStage.CREATED, db=db)


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
        project.current_stage = ProjectStage.FAILED
        project.status = ProjectStatus.FAILED
        project.updated_at = _now()
    db.commit()


def complete_and_advance(
    db: Session,
    job: Job,
    project: Project,
    result: dict[str, Any] | None = None,
) -> AdvanceResult:
    step = step_for_queue(job.job_type)
    job.status = JobStatus.COMPLETED
    job.result = result or {}
    job.finished_at = _now()
    db.flush()
    return advance_stage(project.id, step.stage, db=db)
