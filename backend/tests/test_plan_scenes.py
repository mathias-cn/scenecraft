from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.plan_scenes import (
    ScenePlanningError,
    close_scene_timeline,
    ffprobe_duration_ms,
    measure_project_audio_duration_ms,
    plan_project_scenes,
    project_audio_duration_ms,
    scenes_from_groups,
    validate_segment_partition,
)
from app.models.character import Character
from app.models.enums import CharacterStatus, MediaType, SceneStatus
from app.models.project import Project
from app.models.scene import Scene
from app.models.style import Style


class FakeDB:
    def __init__(self, project, rows=None):
        self.project = project
        self.rows = list(rows or [])
        self.added = []
        self.executed = []

    def get(self, model, pid):
        if model is Project:
            return self.project if self.project.id == pid else None
        for row in self.rows:
            if getattr(row, "_model", None) is model and row.id == pid:
                return row
        return None

    def execute(self, statement):
        self.executed.append(statement)
        return None

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        return None

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


def test_plan_project_scenes_enriches_visual_prompt_with_character(monkeypatch):
    style = SimpleNamespace(id=uuid4(), name="Anime", slug="anime", _model=Style)
    character = SimpleNamespace(
        id=uuid4(),
        description_prompt="heroína de casaco vermelho",
        style_id=style.id,
        status=CharacterStatus.APPROVED,
        base_image_url="https://cdn.example.com/base.png",
        _model=Character,
    )
    project = SimpleNamespace(
        id=uuid4(),
        target_language="pt-BR",
        automation_config={
            "character_id": str(character.id),
            "scene_style_id": str(style.id),
        },
        transcript_segments=[
            SimpleNamespace(
                index=0,
                start_ms=0,
                end_ms=1200,
                text_original="olá",
                text_translated=None,
            )
        ],
    )
    db = FakeDB(project, [style, character])

    def fake_plan_scenes(segments, **kwargs):
        assert kwargs["character_description"] == "heroína de casaco vermelho"
        assert kwargs["style_name"] == "Anime"
        assert kwargs["scene_pacing"] == "medium"
        assert segments[0]["text_original"] == "olá"
        return [
            {
                "start_ms": 9999,
                "end_ms": 9999,
                "source_segment_ids": [0],
                "visual_prompt": "Wide shot of a rainy street at night",
            }
        ]

    monkeypatch.setattr("app.core.plan_scenes.plan_scenes", fake_plan_scenes)
    monkeypatch.setattr("app.core.plan_scenes.measure_project_audio_duration_ms", lambda *_a, **_k: 1200)
    result = plan_project_scenes(project.id, db=db)
    assert result["scene_count"] == 1
    assert db.executed
    scene = db.added[0]
    assert isinstance(scene, Scene)
    assert scene.media_type is MediaType.IMAGE
    assert scene.status is SceneStatus.PENDING
    assert scene.start_ms == 0
    assert scene.end_ms == 1200
    assert scene.source_segment_ids == [0]
    assert "heroína de casaco vermelho" in scene.visual_prompt
    assert "Anime" in scene.visual_prompt
    assert scene.style is None


def test_validate_segment_partition_requires_exact_coverage():
    assert validate_segment_partition([[0, 1], [2]], 3) == [[0, 1], [2]]
    with pytest.raises(ScenePlanningError, match="exatamente uma cena"):
        validate_segment_partition([[0], [0]], 2)
    with pytest.raises(ScenePlanningError, match="exatamente uma cena"):
        validate_segment_partition([[0]], 2)
    with pytest.raises(ScenePlanningError, match="contíguos"):
        validate_segment_partition([[0, 2], [1]], 3)


def test_close_scene_timeline_fills_gaps_and_trailing_silence():
    scenes = [
        {"index": 0, "start_ms": 0, "end_ms": 2000, "source_segment_ids": [0]},
        {"index": 1, "start_ms": 2500, "end_ms": 4000, "source_segment_ids": [1]},
    ]
    closed = close_scene_timeline(scenes, audio_duration_ms=5000)
    assert closed[0]["end_ms"] == 2500
    assert closed[1]["start_ms"] == 2500
    assert closed[1]["end_ms"] == 5000


def test_close_scene_timeline_last_scene_ends_exactly_at_file_duration():
    scenes = [{"index": 0, "start_ms": 0, "end_ms": 4000, "source_segment_ids": [0]}]
    assert close_scene_timeline(scenes, audio_duration_ms=5123)[0]["end_ms"] == 5123
    scenes = [{"index": 0, "start_ms": 0, "end_ms": 4000, "source_segment_ids": [0]}]
    assert close_scene_timeline(scenes, audio_duration_ms=3500)[0]["end_ms"] == 3500


def test_scenes_from_groups_computes_times_from_segments():
    segments = [
        SimpleNamespace(index=0, start_ms=0, end_ms=1000),
        SimpleNamespace(index=1, start_ms=1000, end_ms=2000),
        SimpleNamespace(index=2, start_ms=2500, end_ms=4000),
    ]
    rows = scenes_from_groups(
        [
            {"source_segment_ids": [0, 1], "visual_prompt": "a"},
            {"source_segment_ids": [2], "visual_prompt": "b"},
        ],
        segments,
        audio_duration_ms=4800,
    )
    assert rows[0]["start_ms"] == 0
    assert rows[0]["end_ms"] == 2500
    assert rows[0]["source_segment_ids"] == [0, 1]
    assert rows[1]["start_ms"] == 2500
    assert rows[1]["end_ms"] == 4800
    assert rows[1]["source_segment_ids"] == [2]


def test_plan_project_scenes_closes_gaps_and_extends_last_scene(monkeypatch):
    project = SimpleNamespace(
        id=uuid4(),
        target_language="pt-BR",
        automation_config={"scene_pacing": "short"},
        transcript_segments=[
            SimpleNamespace(index=0, start_ms=0, end_ms=1000, text_original="a", text_translated=None),
            SimpleNamespace(index=1, start_ms=1000, end_ms=2000, text_original="b", text_translated=None),
            SimpleNamespace(index=2, start_ms=2500, end_ms=4000, text_original="c", text_translated=None),
        ],
    )
    db = FakeDB(project)

    def fake_plan_scenes(segments, **kwargs):
        assert kwargs["scene_pacing"] == "short"
        assert kwargs["min_duration_ms"] == 8000
        assert kwargs["max_duration_ms"] == 15000
        return [
            {"source_segment_ids": [0, 1], "visual_prompt": "first"},
            {"source_segment_ids": [2], "visual_prompt": "second"},
        ]

    monkeypatch.setattr("app.core.plan_scenes.plan_scenes", fake_plan_scenes)
    monkeypatch.setattr("app.core.plan_scenes.measure_project_audio_duration_ms", lambda *_a, **_k: 5000)
    result = plan_project_scenes(project.id, db=db)
    assert result["scene_count"] == 2
    first, second = db.added
    assert first.start_ms == 0
    assert first.end_ms == 2500
    assert first.source_segment_ids == [0, 1]
    assert first.status is SceneStatus.PENDING
    assert second.start_ms == 2500
    assert second.end_ms == 5000
    assert second.source_segment_ids == [2]


def test_ffprobe_duration_ms_parses_format_duration(monkeypatch, tmp_path):
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")

    def fake_run(cmd, **kwargs):
        assert cmd[:7] == [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
        ]
        assert cmd[7] == str(audio)
        return SimpleNamespace(
            returncode=0,
            stdout='{"format":{"duration":"12.3456"}}',
            stderr="",
        )

    monkeypatch.setattr("app.core.plan_scenes.subprocess.run", fake_run)
    assert ffprobe_duration_ms(audio) == 12346


def test_ffprobe_duration_ms_raises_on_failure(monkeypatch, tmp_path):
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    monkeypatch.setattr(
        "app.core.plan_scenes.subprocess.run",
        lambda *_a, **_k: SimpleNamespace(returncode=1, stdout="", stderr="no such file"),
    )
    with pytest.raises(ScenePlanningError, match="ffprobe falhou"):
        ffprobe_duration_ms(audio)


def test_project_audio_duration_uses_ffprobe_not_last_segment(monkeypatch):
    project = SimpleNamespace(id=uuid4(), audio_tracks=[])
    segments = [SimpleNamespace(end_ms=4000)]
    monkeypatch.setattr("app.core.plan_scenes.measure_project_audio_duration_ms", lambda *_a, **_k: 5123)
    assert project_audio_duration_ms(project, segments) == 5123


def test_project_audio_duration_raises_when_source_unavailable(monkeypatch):
    from app.core.source_downloader import SourceDownloadError

    project = SimpleNamespace(id=uuid4(), audio_tracks=[], source_ref="")
    monkeypatch.setattr(
        "app.core.source_downloader.load_audio",
        lambda *_a, **_k: (_ for _ in ()).throw(SourceDownloadError("ainda sem arquivo")),
    )
    with pytest.raises(ScenePlanningError, match="áudio real ainda não disponível"):
        project_audio_duration_ms(project, [SimpleNamespace(end_ms=4000)])


def test_project_audio_duration_probes_source_when_no_track(monkeypatch, tmp_path):
    audio = tmp_path / "source.mp3"
    audio.write_bytes(b"x")
    project = SimpleNamespace(id=uuid4(), audio_tracks=[])
    persisted = []

    monkeypatch.setattr("app.core.source_downloader.load_audio", lambda *_a, **_k: audio)
    monkeypatch.setattr(
        "app.core.project_audio.persist_original_audio",
        lambda db, proj, path: persisted.append((db, proj, path)) or SimpleNamespace(file_url="s3://b/o.mp3"),
    )
    monkeypatch.setattr("app.core.plan_scenes.ffprobe_duration_ms", lambda path: 7777 if path == audio else 0)
    assert project_audio_duration_ms(project, [SimpleNamespace(end_ms=4000)], db=object()) == 7777
    assert persisted


def test_measure_project_audio_duration_downloads_and_probes(monkeypatch):
    project = SimpleNamespace(
        id=uuid4(),
        audio_tracks=[SimpleNamespace(source="original", file_url="s3://bucket/clip.mp3")],
    )

    def fake_download(url, local_path):
        assert url == "s3://bucket/clip.mp3"
        destination = Path(local_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"x")
        return destination

    monkeypatch.setattr("app.core.plan_scenes._download_audio", fake_download)
    monkeypatch.setattr("app.core.plan_scenes.ffprobe_duration_ms", lambda _path: 5123)
    assert measure_project_audio_duration_ms(project) == 5123


def test_celery_task_is_registered_with_project_id_signature():
    celery = pytest.importorskip("celery")
    _ = celery
    from app.tasks.scene_planning import plan_scenes

    assert plan_scenes.name == "scenecraft.plan_scenes"
