import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.db import SessionLocal
from app.models.enums import JobStatus, ProjectStage, ProjectStatus
from app.models.job import Job
from app.models.project import Project

PIPELINE_STAGES = [
    ProjectStage.INGEST,
    ProjectStage.TRANSCRIBE,
    ProjectStage.TRANSLATE,
    ProjectStage.SCENE,
    ProjectStage.AUDIO,
    ProjectStage.ASSEMBLE,
    ProjectStage.THUMBNAIL,
    ProjectStage.DESCRIBE,
    ProjectStage.UPLOAD,
    ProjectStage.COMPLETE,
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _save(db: Session) -> None:
    db.commit()


@celery_app.task(name="scenecraft.run_pipeline")
def run_pipeline(job_id: str) -> dict:
    db = SessionLocal()
    try:
        job = db.get(Job, uuid.UUID(job_id))
        if job is None:
            return {"ok": False, "error": "job_not_found"}

        project = db.get(Project, job.project_id)
        if project is None:
            return {"ok": False, "error": "project_not_found"}

        job.status = JobStatus.RUNNING
        job.started_at = _now()
        job.attempt_count += 1
        project.status = ProjectStatus.RUNNING
        _save(db)

        for stage in PIPELINE_STAGES:
            job.stage = stage
            project.current_stage = stage
            project.updated_at = _now()
            _save(db)

        job.status = JobStatus.COMPLETED
        job.finished_at = _now()
        job.result = {"stages": [stage.value for stage in PIPELINE_STAGES]}
        project.status = ProjectStatus.COMPLETED
        project.updated_at = _now()
        _save(db)
        return {"ok": True, "job_id": str(job.id), "project_id": str(project.id)}
    except Exception as exc:  # noqa: BLE001 — jobs must never leave the worker hanging
        job = db.get(Job, uuid.UUID(job_id))
        if job is not None:
            job.status = JobStatus.FAILED
            job.error = str(exc)
            job.finished_at = _now()
            project = db.get(Project, job.project_id)
            if project is not None:
                project.status = ProjectStatus.FAILED
                project.updated_at = _now()
            _save(db)
        return {"ok": False, "error": str(exc)}
    finally:
        db.close()
