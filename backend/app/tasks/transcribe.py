from app.tasks.base import pipeline_task


@pipeline_task(name="scenecraft.transcribe", provider="openai")
def transcribe(_self, _db, job, project) -> dict:
    return {"title": project.title, "source_ref": project.source_ref, "job_id": str(job.id)}
