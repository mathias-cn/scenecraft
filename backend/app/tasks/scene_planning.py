from app.core.plan_scenes import plan_project_scenes
from app.tasks.base import pipeline_task


@pipeline_task(name="scenecraft.scene_planning", provider="openai")
def scene_planning(_self, db, job, project) -> dict:
    result = plan_project_scenes(project.id, db=db)
    result["job_id"] = str(job.id)
    result["title"] = project.title
    return result


def _register_project_id_task():
    from app.celery_app import celery_app

    @celery_app.task(name="scenecraft.plan_scenes")
    def plan_scenes(project_id: str) -> dict:
        return plan_project_scenes(project_id)

    return plan_scenes


plan_scenes = _register_project_id_task()
