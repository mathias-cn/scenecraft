from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.export_project import export_project
from app.core.state_machine import ProjectNotFound
from app.models.project import Project
from app.schemas.character import CharacterRead
from app.schemas.project import ProjectExportRead, SceneRead
from app.storage import StorageError, download_url, generate_presigned_url, object_key_from_stored


class FakeDB:
    def __init__(self, project):
        self.project = project

    def get(self, model, pid):
        if model is Project and self.project.id == pid:
            return self.project
        return None

    def close(self):
        return None


def _project(**kwargs):
    pid = kwargs.pop("id", uuid4())
    data = dict(
        id=pid,
        title="O Mar",
        video_assembly=SimpleNamespace(output_url="pid/render.mp4"),
        thumbnails=[SimpleNamespace(file_url="pid/thumbnail.png")],
        descriptions=[
            SimpleNamespace(text="Resumo antigo", tags=["velha"]),
            SimpleNamespace(text="Parágrafo final.", tags=["mar", "oceano"]),
        ],
    )
    data.update(kwargs)
    data["id"] = pid
    return SimpleNamespace(**data)


def test_export_project_returns_object_keys():
    project = _project()
    payload = export_project(project.id, db=FakeDB(project))
    assert payload["title"] == "O Mar"
    assert payload["video_assembly"]["output_url"] == "pid/render.mp4"
    assert payload["thumbnails"]["file_url"] == "pid/thumbnail.png"
    assert payload["descriptions"]["text"] == "Parágrafo final."
    assert payload["descriptions"]["tags"] == ["mar", "oceano"]


def test_export_project_allows_missing_assets():
    project = _project(video_assembly=None, thumbnails=[], descriptions=[])
    payload = export_project(project.id, db=FakeDB(project))
    assert payload["video_assembly"]["output_url"] is None
    assert payload["thumbnails"]["file_url"] is None
    assert payload["descriptions"] == {"text": "", "tags": []}


def test_export_project_not_found():
    with pytest.raises(ProjectNotFound):
        export_project(uuid4(), db=FakeDB(_project()))


def test_export_schema_signs_object_keys(monkeypatch):
    monkeypatch.setattr(
        "app.storage.generate_presigned_url",
        lambda key, expires_in=3600: f"https://signed.example/{key}?exp={expires_in}",
    )
    payload = ProjectExportRead.model_validate(
        {
            "title": "O Mar",
            "video_assembly": {"output_url": "pid/render.mp4"},
            "thumbnails": {"file_url": "pid/thumbnail.png"},
            "descriptions": {"text": "ok", "tags": []},
        }
    )
    dumped = payload.model_dump()
    assert dumped["video_assembly"]["output_url"] == "https://signed.example/pid/render.mp4?exp=3600"
    assert dumped["thumbnails"]["file_url"] == "https://signed.example/pid/thumbnail.png?exp=3600"


def test_scene_read_signs_media_url(monkeypatch):
    monkeypatch.setattr(
        "app.storage.generate_presigned_url",
        lambda key, expires_in=3600: f"https://signed.example/{key}",
    )
    scene = SceneRead.model_validate(
        {
            "id": uuid4(),
            "project_id": uuid4(),
            "index": 0,
            "start_ms": 0,
            "end_ms": 1000,
            "visual_prompt": "cena",
            "media_type": "image",
            "media_url": "pid/scene_0001.png",
            "status": "ready",
        }
    )
    assert scene.media_url == "https://signed.example/pid/scene_0001.png"


def test_character_read_signs_base_image(monkeypatch):
    monkeypatch.setattr(
        "app.storage.generate_presigned_url",
        lambda key, expires_in=3600: f"https://signed.example/{key}",
    )
    row = SimpleNamespace(
        id=uuid4(),
        description_prompt="herói",
        style_id=uuid4(),
        style=None,
        reference_image_url=None,
        base_image_url="characters/abc/base.png",
        status="pending_approval",
        created_at=datetime.now(timezone.utc),
        cost_usd=None,
        assets=[],
    )
    character = CharacterRead.model_validate(row)
    assert character.base_image_url == "https://signed.example/characters/abc/base.png"
    assert character.reference_image_url is None


def test_object_key_from_cdn_and_relative(monkeypatch):
    monkeypatch.setattr("app.storage.settings.s3_bucket", "scenecraft-media")
    monkeypatch.setattr("app.storage.settings.r2_public_base_url", "https://cdn.mazting.studio")
    assert (
        object_key_from_stored("https://cdn.mazting.studio/characters/abc/base.png")
        == "characters/abc/base.png"
    )
    assert object_key_from_stored("characters/abc/base.png") == "characters/abc/base.png"
    assert object_key_from_stored("s3://scenecraft-media/pid/render.mp4") == "pid/render.mp4"
    assert object_key_from_stored("https://images.example.com/ref.png") is None


def test_generate_presigned_url_uses_bucket_and_key(monkeypatch):
    monkeypatch.setattr("app.storage.settings.s3_bucket", "scenecraft-media")
    captured = {}

    class FakeClient:
        def generate_presigned_url(self, operation, Params=None, ExpiresIn=None):
            captured["operation"] = operation
            captured["params"] = Params
            captured["expires"] = ExpiresIn
            return "https://r2.example/signed"

    monkeypatch.setattr("app.storage._client", lambda: FakeClient())
    url = generate_presigned_url("characters/abc/base.png", expires_in=120)
    assert url == "https://r2.example/signed"
    assert captured["operation"] == "get_object"
    assert captured["params"] == {"Bucket": "scenecraft-media", "Key": "characters/abc/base.png"}
    assert captured["expires"] == 120


def test_download_url_signs_cdn_and_keys(monkeypatch):
    monkeypatch.setattr("app.storage.settings.s3_bucket", "bucket")
    monkeypatch.setattr("app.storage.settings.r2_public_base_url", "https://cdn.example.com")
    monkeypatch.setattr(
        "app.storage.generate_presigned_url",
        lambda key, expires_in=3600: f"https://signed/{key}",
    )
    assert download_url("https://cdn.example.com/pid/render.mp4") == "https://signed/pid/render.mp4"
    assert download_url("pid/render.mp4") == "https://signed/pid/render.mp4"
    assert download_url("s3://bucket/pid/render.mp4") == "https://signed/pid/render.mp4"


def test_download_url_rejects_empty():
    with pytest.raises(StorageError, match="vazia"):
        download_url("  ")
