from types import SimpleNamespace
from uuid import uuid4

from app.core.project_audio import should_skip_audio_stage
from app.core.state_machine import advance_stage
from app.models.enums import AudioTrackSource, ProjectStage, ProjectStatus, SourceType


class FakeDB:
    def __init__(self, project, jobs=None):
        self.project = project
        self.jobs = list(jobs or [])
        self.added: list = []
        self.commits = 0
        self.rollbacks = 0

    def get(self, _model, _pid):
        return self.project

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        return None

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def scalars(self, _stmt):
        return SimpleNamespace(all=lambda: list(self.jobs), first=lambda: self.jobs[0] if self.jobs else None)


def _project(**kwargs):
    data = dict(
        id=uuid4(),
        current_stage=ProjectStage.CREATED,
        status=ProjectStatus.PENDING,
        automation_config={},
        source_ref="https://youtube.com/watch?v=abc",
        source_type=SourceType.YOUTUBE_LINK,
        audio_tracks=[],
        video_assemblies=[],
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


def test_should_skip_only_for_upload_audio_flag():
    project = _project(
        source_type=SourceType.UPLOAD_AUDIO,
        automation_config={"reuse_original_audio": True},
    )
    assert should_skip_audio_stage(project) is True
    youtube = _project(automation_config={"reuse_original_audio": True})
    assert should_skip_audio_stage(youtube) is False
    script = _project(
        source_type=SourceType.TEXT_SCRIPT,
        source_ref="Olá mundo.",
        automation_config={"reuse_original_audio": True},
    )
    assert should_skip_audio_stage(script) is False
    upload_off = _project(source_type=SourceType.UPLOAD_AUDIO, automation_config={})
    assert should_skip_audio_stage(upload_off) is False


def test_transcript_review_pauses_on_audio_stage_for_input(monkeypatch):
    monkeypatch.setattr("app.core.state_machine.enqueue_job", lambda *a, **k: None)
    project = _project(
        current_stage=ProjectStage.TRANSCRIPT_REVIEW,
        status=ProjectStatus.PAUSED_FOR_REVIEW,
        automation_config={"audio_generation_mode": "elevenlabs"},
    )
    db = FakeDB(project)
    result = advance_stage(project.id, ProjectStage.TRANSCRIPT_REVIEW, db=db)
    assert result.to_stage is ProjectStage.AUDIO_STAGE
    assert result.paused_for_review is True
    assert project.status is ProjectStatus.PAUSED_FOR_REVIEW
    assert result.dispatched_job_id is None
    assert db.added == []


def test_reuse_original_audio_skips_to_scene_planning(monkeypatch):
    enqueued = []
    monkeypatch.setattr(
        "app.core.state_machine.enqueue_job",
        lambda step, job_id: enqueued.append(step.queue.value),
    )
    track = SimpleNamespace(
        source=AudioTrackSource.ORIGINAL,
        file_url="https://cdn.example.com/original.mp3",
    )
    project = _project(
        current_stage=ProjectStage.TRANSCRIPT_REVIEW,
        source_type=SourceType.UPLOAD_AUDIO,
        source_ref="s3://bucket/voice.mp3",
        automation_config={"reuse_original_audio": True},
        audio_tracks=[track],
        video_assemblies=[],
    )
    db = FakeDB(project)
    result = advance_stage(project.id, ProjectStage.TRANSCRIPT_REVIEW, db=db)
    assert result.to_stage is ProjectStage.SCENE_PLANNING
    assert result.paused_for_review is False
    assert result.auto_advanced is True
    assert project.current_stage is ProjectStage.SCENE_PLANNING
    assert project.status is ProjectStatus.RUNNING
    assert enqueued == ["scene_planning"]
    assembly = next(item for item in db.added if getattr(item, "render_config", None))
    assert assembly.render_config["audio_url"] == "https://cdn.example.com/original.mp3"
    assert assembly.render_config["audio_source"] == "original"
