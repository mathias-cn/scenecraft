from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.state_machine import (
    IllegalTransition,
    ProjectNotFound,
    advance_stage,
    auto_flag_enabled,
    is_valid_transition,
    linear_next,
    parse_stage,
    retry_stage,
    stage_to_retry,
)
from app.models.enums import JobStatus, ProjectStage, ProjectStatus, SourceType


def test_parse_stage_accepts_enum_and_names():
    assert parse_stage(ProjectStage.CREATED) is ProjectStage.CREATED
    assert parse_stage("created") is ProjectStage.CREATED
    assert parse_stage("TRANSCRIBING") is ProjectStage.TRANSCRIBING
    assert parse_stage("transcript_review") is ProjectStage.TRANSCRIPT_REVIEW


def test_linear_next_follows_declared_order():
    assert linear_next(ProjectStage.CREATED) is ProjectStage.TRANSCRIBING
    assert linear_next(ProjectStage.TRANSCRIBING) is ProjectStage.TRANSCRIPT_REVIEW
    assert linear_next(ProjectStage.TRANSCRIPT_REVIEW) is ProjectStage.SCENE_PLANNING
    assert linear_next(ProjectStage.READY_TO_PUBLISH) is ProjectStage.UPLOADING
    assert linear_next(ProjectStage.UPLOADING) is ProjectStage.PUBLISHED
    assert linear_next(ProjectStage.PUBLISHED) is None
    assert linear_next(ProjectStage.FAILED) is None


@pytest.mark.parametrize(
    ("src", "dst", "valid"),
    [
        (ProjectStage.CREATED, ProjectStage.TRANSCRIBING, True),
        (ProjectStage.TRANSCRIBING, ProjectStage.TRANSCRIPT_REVIEW, True),
        (ProjectStage.SCENE_PLANNING, ProjectStage.SCENE_REVIEW, True),
        (ProjectStage.GENERATING_MEDIA, ProjectStage.MEDIA_REVIEW, True),
        (ProjectStage.AUDIO_STAGE, ProjectStage.AUDIO_REVIEW, True),
        (ProjectStage.RENDERING, ProjectStage.RENDER_REVIEW, True),
        (ProjectStage.UPLOADING, ProjectStage.PUBLISHED, True),
        (ProjectStage.CREATED, ProjectStage.SCENE_PLANNING, False),
        (ProjectStage.TRANSCRIBING, ProjectStage.CREATED, False),
        (ProjectStage.PUBLISHED, ProjectStage.UPLOADING, False),
        (ProjectStage.FAILED, ProjectStage.CREATED, False),
        (ProjectStage.CREATED, ProjectStage.FAILED, True),
        (ProjectStage.PUBLISHED, ProjectStage.FAILED, False),
        (ProjectStage.FAILED, ProjectStage.FAILED, False),
    ],
)
def test_is_valid_transition(src: ProjectStage, dst: ProjectStage, valid: bool):
    assert is_valid_transition(src, dst) is valid


def test_auto_flag_for_review_stages():
    assert auto_flag_enabled({"auto_transcribe": True}, ProjectStage.TRANSCRIPT_REVIEW)
    assert auto_flag_enabled({"auto_transcribe": "true"}, ProjectStage.TRANSCRIPT_REVIEW)
    assert not auto_flag_enabled({}, ProjectStage.TRANSCRIPT_REVIEW)
    assert not auto_flag_enabled({"auto_transcribe": True}, ProjectStage.SCENE_REVIEW)
    assert auto_flag_enabled({"auto_publish": True}, ProjectStage.READY_TO_PUBLISH)
    assert auto_flag_enabled({"auto_media_gen": True}, ProjectStage.MEDIA_REVIEW)
    assert auto_flag_enabled({"auto_description": True}, ProjectStage.READY_TO_PUBLISH)
    assert not auto_flag_enabled({"auto_media_gen": False}, ProjectStage.MEDIA_REVIEW)


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
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


def test_advance_stage_project_not_found():
    db = FakeDB(None)
    with pytest.raises(ProjectNotFound):
        advance_stage(uuid4(), ProjectStage.CREATED, db=db)


def test_advance_rejects_stage_mismatch(monkeypatch):
    monkeypatch.setattr("app.core.state_machine.enqueue_job", lambda *a, **k: None)
    project = _project(current_stage=ProjectStage.TRANSCRIBING)
    db = FakeDB(project)
    with pytest.raises(IllegalTransition, match="esperado created"):
        advance_stage(project.id, ProjectStage.CREATED, db=db)
    assert db.rollbacks == 1


def test_advance_from_published_is_invalid(monkeypatch):
    monkeypatch.setattr("app.core.state_machine.enqueue_job", lambda *a, **k: None)
    project = _project(current_stage=ProjectStage.PUBLISHED, status=ProjectStatus.COMPLETED)
    db = FakeDB(project)
    with pytest.raises(IllegalTransition, match="não há estágio seguinte"):
        advance_stage(project.id, ProjectStage.PUBLISHED, db=db)


def test_advance_from_failed_is_invalid(monkeypatch):
    monkeypatch.setattr("app.core.state_machine.enqueue_job", lambda *a, **k: None)
    project = _project(current_stage=ProjectStage.FAILED, status=ProjectStatus.FAILED)
    db = FakeDB(project)
    with pytest.raises(IllegalTransition):
        advance_stage(project.id, ProjectStage.FAILED, db=db)


def test_created_advances_to_transcribing_and_dispatches_job(monkeypatch):
    enqueued = []
    monkeypatch.setattr(
        "app.core.state_machine.enqueue_job",
        lambda step, job_id: enqueued.append((step.queue.value, job_id)),
    )
    project = _project()
    db = FakeDB(project)
    result = advance_stage(project.id, "CREATED", db=db)
    assert result.to_stage is ProjectStage.TRANSCRIBING
    assert result.paused_for_review is False
    assert project.status is ProjectStatus.RUNNING
    assert result.dispatched_job_id is not None
    assert enqueued[0][0] == "transcribe"
    assert db.commits == 1
    job = db.added[0]
    assert job.status is JobStatus.QUEUED
    assert job.job_group_id is not None
    assert job.attempt_count == 0


def test_transcribing_pauses_on_review_without_auto_flag(monkeypatch):
    monkeypatch.setattr("app.core.state_machine.enqueue_job", lambda *a, **k: None)
    project = _project(current_stage=ProjectStage.TRANSCRIBING, automation_config={})
    db = FakeDB(project)
    result = advance_stage(project.id, ProjectStage.TRANSCRIBING, db=db)
    assert result.to_stage is ProjectStage.TRANSCRIPT_REVIEW
    assert result.paused_for_review is True
    assert project.status is ProjectStatus.PAUSED_FOR_REVIEW
    assert result.dispatched_job_id is None
    assert db.added == []


def test_auto_transcribe_skips_review_and_starts_scene_planning(monkeypatch):
    enqueued = []
    monkeypatch.setattr(
        "app.core.state_machine.enqueue_job",
        lambda step, job_id: enqueued.append(step.queue.value),
    )
    project = _project(
        current_stage=ProjectStage.TRANSCRIBING,
        automation_config={"auto_transcribe": True},
    )
    db = FakeDB(project)
    result = advance_stage(project.id, ProjectStage.TRANSCRIBING, db=db)
    assert result.auto_advanced is True
    assert result.to_stage is ProjectStage.SCENE_PLANNING
    assert result.paused_for_review is False
    assert project.current_stage is ProjectStage.SCENE_PLANNING
    assert project.status is ProjectStatus.RUNNING
    assert enqueued == ["scene_planning"]


def test_manual_review_resume_dispatches_next_work(monkeypatch):
    enqueued = []
    monkeypatch.setattr(
        "app.core.state_machine.enqueue_job",
        lambda step, job_id: enqueued.append(step.queue.value),
    )
    project = _project(
        current_stage=ProjectStage.TRANSCRIPT_REVIEW,
        status=ProjectStatus.PAUSED_FOR_REVIEW,
    )
    db = FakeDB(project)
    result = advance_stage(project.id, ProjectStage.TRANSCRIPT_REVIEW, db=db)
    assert result.to_stage is ProjectStage.SCENE_PLANNING
    assert enqueued == ["scene_planning"]


def test_uploading_advances_to_published(monkeypatch):
    monkeypatch.setattr("app.core.state_machine.enqueue_job", lambda *a, **k: None)
    project = _project(current_stage=ProjectStage.UPLOADING, status=ProjectStatus.RUNNING)
    db = FakeDB(project)
    result = advance_stage(project.id, ProjectStage.UPLOADING, db=db)
    assert result.to_stage is ProjectStage.PUBLISHED
    assert project.status is ProjectStatus.COMPLETED
    assert result.dispatched_job_id is None
    assert db.added == []


def test_ready_to_publish_pauses_without_auto_publish(monkeypatch):
    monkeypatch.setattr("app.core.state_machine.enqueue_job", lambda *a, **k: None)
    project = _project(current_stage=ProjectStage.DESCRIPTION_STAGE)
    db = FakeDB(project)
    result = advance_stage(project.id, ProjectStage.DESCRIPTION_STAGE, db=db)
    assert result.to_stage is ProjectStage.READY_TO_PUBLISH
    assert result.paused_for_review is True
    assert project.status is ProjectStatus.PAUSED_FOR_REVIEW


def test_auto_publish_starts_upload(monkeypatch):
    enqueued = []
    monkeypatch.setattr(
        "app.core.state_machine.enqueue_job",
        lambda step, job_id: enqueued.append(step.queue.value),
    )
    project = _project(
        current_stage=ProjectStage.DESCRIPTION_STAGE,
        automation_config={"auto_publish": True},
    )
    db = FakeDB(project)
    result = advance_stage(project.id, ProjectStage.DESCRIPTION_STAGE, db=db)
    assert result.to_stage is ProjectStage.UPLOADING
    assert result.auto_advanced is True
    assert enqueued == ["upload"]


def test_stage_to_retry_keeps_work_stage():
    project = _project(current_stage=ProjectStage.GENERATING_MEDIA, status=ProjectStatus.FAILED)
    assert stage_to_retry(project, []) is ProjectStage.GENERATING_MEDIA


def test_stage_to_retry_reads_last_job_when_stage_is_failed():
    job = SimpleNamespace(stage=ProjectStage.AUDIO_STAGE)
    project = _project(current_stage=ProjectStage.FAILED, status=ProjectStatus.FAILED)
    assert stage_to_retry(project, [job]) is ProjectStage.AUDIO_STAGE


def test_retry_stage_rejects_when_not_failed(monkeypatch):
    monkeypatch.setattr("app.core.state_machine.enqueue_job", lambda *a, **k: None)
    project = _project(current_stage=ProjectStage.TRANSCRIBING, status=ProjectStatus.RUNNING)
    db = FakeDB(project)
    with pytest.raises(IllegalTransition, match="após falha"):
        retry_stage(project.id, db=db)


def test_retry_stage_redispatches_current_work_stage(monkeypatch):
    enqueued = []
    monkeypatch.setattr(
        "app.core.state_machine.enqueue_job",
        lambda step, job_id: enqueued.append(step.queue.value),
    )
    project = _project(current_stage=ProjectStage.GENERATING_MEDIA, status=ProjectStatus.FAILED)
    previous = SimpleNamespace(
        stage=ProjectStage.GENERATING_MEDIA,
        job_group_id=uuid4(),
        payload={"scene": 1},
    )
    db = FakeDB(project, jobs=[previous])
    result = retry_stage(project.id, db=db)
    assert result.to_stage is ProjectStage.GENERATING_MEDIA
    assert project.status is ProjectStatus.RUNNING
    assert enqueued == ["media_gen"]
    assert result.dispatched_job_id is not None
    assert db.added[0].payload == {"scene": 1}


def test_render_review_pauses_on_thumbnail_stage(monkeypatch):
    monkeypatch.setattr("app.core.state_machine.enqueue_job", lambda *a, **k: None)
    project = _project(
        current_stage=ProjectStage.RENDER_REVIEW,
        status=ProjectStatus.PAUSED_FOR_REVIEW,
    )
    db = FakeDB(project)
    result = advance_stage(project.id, ProjectStage.RENDER_REVIEW, db=db)
    assert result.to_stage is ProjectStage.THUMBNAIL_STAGE
    assert result.paused_for_review is True
    assert project.status is ProjectStatus.PAUSED_FOR_REVIEW
    assert result.dispatched_job_id is None
    assert db.added == []


def test_auto_thumbnail_dispatches_thumbnail_job(monkeypatch):
    enqueued = []
    monkeypatch.setattr(
        "app.core.state_machine.enqueue_job",
        lambda step, job_id: enqueued.append(step.queue.value),
    )
    project = _project(
        current_stage=ProjectStage.RENDER_REVIEW,
        automation_config={"auto_thumbnail": True},
    )
    db = FakeDB(project)
    result = advance_stage(project.id, ProjectStage.RENDER_REVIEW, db=db)
    assert result.to_stage is ProjectStage.THUMBNAIL_STAGE
    assert result.paused_for_review is False
    assert result.auto_advanced is True
    assert project.status is ProjectStatus.RUNNING
    assert enqueued == ["thumbnail"]


def test_cannot_leave_thumbnail_stage_without_file(monkeypatch):
    monkeypatch.setattr("app.core.state_machine.enqueue_job", lambda *a, **k: None)
    project = _project(
        current_stage=ProjectStage.THUMBNAIL_STAGE,
        status=ProjectStatus.PAUSED_FOR_REVIEW,
        thumbnails=[],
    )
    db = FakeDB(project)
    with pytest.raises(IllegalTransition, match="thumbnail"):
        advance_stage(project.id, ProjectStage.THUMBNAIL_STAGE, db=db)
    assert project.current_stage is ProjectStage.THUMBNAIL_STAGE
