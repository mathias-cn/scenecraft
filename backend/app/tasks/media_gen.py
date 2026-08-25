from app.core.generate_scene_media import (
    generate_project_media,
    generate_scene_media as run_generate_scene_media,
)
from app.tasks.base import pipeline_task


@pipeline_task(name="scenecraft.media_gen", provider=None)
def media_gen(_self, db, job, project) -> dict:
    """O semáforo Redis é adquirido em generate_scene_media com o provider ativo."""
    payload = job.payload or {}
    scene_id = payload.get("scene_id")
    group_id = job.job_group_id
    if scene_id:
        return run_generate_scene_media(project.id, scene_id, db=db, job_group_id=group_id)
    return generate_project_media(project.id, db=db, job_group_id=group_id)


def _register_scene_task():
    from app.celery_app import celery_app

    @celery_app.task(name="scenecraft.generate_scene_media")
    def generate_scene_media(project_id: str, scene_id: str) -> dict:
        return run_generate_scene_media(project_id, scene_id)

    return generate_scene_media


generate_scene_media = _register_scene_task()
