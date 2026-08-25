from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.render_video import (
    RenderError,
    ffmpeg_concat_cmd,
    ffmpeg_mux_cmd,
    render_video,
    write_concat_list,
)
from app.core.scene_clips import clip_cache_entry, spec_from_scene
from app.core.state_machine import linear_next, parse_stage
from app.models.enums import AssemblyStatus, MediaType, ProjectStage, SourceType
from app.models.project import Project


class FakeDB:
    def __init__(self, project):
        self.project = project
        self.added = []
        self.commits = 0

    def get(self, model, pid):
        if model is Project and self.project.id == pid:
            return self.project
        return None

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        return None

    def commit(self):
        self.commits += 1

    def rollback(self):
        return None

    def close(self):
        return None


def _scene(**kwargs):
    data = dict(
        id=uuid4(),
        index=0,
        start_ms=0,
        end_ms=800,
        media_url="https://cdn.example.com/s.png",
        media_type=MediaType.IMAGE,
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


def _assembly(**kwargs):
    data = dict(
        render_config={"audio_url": "https://cdn.example.com/narration.mp3"},
        status=AssemblyStatus.PENDING,
        output_url=None,
        ffmpeg_job_id=None,
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


def _project(scenes, assembly=None, **kwargs):
    pid = kwargs.pop("id", uuid4())
    assembly = assembly or _assembly()
    data = dict(
        id=pid,
        source_type=SourceType.YOUTUBE_LINK,
        current_stage=ProjectStage.RENDERING,
        automation_config={"ken_burns": True},
        scenes=scenes,
        video_assemblies=[assembly],
        video_assembly=assembly,
    )
    data.update(kwargs)
    data["id"] = pid
    return SimpleNamespace(**data)


def _stub_advance(project):
    def fake_advance(_pid, stage, db=None):
        nxt = linear_next(parse_stage(stage))
        project.current_stage = nxt
        return SimpleNamespace(to_stage=nxt)

    return fake_advance


def _fake_run(cmd, **_kwargs):
    Path(cmd[-1]).write_bytes(b"ftypmp4")
    return SimpleNamespace(returncode=0, stderr="", stdout="")


def _fake_download(url, dest):
    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"bytes")
    return path


def test_ffmpeg_concat_cmd_uses_demuxer():
    cmd = ffmpeg_concat_cmd("list.txt", "out.mp4")
    assert cmd[cmd.index("-f") + 1] == "concat"
    assert "-safe" in cmd
    assert cmd[cmd.index("-c") + 1] == "copy"


def test_ffmpeg_mux_cmd_uses_shortest():
    cmd = ffmpeg_mux_cmd("video.mp4", "audio.mp3", "final.mp4")
    assert "-shortest" in cmd
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    assert cmd.count("-i") == 2


def test_write_concat_list_keeps_scene_order(tmp_path):
    a = tmp_path / "scene_0000.mp4"
    b = tmp_path / "scene_0001.mp4"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    dest = write_concat_list([a, b], tmp_path / "concat.txt")
    text = dest.read_text(encoding="utf-8")
    assert text.index("scene_0000.mp4") < text.index("scene_0001.mp4")
    assert text.strip().startswith("file '")


def test_render_video_concat_mux_upload_and_advances(monkeypatch):
    scenes = [_scene(index=1, end_ms=400), _scene(index=0, end_ms=800)]
    project = _project(scenes)
    monkeypatch.setattr("app.core.render_video.advance_stage", _stub_advance(project))
    generated = []
    uploads = []
    cmds = []
    concat_listing = []

    def fake_clip(spec, output_path=None, **_k):
        generated.append(spec.index)
        path = Path(output_path)
        path.write_bytes(b"clip")
        return path

    def fake_upload(local, project_id, filename):
        uploads.append(filename)
        return f"https://cdn.example.com/{filename}"

    def fake_run(cmd, **kwargs):
        cmds.append(list(cmd))
        if "-f" in cmd and cmd[cmd.index("-f") + 1] == "concat":
            concat_listing.append(Path(cmd[cmd.index("-i") + 1]).read_text(encoding="utf-8"))
        return _fake_run(cmd, **kwargs)

    result = render_video(
        project.id,
        db=FakeDB(project),
        gere_clipe=fake_clip,
        download=_fake_download,
        run=fake_run,
        upload=fake_upload,
    )
    assert set(generated) == {0, 1}
    mux = next(cmd for cmd in cmds if "-shortest" in cmd)
    assert concat_listing
    listing = concat_listing[0]
    assert listing.index("scene_0000.mp4") < listing.index("scene_0001.mp4")
    assert mux[-1].endswith("render.mp4")
    assert result["output_url"] == "https://cdn.example.com/render.mp4"
    assert result["advanced"] is True
    assert project.video_assembly.output_url == result["output_url"]
    assert project.video_assembly.status is AssemblyStatus.COMPLETED
    assert project.current_stage is ProjectStage.RENDER_REVIEW
    assert "render.mp4" in uploads
    assert result["reused"] == []


def test_render_video_reuses_unchanged_clip_cache(monkeypatch):
    scene = _scene(index=0, end_ms=800)
    spec = spec_from_scene(scene)
    cached = clip_cache_entry(spec, True, "https://cdn.example.com/scene_0000.mp4")
    assembly = _assembly(render_config={"audio_url": "https://cdn.example.com/n.mp3", "scene_clips": [cached]})
    project = _project([scene], assembly=assembly)
    monkeypatch.setattr("app.core.render_video.advance_stage", _stub_advance(project))
    generated = []
    downloads = []

    def fake_clip(spec, output_path=None, **_k):
        generated.append(spec.index)
        path = Path(output_path)
        path.write_bytes(b"clip")
        return path

    def fake_download(url, dest):
        downloads.append(url)
        return _fake_download(url, dest)

    result = render_video(
        project.id,
        db=FakeDB(project),
        gere_clipe=fake_clip,
        download=fake_download,
        run=_fake_run,
        upload=lambda *_a, **_k: "https://cdn.example.com/render.mp4",
    )
    assert generated == []
    assert result["reused"] == [0]
    assert cached["url"] in downloads
    assert project.video_assembly.render_config["scene_clips"][0]["url"] == cached["url"]


def test_render_video_regenerates_when_duration_changes(monkeypatch):
    scene = _scene(index=0, start_ms=0, end_ms=800)
    old = spec_from_scene(_scene(id=scene.id, index=0, start_ms=0, end_ms=400, media_url=scene.media_url))
    cached = clip_cache_entry(old, True, "https://cdn.example.com/scene_0000.mp4")
    assembly = _assembly(render_config={"audio_url": "https://cdn.example.com/n.mp3", "scene_clips": [cached]})
    project = _project([scene], assembly=assembly)
    monkeypatch.setattr("app.core.render_video.advance_stage", _stub_advance(project))
    generated = []

    def fake_clip(spec, output_path=None, **_k):
        generated.append((spec.index, spec.end_ms))
        path = Path(output_path)
        path.write_bytes(b"clip")
        return path

    render_video(
        project.id,
        db=FakeDB(project),
        gere_clipe=fake_clip,
        download=_fake_download,
        run=_fake_run,
        upload=lambda local, pid, filename: f"https://cdn.example.com/{filename}",
    )
    assert generated == [(0, 800)]


def test_render_video_requires_final_audio(monkeypatch):
    project = _project([_scene()], assembly=_assembly(render_config={}))
    monkeypatch.setattr("app.core.render_video.advance_stage", _stub_advance(project))
    with pytest.raises(RenderError, match="áudio final"):
        render_video(
            project.id,
            db=FakeDB(project),
            gere_clipe=lambda *_a, **_k: Path("x"),
            download=_fake_download,
            run=_fake_run,
            upload=lambda *_a, **_k: "https://cdn.example.com/x.mp4",
        )
    assert project.video_assembly.status is AssemblyStatus.FAILED


def test_celery_task_is_registered_with_project_id_signature():
    celery = pytest.importorskip("celery")
    _ = celery
    from app.tasks.render import render_video as task

    assert task.name == "scenecraft.render_video"
