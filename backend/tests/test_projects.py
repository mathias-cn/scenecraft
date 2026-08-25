import pytest
from pydantic import ValidationError

from app.core.ingest import (
    IngestError,
    assert_upload_filename,
    parse_automation_config,
    resolve_source_ref,
    sanitize_filename,
)
from app.models.enums import SourceType
from app.schemas.project import ProjectCreate, ProjectDetail, ProjectRead


def test_youtube_requires_source_ref():
    with pytest.raises(ValidationError):
        ProjectCreate(title="x", source_type=SourceType.YOUTUBE_LINK)


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
