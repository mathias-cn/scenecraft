from app.core.scene_clips import gere_clipes_projeto
from app.tasks.base import pipeline_task


@pipeline_task(name="scenecraft.render", provider=None)
def render(_self, db, job, project) -> dict:
    result = gere_clipes_projeto(project.id, db=db)
    result["title"] = project.title
    result["job_id"] = str(job.id)
    return result
