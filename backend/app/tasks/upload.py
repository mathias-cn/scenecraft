from app.tasks.base import pipeline_task


@pipeline_task(name="scenecraft.upload", provider="youtube")
def upload(_self, _db, job, project) -> dict:
    return {"title": project.title, "job_id": str(job.id)}
