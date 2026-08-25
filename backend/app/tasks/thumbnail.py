from app.tasks.base import pipeline_task


@pipeline_task(name="scenecraft.thumbnail", provider="higgsfield")
def thumbnail(_self, _db, job, project) -> dict:
    return {"title": project.title, "job_id": str(job.id)}
