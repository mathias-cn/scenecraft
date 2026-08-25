"""Task Celery: transcrever o áudio de um projeto."""

from app.core.transcribe_project import transcribe_project
from app.tasks.base import pipeline_task


@pipeline_task(name="scenecraft.transcribe", provider="openai")
def transcribe(_self, db, _job, project) -> dict:
    return transcribe_project(project.id, db=db)


def _register_project_id_task():
    from app.celery_app import celery_app

    @celery_app.task(name="scenecraft.transcribe_project")
    def transcribe_project_task(project_id: str) -> dict:
        return transcribe_project(project_id)

    return transcribe_project_task


transcribe_project_task = _register_project_id_task()
