"""Validação da fonte do projeto (YouTube vs upload)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from app.models.enums import SourceType

VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma"}


class IngestError(ValueError):
    pass


def parse_automation_config(raw: Any) -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise IngestError("automation_config deve ser um JSON objeto") from exc
        if not isinstance(parsed, dict):
            raise IngestError("automation_config deve ser um JSON objeto")
        return parsed
    raise IngestError("automation_config inválido")


def sanitize_filename(filename: str | None, source_type: SourceType) -> str:
    name = Path(filename or "").name.strip()
    if not name or name in {".", ".."}:
        suffix = ".mp4" if source_type is SourceType.UPLOAD_VIDEO else ".mp3"
        return f"source{suffix}"
    return name.replace("\\", "_").replace("/", "_")


def assert_audio_upload_filename(filename: str) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix not in AUDIO_SUFFIXES:
        raise IngestError(f"arquivo de áudio inválido ({suffix or 'sem extensão'})")


def assert_upload_filename(filename: str, source_type: SourceType) -> None:
    suffix = Path(filename).suffix.lower()
    if source_type is SourceType.UPLOAD_VIDEO and suffix not in VIDEO_SUFFIXES:
        raise IngestError(f"arquivo de vídeo inválido ({suffix or 'sem extensão'})")
    if source_type is SourceType.UPLOAD_AUDIO and suffix not in AUDIO_SUFFIXES:
        raise IngestError(f"arquivo de áudio inválido ({suffix or 'sem extensão'})")


def resolve_source_ref(
    *,
    source_type: SourceType,
    source_ref: str | None,
    has_file: bool,
) -> str | None:
    """Valida a combinação fonte/arquivo. Devolve source_ref já limpo, ou None se o upload for obrigatório."""
    ref = (source_ref or "").strip()
    if source_type is SourceType.YOUTUBE_LINK:
        if has_file:
            raise IngestError("youtube_link não aceita arquivo; envie source_ref com a URL")
        if not ref:
            raise IngestError("source_ref é obrigatório para youtube_link")
        return ref
    if source_type in {SourceType.UPLOAD_VIDEO, SourceType.UPLOAD_AUDIO}:
        if has_file:
            return None
        if not ref:
            raise IngestError("envie um arquivo (multipart) ou source_ref apontando para o storage")
        return ref
    raise IngestError(f"source_type não suportado: {source_type}")


def persist_upload(
    fileobj,
    *,
    project_id: UUID,
    filename: str,
    content_type: str | None,
) -> str:
    from app.storage import upload_fileobj

    return upload_fileobj(
        fileobj,
        str(project_id),
        filename,
        content_type=content_type,
    )
