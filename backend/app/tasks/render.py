from app.tasks.base import pipeline_task


@pipeline_task(name="scenecraft.render")
def render(_self, _db, job, project) -> dict:
    return {"title": project.title, "job_id": str(job.id)}
