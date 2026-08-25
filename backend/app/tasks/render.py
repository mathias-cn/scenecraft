from app.core.render_video import render_video as run_render_video
from app.tasks.base import pipeline_task


@pipeline_task(name="scenecraft.render", provider=None)
def render(_self, db, job, project) -> dict:
    result = run_render_video(project.id, db=db)
    result["title"] = project.title
    result["job_id"] = str(job.id)
    return result


def _register_render_video():
    from app.celery_app import celery_app

    @celery_app.task(name="scenecraft.render_video")
    def render_video(project_id: str) -> dict:
        return run_render_video(project_id)

    return render_video


render_video = _register_render_video()
