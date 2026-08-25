from app.tasks.base import pipeline_task


@pipeline_task(name="scenecraft.audio_gen", provider="elevenlabs")
def audio_gen(_self, _db, job, project) -> dict:
    return {"title": project.title, "job_id": str(job.id)}
