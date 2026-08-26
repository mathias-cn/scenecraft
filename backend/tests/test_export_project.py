from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.export_project import export_project
from app.core.state_machine import ProjectNotFound
from app.models.project import Project
from app.storage import StorageError, download_url


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
        video_assembly=SimpleNamespace(output_url="s3://bucket/pid/render.mp4"),
        thumbnails=[SimpleNamespace(file_url="s3://bucket/pid/thumbnail.png")],
        descriptions=[
            SimpleNamespace(text="Resumo antigo", tags=["velha"]),
            SimpleNamespace(text="Parágrafo final.", tags=["mar", "oceano"]),
        ],
    )
    data.update(kwargs)
    data["id"] = pid
    return SimpleNamespace(**data)


def test_export_project_uses_latest_description_and_signed_urls():
    project = _project()
    seen = []

    def resolve(url, *, filename=None, content_type=None):
        seen.append((url, filename, content_type))
        return f"https://signed.example/{filename}"

    payload = export_project(project.id, db=FakeDB(project), resolve_url=resolve)
    assert payload["title"] == "O Mar"
    assert payload["video_assembly"]["output_url"] == "https://signed.example/render.mp4"
    assert payload["thumbnails"]["file_url"] == "https://signed.example/thumbnail.png"
    assert payload["descriptions"]["text"] == "Parágrafo final."
    assert payload["descriptions"]["tags"] == ["mar", "oceano"]
    assert seen[0][2] == "video/mp4"
    assert seen[0][1].endswith(".mp4")


def test_export_project_allows_missing_assets():
    project = _project(video_assembly=None, thumbnails=[], descriptions=[])
    payload = export_project(project.id, db=FakeDB(project), resolve_url=lambda *_a, **_k: "nope")
    assert payload["video_assembly"]["output_url"] is None
    assert payload["thumbnails"]["file_url"] is None
    assert payload["descriptions"] == {"text": "", "tags": []}


def test_export_project_not_found():
    with pytest.raises(ProjectNotFound):
        export_project(uuid4(), db=FakeDB(_project()))


def test_download_url_returns_public_cdn(monkeypatch):
    monkeypatch.setattr("app.storage.settings.r2_public_base_url", "https://cdn.example.com")
    monkeypatch.setattr("app.storage.settings.s3_bucket", "bucket")
    url = download_url("https://cdn.example.com/pid/render.mp4")
    assert url == "https://cdn.example.com/pid/render.mp4"


def test_download_url_rewrites_s3_to_public_cdn(monkeypatch):
    monkeypatch.setattr("app.storage.settings.r2_public_base_url", "https://cdn.example.com")
    monkeypatch.setattr("app.storage.settings.s3_bucket", "bucket")
    url = download_url("s3://bucket/pid/render.mp4")
    assert url == "https://cdn.example.com/pid/render.mp4"


def test_download_url_signs_private_object(monkeypatch):
    monkeypatch.setattr("app.storage.settings.r2_public_base_url", "")
    monkeypatch.setattr("app.storage.settings.s3_bucket", "bucket")
    captured = {}

    class FakeClient:
        def generate_presigned_url(self, operation, Params=None, ExpiresIn=None):
            captured["operation"] = operation
            captured["params"] = Params
            captured["expires"] = ExpiresIn
            return "https://signed.example/render.mp4?X-Amz-Signature=abc"

    monkeypatch.setattr("app.storage._client", lambda: FakeClient())
    url = download_url(
        "s3://bucket/pid/render.mp4",
        filename="render.mp4",
        content_type="video/mp4",
    )
    assert url.startswith("https://signed.example/")
    assert captured["operation"] == "get_object"
    assert captured["params"]["ResponseContentType"] == "video/mp4"
    assert "render.mp4" in captured["params"]["ResponseContentDisposition"]
    assert captured["params"]["ResponseContentDisposition"].startswith("inline;")


def test_download_url_rejects_empty():
    with pytest.raises(StorageError, match="vazia"):
        download_url("  ")
