"""Monta o vídeo final: clipes (com cache), concat demuxer e mux com o áudio."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.project_audio import ensure_video_assembly
from app.core.scene_clips import (
    ClipError,
    clip_cache_entry,
    clip_output_name,
    clip_storage_url,
    ensure_scene_clips,
    ken_burns_enabled,
    run_ffmpeg,
    spec_from_scene,
)
from app.core.state_machine import IllegalTransition, ProjectNotFound, advance_stage, parse_stage
from app.models.enums import AssemblyStatus, ProjectStage, ProjectStatus
from app.models.project import Project


class RenderError(RuntimeError):
    """Falha ao concatenar, muxar ou persistir o vídeo final."""


def ffmpeg_concat_cmd(list_path: str | Path, output_path: str | Path) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c",
        "copy",
        str(output_path),
    ]


def ffmpeg_mux_cmd(video_path: str | Path, audio_path: str | Path, output_path: str | Path) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def write_concat_list(clip_paths: list[Path], list_path: str | Path) -> Path:
    dest = Path(list_path)
    lines = []
    for path in clip_paths:
        escaped = path.resolve().as_posix().replace("'", r"'\''")
        lines.append(f"file '{escaped}'")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest


def render_video(
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
    """Gera clipes (reusa cache), concatena, muxa com o áudio e avança RENDERING."""
    session, owns = _session(db)
    assembly = None
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))

        scenes = sorted(list(getattr(project, "scenes", None) or []), key=lambda item: int(item.index))
        specs = [spec_from_scene(scene) for scene in scenes]
        if not specs:
            raise RenderError("projeto sem cenas para renderizar")

        apply_zoom = ken_burns_enabled(project.automation_config) if ken_burns is None else bool(ken_burns)
        assembly = ensure_video_assembly(session, project)
        config = dict(assembly.render_config or {})
        audio_url = str(config.get("audio_url") or "").strip()
        if not audio_url:
            raise RenderError("video_assembly sem áudio final (audio_url)")

        assembly.status = AssemblyStatus.RENDERING
        session.flush()

        if download is None:
            from app.storage import download_file as download
        if upload is None:
            from app.storage import upload_file as upload
        url_fn = object_url or clip_storage_url

        total_ms = sum(max(spec.end_ms - spec.start_ms, 1) for spec in specs)
        with tempfile.TemporaryDirectory(prefix="scenecraft-render-") as tmp:
            work = Path(tmp)
            clip_paths, entries, reused = _ensure_clips(
                specs,
                work,
                ken_burns=apply_zoom,
                max_workers=max_workers,
                gere_clipe=gere_clipe,
                download=download,
                run=run,
                upload=upload,
                exists=exists,
                object_url=url_fn,
                project_id=str(project.id),
            )
            silent = work / "concat.mp4"
            concat_list = write_concat_list(clip_paths, work / "concat.txt")
            run_ffmpeg(
                ffmpeg_concat_cmd(concat_list, silent),
                timeout=max(60.0, total_ms / 1000 * 2 + 30),
                run=run,
            )
            audio_path = _download_named(audio_url, work / f"narration{_suffix(audio_url, '.mp3')}", download)
            final_path = work / "render.mp4"
            run_ffmpeg(
                ffmpeg_mux_cmd(silent, audio_path, final_path),
                timeout=max(60.0, total_ms / 1000 * 4 + 30),
                run=run,
            )
            if not final_path.is_file() or final_path.stat().st_size <= 0:
                raise RenderError("ffmpeg não gerou o vídeo final")
            output_url = upload(str(final_path), str(project.id), "render.mp4")

        config["scene_clips"] = entries
        config["ken_burns"] = apply_zoom
        assembly.render_config = config
        try:
            flag_modified(assembly, "render_config")
        except Exception:
            pass
        assembly.output_url = output_url
        assembly.status = AssemblyStatus.COMPLETED
        session.flush()
        advanced = _advance_rendering(session, project)
        if owns:
            session.commit()
        return {
            "project_id": str(project.id),
            "output_url": output_url,
            "clips": [item["url"] for item in entries],
            "reused": reused,
            "count": len(entries),
            "ken_burns": apply_zoom,
            "advanced": advanced,
        }
    except Exception:
        if assembly is not None:
            assembly.status = AssemblyStatus.FAILED
            try:
                session.flush()
            except Exception:
                pass
        if owns:
            session.rollback()
        raise
    finally:
        if owns:
            session.close()


def _ensure_clips(
    specs: list,
    work: Path,
    *,
    ken_burns: bool,
    max_workers: int | None,
    gere_clipe,
    download,
    run,
    upload,
    exists,
    object_url,
    project_id: str,
) -> tuple[list[Path], list[dict[str, Any]], list[int]]:
    url_fn = object_url or clip_storage_url
    paths, reused = ensure_scene_clips(
        specs,
        work,
        project_id=project_id,
        ken_burns=ken_burns,
        max_workers=max_workers,
        gere_clipe=gere_clipe,
        download=download,
        run=run,
        exists=exists,
        object_url=url_fn,
    )
    by_index = {spec.index: path for spec, path in zip(sorted(specs, key=lambda item: item.index), paths, strict=True)}
    reused_set = set(reused)
    entries: list[dict[str, Any]] = []
    ordered: list[Path] = []
    for spec in specs:
        path = by_index[spec.index]
        ordered.append(path)
        if spec.index in reused_set:
            url = url_fn(project_id, clip_output_name(spec))
        else:
            url = upload(str(path), project_id, clip_output_name(spec))
        entries.append(clip_cache_entry(spec, ken_burns, url))
    return ordered, entries, reused


def _download_named(url: str, dest: Path, download) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    path = Path(download(url, str(dest)))
    if not path.is_file() or path.stat().st_size <= 0:
        raise RenderError("não foi possível baixar o áudio final")
    return path


def _suffix(url: str, fallback: str) -> str:
    suffix = Path(url.split("?", 1)[0]).suffix.lower()
    return suffix if suffix else fallback


def _advance_rendering(session: Session, project: Project) -> bool:
    try:
        current = parse_stage(project.current_stage)
    except Exception:
        return False
    if current is not ProjectStage.RENDERING:
        return False
    try:
        advance_stage(project.id, ProjectStage.RENDERING, db=session)
        return True
    except IllegalTransition:
        return False


def enqueue_render_regenerate(
    project_id: str | UUID,
    db: Session | None = None,
    *,
    send_task=None,
) -> dict:
    """Dispara render_video de novo em render_review, sem avançar o estágio."""
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))
        if (
            parse_stage(project.current_stage) is not ProjectStage.RENDER_REVIEW
            or project.status is not ProjectStatus.PAUSED_FOR_REVIEW
        ):
            raise IllegalTransition("render só pode ser regenerado em render_review")
        assembly = ensure_video_assembly(session, project)
        if assembly.status is AssemblyStatus.RENDERING:
            raise IllegalTransition("render já em andamento")
        assembly.status = AssemblyStatus.RENDERING
        session.flush()
        enqueue = send_task
        if enqueue is None:
            from app.celery_app import celery_app

            enqueue = celery_app.send_task
        enqueue("scenecraft.render_video", args=[str(project.id)], queue="render")
        if owns:
            session.commit()
        return {"project_id": str(project.id)}
    except Exception:
        if owns:
            session.rollback()
        raise
    finally:
        if owns:
            session.close()


def _session(db: Session | None) -> tuple[Session, bool]:
    if db is not None:
        return db, False
    from app.db import SessionLocal

    return SessionLocal(), True
