from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.db import SessionLocal
from app.models.job import Job, JobStatus
from app.providers import anthropic, elevenlabs, higgsfield, storage, youtube


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _update(db: Session, job: Job, **fields) -> None:
    for key, value in fields.items():
        setattr(job, key, value)
    job.updated_at = _now()
    db.commit()
    db.refresh(job)


@celery_app.task(name="scenecraft.run_pipeline")
def run_pipeline(job_id: str) -> dict:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return {"ok": False, "error": "job_not_found"}

        _update(db, job, status=JobStatus.SCRIPTING)
        script = anthropic.generate_script(title=job.title, prompt=job.prompt)
        _update(db, job, script=script, status=JobStatus.VOICING)

        voice_url = elevenlabs.synthesize(script=script, job_id=job.id)
        _update(db, job, voice_url=voice_url, status=JobStatus.VOICING)

        _update(db, job, status=JobStatus.GENERATING)
        video_source = higgsfield.generate_video(script=script, job_id=job.id)
        video_url = storage.upload_media(job_id=job.id, source=video_source)
        _update(db, job, video_url=video_url, status=JobStatus.UPLOADING)

        youtube_url = youtube.upload_video(
            title=job.title,
            description=script,
            video_url=video_url,
        )
        _update(db, job, youtube_url=youtube_url, status=JobStatus.COMPLETED)
        return {"ok": True, "job_id": job.id, "youtube_url": youtube_url}
    except Exception as exc:  # noqa: BLE001 — jobs must never leave the worker hanging
        job = db.get(Job, job_id)
        if job is not None:
            _update(db, job, status=JobStatus.FAILED, error=str(exc))
        return {"ok": False, "error": str(exc)}
    finally:
        db.close()
