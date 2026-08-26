"""Config e persistência do áudio final do projeto."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.audio_track import AudioTrack
from app.models.enums import AssemblyStatus, AudioTrackSource, SourceType
from app.models.project import Project
from app.models.video_assembly import VideoAssembly

AUDIO_GENERATION_MODES = ("elevenlabs", "user_upload")
_TRUE = {True, 1, "1", "true", "True", "yes", "on"}


class ProjectAudioError(ValueError):
    """Áudio do projeto inválido ou ausente."""


def config_bool(config: dict[str, Any] | None, key: str) -> bool:
    return (config or {}).get(key) in _TRUE


def source_value(source: Any) -> str:
    if source is None:
        return ""
    return str(getattr(source, "value", source))


def should_skip_audio_stage(project: Project) -> bool:
    source = project.source_type
    value = source.value if hasattr(source, "value") else str(source)
    if value != SourceType.UPLOAD_AUDIO.value:
        return False
    return config_bool(project.automation_config, "reuse_original_audio")


def audio_generation_mode(config: dict[str, Any] | None) -> str:
    if config_bool(config, "reuse_original_audio"):
        return "reuse"
    mode = str((config or {}).get("audio_generation_mode") or "elevenlabs").strip().lower()
    return mode if mode in AUDIO_GENERATION_MODES else "elevenlabs"


def iter_tracks(project: Project) -> list[AudioTrack]:
    return list(getattr(project, "audio_tracks", None) or [])


def find_track(project: Project, source: AudioTrackSource) -> AudioTrack | None:
    wanted = source.value
    for track in reversed(iter_tracks(project)):
        if source_value(track.source) == wanted and (track.file_url or "").strip():
            return track
    return None


def original_audio_track(project: Project) -> AudioTrack | None:
    return find_track(project, AudioTrackSource.ORIGINAL)


def final_narration_track(project: Project) -> AudioTrack | None:
    for source in (AudioTrackSource.USER_UPLOAD, AudioTrackSource.GENERATED):
        track = find_track(project, source)
        if track is not None:
            return track
    return None


def finalized_audio_track(project: Project) -> AudioTrack | None:
    """Áudio já produzido no estágio de áudio (TTS/upload) ou original reaproveitado."""
    return final_narration_track(project) or original_audio_track(project)


def persist_original_audio(session: Session, project: Project, audio_path: str | Path) -> AudioTrack:
    """Envia o áudio extraído na transcrição para o R2 e grava audio_tracks.source=original."""
    existing = original_audio_track(project)
    if existing is not None:
        return existing
    path = Path(audio_path)
    suffix = path.suffix.lower() or ".mp3"
    from app.storage import upload_file

    object_key = upload_file(str(path), str(project.id), f"original{suffix}")
    track = AudioTrack(
        project_id=project.id,
        source=AudioTrackSource.ORIGINAL,
        file_url=object_key,
        provider=None,
    )
    session.add(track)
    tracks = getattr(project, "audio_tracks", None)
    if tracks is not None:
        tracks.append(track)
    return track


def ensure_video_assembly(session: Session, project: Project) -> VideoAssembly:
    assembly = getattr(project, "video_assembly", None)
    if assembly is not None:
        return assembly
    assembly = VideoAssembly(
        project_id=project.id,
        status=AssemblyStatus.PENDING,
        render_config={},
    )
    session.add(assembly)
    assemblies = getattr(project, "video_assemblies", None)
    if assemblies is not None:
        assemblies.append(assembly)
    session.flush()
    return assembly


def set_final_audio(session: Session, project: Project, file_url: str, source: str) -> VideoAssembly:
    """Grava o áudio final em video_assembly.render_config para o render."""
    if not (file_url or "").strip():
        raise ProjectAudioError("áudio final sem file_url")
    assembly = ensure_video_assembly(session, project)
    config = dict(assembly.render_config or {})
    config["audio_url"] = file_url
    config["audio_source"] = source
    assembly.render_config = config
    try:
        flag_modified(assembly, "render_config")
    except Exception:
        pass
    return assembly


def attach_original_audio_for_render(session: Session, project: Project) -> str:
    """Copia o áudio original (upload) para o render, sem re-transcrever.

    Não baixa YouTube nem roteiro em texto: esses tipos não têm áudio original.
    """
    track = original_audio_track(project)
    url = (track.file_url if track is not None else "") or ""
    if not url.strip():
        url = _extract_original_audio(session, project)
    set_final_audio(session, project, url, AudioTrackSource.ORIGINAL.value)
    return url


def _has_no_original_audio(project: Project) -> bool:
    value = getattr(project.source_type, "value", project.source_type)
    return str(value) in {SourceType.YOUTUBE_LINK.value, SourceType.TEXT_SCRIPT.value}


def _extract_original_audio(session: Session, project: Project) -> str:
    if _has_no_original_audio(project):
        value = getattr(project.source_type, "value", project.source_type)
        raise ProjectAudioError(
            f"{value} não tem áudio original para reaproveitar; use ElevenLabs ou upload próprio"
        )
    import tempfile

    from app.core.source_downloader import load_audio

    with tempfile.TemporaryDirectory(prefix="scenecraft-original-audio-") as tmp:
        path = load_audio(project, Path(tmp))
        track = persist_original_audio(session, project, path)
    if not (track.file_url or "").strip():
        raise ProjectAudioError("não foi possível persistir o áudio original")
    return track.file_url


def start_audio_stage_job(
    session: Session,
    project: Project,
    payload: dict[str, Any],
) -> UUID:
    """Enfileira o job de AUDIO_STAGE (TTS e/ou re-transcrição)."""
    from app.core.state_machine import dispatch_job_group
    from app.models.enums import ProjectStage

    _, jobs = dispatch_job_group(session, project, ProjectStage.AUDIO_STAGE, [payload])
    return jobs[0].id
