from app.core.audio_stage import run_audio_stage
from app.tasks.base import pipeline_task


@pipeline_task(name="scenecraft.audio_gen", provider="openai")
def audio_gen(_self, db, job, project) -> dict:
    return run_audio_stage(project.id, job.payload or {}, db=db)


@pipeline_task(name="scenecraft.retranscribe_and_align", provider="openai")
def retranscribe_and_align(_self, db, job, project) -> dict:
    return run_audio_stage(project.id, job.payload or {}, db=db)
