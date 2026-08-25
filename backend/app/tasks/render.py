from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.core.queues import JobQueue
from app.models.job import Job
from app.models.project import Project
from app.tasks.base import execute_stage


def _run(_db: Session, job: Job, project: Project) -> dict:
    return {"title": project.title, "job_id": str(job.id)}


@celery_app.task(name="scenecraft.render")
def render(job_id: str) -> dict:
    return execute_stage(job_id, JobQueue.RENDER, _run)
