from app.core.plan_scenes import plan_project_scenes
from app.tasks.base import pipeline_task


@pipeline_task(name="scenecraft.scene_planning", provider="openai")
def scene_planning(_self, db, job, project) -> dict:
    result = plan_project_scenes(project.id, db=db)
    result["job_id"] = str(job.id)
    result["title"] = project.title
    return result
