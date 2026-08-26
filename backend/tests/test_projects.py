from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.ingest import (
    IngestError,
    assert_upload_filename,
    parse_automation_config,
    resolve_source_ref,
    sanitize_filename,
    assert_image_upload_filename,
    sanitize_image_filename,
)
from app.models.enums import ProjectStage, ProjectStatus, SourceType
from app.schemas.project import AdvanceRead, ProjectCreate, ProjectDetail, ProjectRead


def test_youtube_requires_source_ref():
    with pytest.raises(ValidationError):
        ProjectCreate(title="x", source_type=SourceType.YOUTUBE_LINK)


def test_text_script_requires_source_ref():
    with pytest.raises(ValidationError, match="source_ref"):
        ProjectCreate(title="x", source_type=SourceType.TEXT_SCRIPT)


def test_upload_json_may_omit_file_when_source_ref_present():
    payload = ProjectCreate(
        title="clip",
        source_type=SourceType.UPLOAD_VIDEO,
        source_ref="s3://bucket/a.mp4",
        target_language="pt-BR",
        automation_config={"auto_media": True},
    )
    ref = resolve_source_ref(
        source_type=payload.source_type,
        source_ref=payload.source_ref,
        has_file=False,
    )
    assert ref == "s3://bucket/a.mp4"


def test_upload_requires_file_or_ref():
    with pytest.raises(IngestError, match="arquivo"):
        resolve_source_ref(
            source_type=SourceType.UPLOAD_AUDIO,
            source_ref=None,
            has_file=False,
        )


def test_youtube_rejects_file():
    with pytest.raises(IngestError, match="não aceita arquivo"):
        resolve_source_ref(
            source_type=SourceType.YOUTUBE_LINK,
            source_ref="https://youtu.be/x",
            has_file=True,
        )


def test_text_script_rejects_file_and_requires_ref():
    with pytest.raises(IngestError, match="não aceita arquivo"):
        resolve_source_ref(
            source_type=SourceType.TEXT_SCRIPT,
            source_ref="Olá. Isto é um roteiro.",
            has_file=True,
        )
    with pytest.raises(IngestError, match="obrigatório"):
        resolve_source_ref(source_type=SourceType.TEXT_SCRIPT, source_ref=None, has_file=False)
    ref = resolve_source_ref(
        source_type=SourceType.TEXT_SCRIPT,
        source_ref="  Primeira frase. Segunda frase.  ",
        has_file=False,
    )
    assert ref == "Primeira frase. Segunda frase."


def test_parse_automation_config_json_object():
    assert parse_automation_config('{"auto_transcribe": true}') == {"auto_transcribe": True}
    assert parse_automation_config(None) == {}
    with pytest.raises(IngestError):
        parse_automation_config("[1]")
    with pytest.raises(IngestError):
        parse_automation_config("{")


def test_filename_rules():
    assert sanitize_filename("clip.MP4", SourceType.UPLOAD_VIDEO) == "clip.MP4"
    assert_upload_filename("a.mp4", SourceType.UPLOAD_VIDEO)
    assert_upload_filename("voice.wav", SourceType.UPLOAD_AUDIO)
    with pytest.raises(IngestError):
        assert_upload_filename("notes.txt", SourceType.UPLOAD_VIDEO)
    assert sanitize_image_filename("cover.PNG") == "cover.PNG"
    assert_image_upload_filename("thumb.webp")
    with pytest.raises(IngestError, match="imagem"):
        assert_image_upload_filename("notes.txt")


def test_project_detail_sorts_scenes():
    from datetime import datetime, timezone
    from uuid import uuid4

    from app.models.enums import MediaType, ProjectStage, ProjectStatus, SceneStatus

    pid = uuid4()
    now = datetime.now(timezone.utc)
    detail = ProjectDetail(
        id=pid,
        title="t",
        source_type=SourceType.YOUTUBE_LINK,
        source_ref="https://youtu.be/x",
        target_language="pt-BR",
        automation_config={},
        current_stage=ProjectStage.SCENE_REVIEW,
        status=ProjectStatus.PAUSED_FOR_REVIEW,
        created_at=now,
        updated_at=now,
        scenes=[
            {
                "id": uuid4(),
                "project_id": pid,
                "index": 2,
                "start_ms": 1000,
                "end_ms": 2000,
                "source_segment_ids": [],
                "visual_prompt": "b",
                "media_type": MediaType.IMAGE,
                "status": SceneStatus.PENDING,
            },
            {
                "id": uuid4(),
                "project_id": pid,
                "index": 1,
                "start_ms": 0,
                "end_ms": 1000,
                "source_segment_ids": [0],
                "visual_prompt": "a",
                "media_type": MediaType.VIDEO,
                "status": SceneStatus.COMPLETED,
            },
        ],
        audio_tracks=[],
        video_assembly=None,
    )
    assert [scene.index for scene in detail.scenes] == [1, 2]
    assert isinstance(detail, ProjectRead)


def test_project_create_accepts_optional_character_and_style_ids():
    from uuid import uuid4

    cid = uuid4()
    sid = uuid4()
    payload = ProjectCreate(
        title="clip",
        source_type=SourceType.YOUTUBE_LINK,
        source_ref="https://youtu.be/x",
        character_id=cid,
        scene_style_id=sid,
    )
    assert payload.character_id == cid
    assert payload.scene_style_id == sid


def test_project_create_defaults_scene_pacing_to_medium():
    payload = ProjectCreate(
        title="clip",
        source_type=SourceType.YOUTUBE_LINK,
        source_ref="https://youtu.be/x",
    )
    assert payload.automation_config["scene_pacing"] == "medium"


def test_project_create_accepts_scene_pacing():
    payload = ProjectCreate(
        title="clip",
        source_type=SourceType.YOUTUBE_LINK,
        source_ref="https://youtu.be/x",
        automation_config={"scene_pacing": "long"},
    )
    assert payload.automation_config["scene_pacing"] == "long"


def test_project_create_rejects_invalid_scene_pacing():
    with pytest.raises(ValidationError):
        ProjectCreate(
            title="clip",
            source_type=SourceType.YOUTUBE_LINK,
            source_ref="https://youtu.be/x",
            automation_config={"scene_pacing": "instant"},
        )


def test_project_create_accepts_audio_automation_fields():
    payload = ProjectCreate(
        title="clip",
        source_type=SourceType.UPLOAD_AUDIO,
        source_ref="s3://bucket/a.mp3",
        automation_config={
            "reuse_original_audio": True,
            "audio_generation_mode": "user_upload",
        },
    )
    assert payload.automation_config["reuse_original_audio"] is True
    assert payload.automation_config["audio_generation_mode"] == "elevenlabs"


def test_project_create_rejects_reuse_original_audio_for_youtube():
    with pytest.raises(ValidationError, match="reuse_original_audio"):
        ProjectCreate(
            title="clip",
            source_type=SourceType.YOUTUBE_LINK,
            source_ref="https://youtu.be/x",
            automation_config={"reuse_original_audio": True, "audio_generation_mode": "user_upload"},
        )


def test_project_create_rejects_reuse_original_audio_for_text_script():
    with pytest.raises(ValidationError, match="reuse_original_audio"):
        ProjectCreate(
            title="clip",
            source_type=SourceType.TEXT_SCRIPT,
            source_ref="Olá mundo. Este é o roteiro.",
            automation_config={"reuse_original_audio": True, "audio_generation_mode": "elevenlabs"},
        )


def test_project_create_accepts_text_script_with_elevenlabs():
    payload = ProjectCreate(
        title="clip",
        source_type=SourceType.TEXT_SCRIPT,
        source_ref="Olá mundo. Este é o roteiro completo da narração.",
        automation_config={"audio_generation_mode": "user_upload"},
    )
    assert payload.source_type is SourceType.TEXT_SCRIPT
    assert payload.automation_config["reuse_original_audio"] is False
    assert payload.automation_config["audio_generation_mode"] == "user_upload"


def test_project_create_forces_reuse_false_for_upload_video():
    payload = ProjectCreate(
        title="clip",
        source_type=SourceType.UPLOAD_VIDEO,
        source_ref="s3://bucket/a.mp4",
        automation_config={"reuse_original_audio": True, "audio_generation_mode": "user_upload"},
    )
    assert payload.automation_config["reuse_original_audio"] is False
    assert payload.automation_config["audio_generation_mode"] == "user_upload"


def test_project_create_blank_cast_ids_become_none():
    payload = ProjectCreate(
        title="clip",
        source_type=SourceType.YOUTUBE_LINK,
        source_ref="https://youtu.be/x",
        character_id="",
        scene_style_id="",
    )
    assert payload.character_id is None
    assert payload.scene_style_id is None


def _advance_result(**overrides):
    from app.core.state_machine import AdvanceResult

    payload = dict(
        project_id=uuid4(),
        from_stage=ProjectStage.GENERATING_MEDIA,
        to_stage=ProjectStage.GENERATING_MEDIA,
        status=ProjectStatus.RUNNING,
        paused_for_review=False,
        dispatched_job_id=uuid4(),
        auto_advanced=False,
        paused_for_cost_limit=False,
    )
    payload.update(overrides)
    return AdvanceResult(**payload)


def test_advance_read_accepts_advance_result_dataclass():
    result = _advance_result()
    payload = AdvanceRead.model_validate(result)
    assert payload.project_id == result.project_id
    assert payload.to_stage is ProjectStage.GENERATING_MEDIA
    assert payload.status is ProjectStatus.RUNNING
    assert payload.dispatched_job_id == result.dispatched_job_id
    assert payload.paused_for_review is False


def test_retry_stage_endpoint_returns_200_for_failed_project(monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.auth import CurrentUser, get_current_user
    from app.db import get_db
    from app.main import app

    result = _advance_result()
    monkeypatch.setattr("app.api.projects.retry_stage", lambda *_a, **_k: result)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        email="owner@example.com",
        subject="owner",
    )
    app.dependency_overrides[get_db] = lambda: None
    try:
        with TestClient(app) as client:
            response = client.post(f"/api/projects/{result.project_id}/retry-stage")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == str(result.project_id)
    assert body["from_stage"] == ProjectStage.GENERATING_MEDIA.value
    assert body["to_stage"] == ProjectStage.GENERATING_MEDIA.value
    assert body["status"] == ProjectStatus.RUNNING.value
    assert body["paused_for_review"] is False
    assert body["dispatched_job_id"] == str(result.dispatched_job_id)
    assert body["auto_advanced"] is False
    assert body["paused_for_cost_limit"] is False


def test_advance_endpoint_returns_200_from_advance_result(monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.auth import CurrentUser, get_current_user
    from app.db import get_db
    from app.main import app

    result = _advance_result(
        from_stage=ProjectStage.TRANSCRIPT_REVIEW,
        to_stage=ProjectStage.SCENE_PLANNING,
        status=ProjectStatus.RUNNING,
    )
    monkeypatch.setattr("app.api.projects.advance_stage", lambda *_a, **_k: result)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        email="owner@example.com",
        subject="owner",
    )
    app.dependency_overrides[get_db] = lambda: None
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/projects/{result.project_id}/advance",
                json={"from_stage": ProjectStage.TRANSCRIPT_REVIEW.value},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["to_stage"] == ProjectStage.SCENE_PLANNING.value
    assert body["status"] == ProjectStatus.RUNNING.value


def test_generate_script_endpoint_returns_text(monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.auth import CurrentUser, get_current_user
    from app.db import get_db
    from app.main import app
    from app.providers.pricing import PricedText

    monkeypatch.setattr("app.api.ai.assert_paid_job_allowed", lambda _db: None)
    monkeypatch.setattr(
        "app.api.ai.generate_script",
        lambda topic, target_duration_minutes=None: PricedText(f"Roteiro sobre {topic}.", "0.01"),
    )
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        email="owner@example.com",
        subject="owner",
    )
    app.dependency_overrides[get_db] = lambda: None
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/ai/generate-script",
                json={"topic": "fotossíntese", "target_duration_minutes": 3},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert "fotossíntese" in body["script"]
    assert body["cost_usd"] == 0.01
