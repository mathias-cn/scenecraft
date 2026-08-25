from app.core.audio_stage import run_audio_stage
from app.core.generate_audio import generate_audio as run_generate_audio
from app.core.retranscribe_align import retranscribe_and_align as run_retranscribe_and_align
from app.tasks.base import pipeline_task


@pipeline_task(name="scenecraft.audio_gen", provider=None)
def audio_gen(_self, db, job, project) -> dict:
    return run_audio_stage(project.id, job.payload or {}, db=db)


def _register_generate_audio():
    from app.celery_app import celery_app

    @celery_app.task(name="scenecraft.generate_audio")
    def generate_audio(project_id: str, voice_id: str) -> dict:
        return run_generate_audio(project_id, voice_id)

    return generate_audio


def _register_retranscribe_and_align():
    from app.celery_app import celery_app

    @celery_app.task(name="scenecraft.retranscribe_and_align")
    def retranscribe_and_align(project_id: str) -> dict:
        return run_retranscribe_and_align(project_id)

    return retranscribe_and_align


generate_audio = _register_generate_audio()
retranscribe_and_align = _register_retranscribe_and_align()
