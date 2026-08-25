"""Helpers compartilhados das tasks Celery."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.core.queues import JobQueue, step_for_queue
from app.core.rate_limiter import limiter
from app.core.state_machine import complete_and_advance, fail, mark_running
from app.db import SessionLocal
from app.models.job import Job
from app.models.project import Project

logger = logging.getLogger(__name__)

WorkFn = Callable[[Session, Job, Project], dict[str, Any] | None]


def execute_stage(job_id: str, queue: JobQueue, work: WorkFn) -> dict[str, Any]:
    step = step_for_queue(queue)
    limiter.acquire(queue)
    db = SessionLocal()
    try:
        job = db.get(Job, uuid.UUID(job_id))
        if job is None:
            return {"ok": False, "error": "job_not_found"}
        project = db.get(Project, job.project_id)
        if project is None:
            return {"ok": False, "error": "project_not_found"}

        mark_running(db, job, project, step)
        result = work(db, job, project) or {}
        complete_and_advance(db, job, project, result)
        return {"ok": True, "job_id": str(job.id), "project_id": str(project.id), "queue": queue.value}
    except Exception as exc:  # noqa: BLE001
        logger.exception("job %s na fila %s falhou", job_id, queue.value)
        job = db.get(Job, uuid.UUID(job_id))
        project = db.get(Project, job.project_id) if job is not None else None
        if job is not None:
            fail(db, job, project, str(exc))
        return {"ok": False, "error": str(exc)}
    finally:
        db.close()
