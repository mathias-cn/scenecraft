from app.core.generate_thumbnail import generate_thumbnail as run_generate_thumbnail
from app.tasks.base import pipeline_task


@pipeline_task(name="scenecraft.thumbnail", provider=None)
def thumbnail(_self, db, job, project) -> dict:
    """O semáforo Redis é adquirido em generate_thumbnail com o ImageProvider ativo."""
    result = run_generate_thumbnail(project.id, db=db)
    result["title"] = project.title
    result["job_id"] = str(job.id)
    return result


def _register_generate_thumbnail():
    from app.celery_app import celery_app

    @celery_app.task(name="scenecraft.generate_thumbnail")
    def generate_thumbnail(project_id: str) -> dict:
        return run_generate_thumbnail(project_id)

    return generate_thumbnail


generate_thumbnail = _register_generate_thumbnail()
