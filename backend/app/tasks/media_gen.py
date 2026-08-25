from app.tasks.base import pipeline_task


@pipeline_task(name="scenecraft.media_gen", provider="higgsfield")
def media_gen(_self, _db, job, project) -> dict:
    return {"title": project.title, "job_id": str(job.id)}
