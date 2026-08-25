from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.scene_clips import (
    ZOOM_MAX,
    ClipError,
    clip_cache_hash,
    clip_output_name,
    ensure_scene_clips,
    ffmpeg_clipe_cmd,
    gere_clipe_cena,
    gere_clipes_cenas,
    gere_clipes_projeto,
    ken_burns_enabled,
    scene_duration_ms,
    spec_from_scene,
)
from app.models.enums import AssemblyStatus, MediaType, SourceType
from app.models.project import Project
from app.schemas.project import ProjectCreate


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
        end_ms=2000,
        media_url="https://cdn.example.com/s.png",
        media_type=MediaType.IMAGE,
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


def _fake_run(cmd, **_kwargs):
    Path(cmd[-1]).write_bytes(b"ftypmp4")
    return SimpleNamespace(returncode=0, stderr="", stdout="")


def test_scene_duration_ms_is_end_minus_start():
    assert scene_duration_ms(_scene(start_ms=500, end_ms=2500)) == 2000
    assert scene_duration_ms(_scene(start_ms=10, end_ms=10)) == 1


def test_ffmpeg_clipe_cmd_zoompan_when_ken_burns():
    cmd = ffmpeg_clipe_cmd("in.png", "out.mp4", 2000, ken_burns=True)
    assert cmd[0] == "ffmpeg"
    assert "-loop" in cmd
    vf = cmd[cmd.index("-vf") + 1]
    assert "scale=1920:1080" in vf
    assert "zoompan" in vf
    assert f"{ZOOM_MAX}" in vf
    assert "fps=25" in vf
    assert cmd[cmd.index("-t") + 1] == "2.000"
    assert cmd[cmd.index("-r") + 1] == "25"


def test_ffmpeg_clipe_cmd_skips_zoompan_without_ken_burns():
    cmd = ffmpeg_clipe_cmd("in.png", "out.mp4", 1200, ken_burns=False)
    vf = cmd[cmd.index("-vf") + 1]
    assert "zoompan" not in vf
    assert "scale=1920:1080" in vf
    assert cmd[cmd.index("-t") + 1] == "1.200"


def test_gere_clipe_cena_runs_ffmpeg_for_exact_duration(tmp_path):
    image = tmp_path / "still.png"
    image.write_bytes(b"PNG")
    scene = _scene(start_ms=0, end_ms=800)
    dest = tmp_path / "clip.mp4"
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        return _fake_run(cmd, **kwargs)

    path = gere_clipe_cena(scene, dest, ken_burns=True, image_path=image, run=fake_run)
    assert path == dest
    assert dest.is_file()
    vf = seen[0][seen[0].index("-vf") + 1]
    assert "zoompan" in vf
    assert seen[0][seen[0].index("-t") + 1] == "0.800"


def test_gere_clipe_cena_without_ken_burns(tmp_path):
    image = tmp_path / "still.png"
    image.write_bytes(b"PNG")
    seen = []
    gere_clipe_cena(
        _scene(),
        tmp_path / "clip.mp4",
        ken_burns=False,
        image_path=image,
        run=lambda cmd, **k: seen.append(cmd) or _fake_run(cmd, **k),
    )
    assert "zoompan" not in seen[0][seen[0].index("-vf") + 1]


def test_gere_clipe_cena_raises_without_image():
    with pytest.raises(ClipError, match="sem"):
        gere_clipe_cena(_scene(media_url=""), ken_burns=True, run=_fake_run)


def test_gere_clipes_cenas_uses_worker_pool(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr("app.core.scene_clips.settings.render_clip_concurrency", 3)
    scenes = [_scene(index=1, end_ms=400), _scene(index=0, end_ms=800)]
    seen_workers = []
    real_pool = ThreadPoolExecutor

    def tracking_pool(max_workers=None, **kwargs):
        seen_workers.append(max_workers)
        return real_pool(max_workers=max_workers, **kwargs)

    monkeypatch.setattr("app.core.scene_clips.ThreadPoolExecutor", tracking_pool)

    def fake_clip(spec, output_path=None, **_k):
        path = Path(output_path)
        path.write_bytes(b"mp4")
        return path

    paths = gere_clipes_cenas(scenes, tmp_path, gere_clipe=fake_clip)
    assert seen_workers == [3]
    assert [path.name for path in paths] == [
        clip_output_name(spec_from_scene(scenes[1])),
        clip_output_name(spec_from_scene(scenes[0])),
    ]


def test_ken_burns_enabled_defaults_true():
    assert ken_burns_enabled(None) is True
    assert ken_burns_enabled({}) is True
    assert ken_burns_enabled({"ken_burns": False}) is False
    assert ken_burns_enabled({"ken_burns": True}) is True


def test_project_create_persists_ken_burns_flag():
    payload = ProjectCreate(
        title="clip",
        source_type=SourceType.YOUTUBE_LINK,
        source_ref="https://youtu.be/x",
        automation_config={"ken_burns": False},
    )
    assert payload.automation_config["ken_burns"] is False
    default = ProjectCreate(
        title="clip",
        source_type=SourceType.YOUTUBE_LINK,
        source_ref="https://youtu.be/x",
    )
    assert default.automation_config["ken_burns"] is True


def test_clip_cache_hash_is_stable_and_changes_with_inputs():
    scene = _scene(media_url="https://cdn.example.com/a.png", start_ms=0, end_ms=800)
    same = _scene(media_url="https://cdn.example.com/a.png", start_ms=0, end_ms=800, index=9)
    assert clip_cache_hash(scene) == clip_cache_hash(same)
    assert clip_output_name(scene) == f"{clip_cache_hash(scene)}.mp4"
    assert clip_cache_hash(_scene(media_url="https://cdn.example.com/b.png", start_ms=0, end_ms=800)) != clip_cache_hash(scene)
    assert clip_cache_hash(_scene(media_url=scene.media_url, start_ms=0, end_ms=1200)) != clip_cache_hash(scene)


def test_ensure_scene_clips_reuses_storage_hash(tmp_path):
    kept = _scene(index=0, media_url="https://cdn.example.com/a.png", end_ms=800)
    changed = _scene(index=1, media_url="https://cdn.example.com/b-new.png", end_ms=400)
    kept_name = clip_output_name(spec_from_scene(kept))
    generated = []

    def fake_clip(spec, output_path=None, **_k):
        generated.append(spec.index)
        path = Path(output_path)
        path.write_bytes(b"new")
        return path

    def fake_download(url, dest):
        path = Path(dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"cached")
        return path

    paths, reused = ensure_scene_clips(
        [kept, changed],
        tmp_path,
        project_id="proj",
        gere_clipe=fake_clip,
        download=fake_download,
        exists=lambda _pid, name: name == kept_name,
        object_url=lambda _pid, name: f"https://cdn.example.com/{name}",
    )
    assert reused == [0]
    assert generated == [1]
    assert [path.name for path in paths] == [
        kept_name,
        clip_output_name(spec_from_scene(changed)),
    ]
    assert paths[0].read_bytes() == b"cached"
    assert paths[1].read_bytes() == b"new"


def test_gere_clipes_projeto_uploads_and_stores_config(tmp_path):
    pid = uuid4()
    scene = _scene(index=0, end_ms=400)
    filename = clip_output_name(spec_from_scene(scene))
    project = SimpleNamespace(
        id=pid,
        source_type=SourceType.YOUTUBE_LINK,
        automation_config={"ken_burns": True},
        scenes=[scene],
        video_assemblies=[],
        video_assembly=None,
    )
    uploaded = []

    def fake_clip(spec, output_path=None, **_k):
        path = Path(output_path)
        path.write_bytes(b"mp4")
        return path

    def fake_upload(local, project_id, filename):
        uploaded.append((local, project_id, filename))
        return f"https://cdn.example.com/{filename}"

    result = gere_clipes_projeto(
        project.id,
        db=FakeDB(project),
        gere_clipe=fake_clip,
        upload=fake_upload,
        exists=lambda *_a, **_k: False,
    )
    assert result["count"] == 1
    assert result["ken_burns"] is True
    assert result["reused"] == []
    assert result["clips"] == [f"https://cdn.example.com/{filename}"]
    assert project.video_assemblies[0].render_config["scene_clips"][0]["url"] == result["clips"][0]
    assert project.video_assemblies[0].render_config["scene_clips"][0]["hash"] == clip_cache_hash(spec_from_scene(scene))
    assert project.video_assemblies[0].status is AssemblyStatus.RENDERING
    assert uploaded[0][2] == filename
