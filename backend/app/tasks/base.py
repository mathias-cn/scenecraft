"""TrackedTask: persiste jobs, retry com backoff e semáforo por provider."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from celery import Task
from celery.exceptions import Retry
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.job_groups import settle_job_group
from app.core.provider_limiter import provider_semaphore
from app.core.retries import retry_countdown
from app.db import SessionLocal
from app.models.enums import JobStatus
from app.models.job import Job
from app.models.project import Project

logger = logging.getLogger(__name__)

WorkFn = Callable[..., dict[str, Any] | None]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TrackedTask(Task):
    """Base Celery: grava a tabela `jobs`, retry exponencial (3 tentativas) e semáforo Redis."""

    abstract = True
    provider: str | None = None
    max_retries = 2  # 3 execuções no total (1 inicial + 2 retries)
    autoretry_for = ()
    throws = (Retry,)

    def run_tracked(self, job_id: str, work: WorkFn, *args: Any, **kwargs: Any) -> dict[str, Any]:
        db = SessionLocal()
        try:
            job = db.get(Job, UUID(str(job_id)))
            if job is None:
                logger.error("job %s não encontrado", job_id)
                return {"ok": False, "error": "job_not_found"}
            project = db.get(Project, job.project_id)
            if project is None:
                job.status = JobStatus.FAILED
                job.error = "project_not_found"
                job.finished_at = _now()
                db.commit()
                return {"ok": False, "error": "project_not_found"}

            job.status = JobStatus.RUNNING
            job.started_at = job.started_at or _now()
            job.attempt_count = int(self.request.retries) + 1
            job.error = None
            db.commit()

            try:
                with provider_semaphore.hold(self.provider):
                    result = work(self, db, job, project, *args, **kwargs) or {}
            except Retry:
                raise
            except Exception as exc:
                return self._on_failure(db, job, project, exc)

            job.status = JobStatus.SUCCEEDED
            job.result = result
            job.error = None
            job.finished_at = _now()
            db.commit()
            self._maybe_advance(db, job, project)
            return {"ok": True, "job_id": str(job.id), "result": result}
        finally:
            db.close()

    def _on_failure(
        self,
        db: Session,
        job: Job,
        project: Project | None,
        exc: BaseException,
    ) -> dict[str, Any]:
        retries_left = int(self.max_retries) - int(self.request.retries)
        job.error = str(exc)
        if retries_left > 0 and not getattr(exc, "permanent", False):
            job.status = JobStatus.RETRYING
            db.commit()
            countdown = retry_countdown(int(self.request.retries), settings.celery_retry_backoff_base)
            logger.warning(
                "job %s falhou (tentativa %s/%s), retry em %ss: %s",
                job.id,
                job.attempt_count,
                int(self.max_retries) + 1,
                countdown,
                exc,
            )
            raise self.retry(exc=exc, countdown=countdown)

        job.status = JobStatus.FAILED
        job.finished_at = _now()
        db.commit()
        logger.exception("job %s esgotou retries", job.id)
        self._maybe_advance(db, job, project)
        return {"ok": False, "error": str(exc)}

    def _maybe_advance(self, db: Session, job: Job, project: Project | None) -> None:
        settle_job_group(db, job, project)


def pipeline_task(*, name: str, provider: str | None = None, **celery_opts):
    """Decorator: task Celery com TrackedTask, retry e rate limit do provider."""

    from app.celery_app import celery_app

    def decorator(fn: WorkFn):
        prov = provider

        class BoundTracked(TrackedTask):
            abstract = True
            provider = prov

        @celery_app.task(
            bind=True,
            base=BoundTracked,
            name=name,
            max_retries=settings.celery_task_max_retries,
            track_started=True,
            **celery_opts,
        )
        def wrapped(self: TrackedTask, job_id: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
            return self.run_tracked(job_id, fn, *args, **kwargs)

        return wrapped

    return decorator
