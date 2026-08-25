from app.core.generate_description import generate_description as run_generate_description
from app.tasks.base import pipeline_task


@pipeline_task(name="scenecraft.description", provider=None)
def description(_self, db, job, project) -> dict:
    """O semáforo Redis é adquirido em generate_description (OpenAI)."""
    result = run_generate_description(project.id, db=db)
    result["title"] = project.title
    result["job_id"] = str(job.id)
    return result


def _register_generate_description():
    from app.celery_app import celery_app

    @celery_app.task(name="scenecraft.generate_description")
    def generate_description(project_id: str) -> dict:
        return run_generate_description(project_id)

    return generate_description


generate_description = _register_generate_description()
