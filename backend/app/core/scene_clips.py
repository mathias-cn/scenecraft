"""Clipes .mp4 por cena via ffmpeg (Ken Burns opcional) com pool de workers."""

from __future__ import annotations

import hashlib
import math
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.core.project_audio import config_bool, ensure_video_assembly
from app.core.state_machine import ProjectNotFound
from app.models.enums import AssemblyStatus, MediaType
from app.models.project import Project

FPS = 25
WIDTH = 1920
HEIGHT = 1080
ZOOM_MAX = 1.15
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


class ClipError(RuntimeError):
    """Falha ao gerar o clipe de uma cena com ffmpeg."""


@dataclass(frozen=True)
class SceneClipSpec:
    id: str
    index: int
    start_ms: int
    end_ms: int
    media_url: str
    media_type: str


def clip_cache_hash(spec: Any) -> str:
    """Hash estável de media_url + start_ms + end_ms (nome do clipe no storage)."""
    item = spec if isinstance(spec, SceneClipSpec) else spec_from_scene(spec)
    payload = f"{item.media_url}|{int(item.start_ms)}|{int(item.end_ms)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def clip_output_name(spec: Any) -> str:
    return f"{clip_cache_hash(spec)}.mp4"


def clip_storage_url(project_id: str, filename: str) -> str:
    from app.storage import object_key

    return object_key(project_id, filename)


def clip_cache_entry(spec: SceneClipSpec, ken_burns: bool, url: str = "") -> dict[str, Any]:
    apply = bool(ken_burns) and spec.media_type != MediaType.VIDEO.value
    return {
        "scene_id": spec.id,
        "index": spec.index,
        "url": url,
        "media_url": spec.media_url,
        "start_ms": spec.start_ms,
        "end_ms": spec.end_ms,
        "ken_burns": apply,
        "hash": clip_cache_hash(spec),
    }


def ken_burns_enabled(config: dict[str, Any] | None) -> bool:
    if not config or "ken_burns" not in config:
        return True
    return config_bool(config, "ken_burns")


def scene_duration_ms(scene: Any) -> int:
    start = int(getattr(scene, "start_ms", 0) or 0)
    end = int(getattr(scene, "end_ms", 0) or 0)
    return max(end - start, 1)


def spec_from_scene(scene: Any) -> SceneClipSpec:
    media_type = getattr(scene, "media_type", MediaType.IMAGE)
    value = media_type.value if hasattr(media_type, "value") else str(media_type or "image")
    return SceneClipSpec(
        id=str(getattr(scene, "id", getattr(scene, "index", ""))),
        index=int(getattr(scene, "index", 0) or 0),
        start_ms=int(getattr(scene, "start_ms", 0) or 0),
        end_ms=int(getattr(scene, "end_ms", 0) or 0),
        media_url=str(getattr(scene, "media_url", None) or "").strip(),
        media_type=value,
    )


def ffmpeg_clipe_cmd(
    image_path: str | Path,
    output_path: str | Path,
    duration_ms: int,
    *,
    ken_burns: bool = True,
) -> list[str]:
    """Monta o argv do ffmpeg: 1920x1080, 25 fps, duração exata, zoompan opcional até 1.15."""
    ms = max(int(duration_ms), 1)
    duration_s = ms / 1000
    frames = max(1, math.ceil(ms * FPS / 1000))
    scale = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT}"
    )
    if ken_burns:
        step = ZOOM_MAX - 1.0
        increment = step / max(frames - 1, 1)
        vf = (
            f"{scale},"
            f"zoompan=z='min(1+{increment:.8f}*on,{ZOOM_MAX})':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS}"
        )
    else:
        vf = scale
    return [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-vf",
        vf,
        "-t",
        f"{duration_s:.3f}",
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(output_path),
    ]


def gere_clipe_cena(
    scene: Any,
    output_path: str | Path | None = None,
    *,
    ken_burns: bool = True,
    image_path: str | Path | None = None,
    download=None,
    run=None,
) -> Path:
    """Gera um .mp4 da imagem da cena com a duração de (end_ms - start_ms)."""
    spec = scene if isinstance(scene, SceneClipSpec) else spec_from_scene(scene)
    duration = scene_duration_ms(spec)
    dest = Path(output_path) if output_path else Path(tempfile.mkdtemp(prefix="scenecraft-clip-")) / clip_output_name(spec)
    dest.parent.mkdir(parents=True, exist_ok=True)
    source = Path(image_path) if image_path else _download_scene_image(spec, dest.parent, download=download)
    if not source.is_file():
        raise ClipError(f"cena {spec.index} sem arquivo de imagem")
    apply_zoom = ken_burns and spec.media_type != MediaType.VIDEO.value
    cmd = ffmpeg_clipe_cmd(source, dest, duration, ken_burns=apply_zoom)
    timeout = max(30.0, duration / 1000 * 8 + 15)
    _run_ffmpeg(cmd, timeout=timeout, run=run)
    if not dest.is_file() or dest.stat().st_size <= 0:
        raise ClipError(f"cena {spec.index}: ffmpeg não gerou o clipe")
    return dest


def gere_clipes_cenas(
    scenes: Sequence[Any],
    output_dir: str | Path,
    *,
    ken_burns: bool = True,
    max_workers: int | None = None,
    gere_clipe=None,
    download=None,
    run=None,
) -> list[Path]:
    """Gera os clipes em paralelo, limitado por RENDER_CLIP_CONCURRENCY."""
    specs = [scene if isinstance(scene, SceneClipSpec) else spec_from_scene(scene) for scene in scenes]
    if not specs:
        raise ClipError("projeto sem cenas para renderizar")
    missing = [spec.index for spec in specs if not spec.media_url]
    if missing:
        raise ClipError(f"cenas sem imagem: {', '.join(str(item) for item in missing)}")
    dest_dir = Path(output_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    worker = gere_clipe or gere_clipe_cena
    workers = max(1, int(max_workers or settings.render_clip_concurrency))
    ordered: dict[int, Path] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                worker,
                spec,
                dest_dir / clip_output_name(spec),
                ken_burns=ken_burns,
                download=download,
                run=run,
            ): spec
            for spec in specs
        }
        for future in as_completed(futures):
            spec = futures[future]
            try:
                ordered[spec.index] = future.result()
            except Exception as exc:
                errors.append(f"#{spec.index}: {exc}")
    if errors:
        raise ClipError("falha ao gerar clipes: " + "; ".join(errors))
    return [ordered[spec.index] for spec in sorted(specs, key=lambda item: item.index)]


def ensure_scene_clips(
    scenes: Sequence[Any],
    output_dir: str | Path,
    *,
    project_id: str,
    ken_burns: bool = True,
    max_workers: int | None = None,
    gere_clipe=None,
    download=None,
    run=None,
    exists=None,
    object_url=None,
) -> tuple[list[Path], list[int]]:
    """Gera clipes só se o hash ainda não existir no storage; senão baixa o cache."""
    specs = [scene if isinstance(scene, SceneClipSpec) else spec_from_scene(scene) for scene in scenes]
    if not specs:
        raise ClipError("projeto sem cenas para renderizar")
    dest_dir = Path(output_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    exists_fn = exists
    if exists_fn is None:
        from app.storage import object_exists as exists_fn
    url_fn = object_url or clip_storage_url

    local_by_hash: dict[str, Path] = {}
    reused_hashes: set[str] = set()
    stale: list[SceneClipSpec] = []
    queued: set[str] = set()
    fetch = download
    for spec in specs:
        digest = clip_cache_hash(spec)
        filename = clip_output_name(spec)
        dest = dest_dir / filename
        if digest in local_by_hash or digest in queued:
            continue
        if exists_fn(str(project_id), filename):
            if fetch is None:
                from app.storage import download_file as fetch
            downloaded = Path(fetch(url_fn(str(project_id), filename), str(dest)))
            if downloaded.is_file() and downloaded.stat().st_size > 0:
                local_by_hash[digest] = downloaded
                reused_hashes.add(digest)
                continue
        stale.append(spec)
        queued.add(digest)

    if stale:
        generated = gere_clipes_cenas(
            stale,
            dest_dir,
            ken_burns=ken_burns,
            max_workers=max_workers,
            gere_clipe=gere_clipe,
            download=download,
            run=run,
        )
        for spec, path in zip(sorted(stale, key=lambda item: item.index), generated, strict=True):
            local_by_hash[clip_cache_hash(spec)] = path

    missing = [
        spec.index for spec in specs if clip_cache_hash(spec) not in local_by_hash
    ]
    if missing:
        raise ClipError(f"cenas sem clipe: {', '.join(str(item) for item in missing)}")
    ordered = [local_by_hash[clip_cache_hash(spec)] for spec in sorted(specs, key=lambda item: item.index)]
    reused = [
        spec.index
        for spec in sorted(specs, key=lambda item: item.index)
        if clip_cache_hash(spec) in reused_hashes
    ]
    return ordered, reused


def gere_clipes_projeto(
    project_id: str | UUID,
    db: Session | None = None,
    *,
    ken_burns: bool | None = None,
    max_workers: int | None = None,
    gere_clipe=None,
    download=None,
    run=None,
    upload=None,
    exists=None,
    object_url=None,
) -> dict:
    """Render: gera clipes (reusa hash no storage) e grava URLs em render_config."""
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))
        scenes = sorted(list(getattr(project, "scenes", None) or []), key=lambda item: int(item.index))
        specs = [spec_from_scene(scene) for scene in scenes]
        apply_zoom = ken_burns_enabled(project.automation_config) if ken_burns is None else bool(ken_burns)
        assembly = ensure_video_assembly(session, project)
        assembly.status = AssemblyStatus.RENDERING
        session.flush()

        if upload is None:
            from app.storage import upload_file as upload
        url_fn = object_url or clip_storage_url

        with tempfile.TemporaryDirectory(prefix="scenecraft-clips-") as tmp:
            clips, reused = ensure_scene_clips(
                specs,
                tmp,
                project_id=str(project.id),
                ken_burns=apply_zoom,
                max_workers=max_workers,
                gere_clipe=gere_clipe,
                download=download,
                run=run,
                exists=exists,
                object_url=url_fn,
            )
            reused_set = set(reused)
            urls: list[str] = []
            for spec, path in zip(specs, clips, strict=True):
                if spec.index in reused_set:
                    urls.append(url_fn(str(project.id), clip_output_name(spec)))
                else:
                    urls.append(upload(str(path), str(project.id), clip_output_name(spec)))
            entries = [
                clip_cache_entry(spec, apply_zoom, url)
                for spec, url in zip(specs, urls, strict=True)
            ]

        config = dict(assembly.render_config or {})
        config["scene_clips"] = entries
        config["ken_burns"] = apply_zoom
        assembly.render_config = config
        try:
            flag_modified(assembly, "render_config")
        except Exception:
            pass
        session.flush()
        if owns:
            session.commit()
        return {
            "project_id": str(project.id),
            "clips": [item["url"] for item in entries],
            "count": len(entries),
            "reused": reused,
            "ken_burns": apply_zoom,
        }
    except Exception:
        if owns:
            session.rollback()
        raise
    finally:
        if owns:
            session.close()


def _image_suffix(url: str) -> str:
    suffix = Path(url.split("?", 1)[0]).suffix.lower()
    return suffix if suffix in _IMAGE_SUFFIXES else ".png"


def _download_scene_image(spec: SceneClipSpec, folder: Path, *, download=None) -> Path:
    if not spec.media_url:
        raise ClipError(f"cena {spec.index} sem media_url")
    dest = folder / f"scene_{spec.index:04d}_src{_image_suffix(spec.media_url)}"
    if download is None:
        from app.storage import download_file as download
    return Path(download(spec.media_url, str(dest)))


def _run_ffmpeg(cmd: list[str], *, timeout: float, run=None) -> None:
    runner = run or subprocess.run
    try:
        completed = runner(cmd, check=False, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise ClipError("ffmpeg excedeu o tempo limite") from exc
    code = getattr(completed, "returncode", 0)
    if code:
        err = (getattr(completed, "stderr", None) or getattr(completed, "stdout", None) or "").strip()
        raise ClipError(f"ffmpeg falhou: {(err or str(code))[:500]}")


run_ffmpeg = _run_ffmpeg


def _session(db: Session | None) -> tuple[Session, bool]:
    if db is not None:
        return db, False
    from app.db import SessionLocal

    return SessionLocal(), True
