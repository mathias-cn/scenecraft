from app.core.generate_scene_media import generate_project_media, generate_scene_media
from app.tasks.base import pipeline_task


@pipeline_task(name="scenecraft.media_gen", provider=None)
def media_gen(_self, db, job, project) -> dict:
    """O semáforo Redis é adquirido em generate_scene_media com o provider ativo."""
    payload = job.payload or {}
    scene_id = payload.get("scene_id")
    if scene_id:
        return generate_scene_media(project.id, scene_id, db=db)
    return generate_project_media(project.id, db=db)
