"""Planeja cenas: o LLM agrupa segmentos; o código calcula e valida timestamps."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.project_audio import finalized_audio_track
from app.core.project_cast import enrich_visual_prompt, load_project_character, load_project_style
from app.core.state_machine import ProjectNotFound
from app.models.enums import MediaType, SceneStatus
from app.models.project import Project
from app.models.scene import Scene
from app.providers.llm_client import plan_scenes
from app.providers.pricing import add_project_llm_cost

SCENE_PACING_MS: dict[str, tuple[int, int]] = {
    "short": (8_000, 15_000),
    "medium": (15_000, 25_000),
    "long": (25_000, 40_000),
}
DEFAULT_SCENE_PACING = "medium"


class ScenePlanningError(ValueError):
    """Agrupamento ou timeline de cenas inválido."""


def resolve_scene_pacing(config: Mapping[str, Any] | None) -> tuple[str, int, int]:
    raw = str((config or {}).get("scene_pacing") or DEFAULT_SCENE_PACING).strip().lower()
    name = raw if raw in SCENE_PACING_MS else DEFAULT_SCENE_PACING
    low, high = SCENE_PACING_MS[name]
    return name, low, high


def _ms(obj: Any, key: str) -> int:
    if isinstance(obj, Mapping):
        return int(obj[key])
    return int(getattr(obj, key))


def validate_segment_partition(
    groups: Sequence[Sequence[int]],
    segment_count: int,
) -> list[list[int]]:
    """Todo índice 0..n-1 aparece em exatamente uma cena, em blocos contíguos."""
    if segment_count <= 0:
        raise ScenePlanningError("projeto sem transcript para planejar cenas")
    ordered: list[list[int]] = []
    for raw in groups:
        ids = [int(item) for item in raw]
        if not ids:
            raise ScenePlanningError("cena sem source_segment_ids")
        ordered.append(ids)
    ordered.sort(key=lambda ids: min(ids))
    used: list[int] = []
    normalized: list[list[int]] = []
    for ids in ordered:
        sequential = sorted(ids)
        if sequential != list(range(sequential[0], sequential[-1] + 1)):
            raise ScenePlanningError("source_segment_ids de cada cena devem ser contíguos")
        used.extend(sequential)
        normalized.append(sequential)
    if used != list(range(segment_count)):
        raise ScenePlanningError(
            "cada transcript_segment deve pertencer a exatamente uma cena"
        )
    return normalized


def assign_scene_times(
    segment_ids: Sequence[int],
    segments_by_index: Mapping[int, Any],
) -> tuple[int, int]:
    parts = [segments_by_index[int(item)] for item in segment_ids]
    return min(_ms(part, "start_ms") for part in parts), max(_ms(part, "end_ms") for part in parts)


def close_scene_timeline(
    scenes: list[dict[str, Any]],
    audio_duration_ms: int,
) -> list[dict[str, Any]]:
    """Cenas contíguas: preenche gaps, remove overlap e cobre o áudio até o fim."""
    if not scenes:
        return []
    scenes[0]["start_ms"] = 0
    for index in range(len(scenes) - 1):
        next_start = int(scenes[index + 1]["start_ms"])
        if int(scenes[index]["end_ms"]) != next_start:
            scenes[index]["end_ms"] = next_start
        if int(scenes[index]["end_ms"]) <= int(scenes[index]["start_ms"]):
            scenes[index]["end_ms"] = int(scenes[index]["start_ms"]) + 1
    last = scenes[-1]
    last["end_ms"] = max(int(audio_duration_ms), int(last["start_ms"]) + 1)
    return scenes


def ffprobe_duration_ms(path: str | Path) -> int:
    """Duração real do arquivo em ms via `ffprobe -show_entries format=duration`."""
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip() or str(completed.returncode)
        raise ScenePlanningError(f"ffprobe falhou ao ler a duração do áudio: {detail}")
    try:
        payload = json.loads(completed.stdout)
        raw = (payload.get("format") or {}).get("duration")
        ms = int(round(float(raw) * 1000))
    except (json.JSONDecodeError, TypeError, ValueError, AttributeError) as exc:
        raise ScenePlanningError("ffprobe não retornou duration válida") from exc
    if ms <= 0:
        raise ScenePlanningError("duração do áudio inválida")
    return ms


def _download_audio(url: str, local_path: str) -> Path:
    from app.storage import download_file

    return download_file(url, local_path)


def _probe_audio_file(url: str) -> int:
    suffix = Path(urlparse(url).path).suffix or ".mp3"
    try:
        with tempfile.TemporaryDirectory(prefix="scenecraft-scene-dur-") as tmp:
            path = _download_audio(url, str(Path(tmp) / f"audio{suffix}"))
            return ffprobe_duration_ms(path)
    except ScenePlanningError:
        raise
    except Exception as exc:
        raise ScenePlanningError(
            "não foi possível obter a duração real do áudio armazenado"
        ) from exc


def measure_project_audio_duration_ms(project: Project, db: Session | None = None) -> int:
    """Duração do áudio finalizado (estágio de áudio) via ffprobe. Sem yt-dlp."""
    del db
    track = finalized_audio_track(project)
    url = (getattr(track, "file_url", None) or "").strip() if track is not None else ""
    if not url:
        raise ScenePlanningError(
            "projeto sem áudio finalizado para medir duração; conclua o estágio de áudio antes"
        )
    return _probe_audio_file(url)


def project_audio_duration_ms(
    project: Project,
    segments: Sequence[Any] | None = None,
    db: Session | None = None,
) -> int:
    del segments  # duração sempre vem do arquivo real, nunca do último transcript_segment
    return measure_project_audio_duration_ms(project, db=db)


def scenes_from_groups(
    groups: Sequence[Mapping[str, Any]],
    segments: Sequence[Any],
    audio_duration_ms: int,
) -> list[dict[str, Any]]:
    segments_by_index = {_ms(segment, "index"): segment for segment in segments}
    if len(segments_by_index) != len(segments):
        raise ScenePlanningError("transcript_segments com index duplicado")
    partition = validate_segment_partition(
        [list(row.get("source_segment_ids") or []) for row in groups],
        segment_count=len(segments_by_index),
    )
    by_min_id = {
        min(int(item) for item in row["source_segment_ids"]): row
        for row in groups
    }
    rows: list[dict[str, Any]] = []
    for index, ids in enumerate(partition):
        start_ms, end_ms = assign_scene_times(ids, segments_by_index)
        rows.append(
            {
                "index": index,
                "source_segment_ids": ids,
                "visual_prompt": by_min_id[min(ids)]["visual_prompt"],
                "start_ms": start_ms,
                "end_ms": end_ms,
            }
        )
    return close_scene_timeline(rows, audio_duration_ms)


def plan_project_scenes(project_id: str | UUID, db: Session | None = None) -> dict:
    """Lê transcript + cast, pede agrupamento ao LLM, calcula tempos e persiste as cenas."""
    session, owns = _session(db)
    try:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        project = session.get(Project, pid)
        if project is None:
            raise ProjectNotFound(str(pid))
        segments = list(getattr(project, "transcript_segments", None) or [])
        if not segments:
            raise ScenePlanningError("projeto sem transcript para planejar cenas")

        ordered = sorted(segments, key=lambda item: item.index)
        config = project.automation_config or {}
        pacing, min_ms, max_ms = resolve_scene_pacing(config)
        character = load_project_character(session, config)
        style = load_project_style(session, config)
        grouped = plan_scenes(
            [
                {
                    "index": segment.index,
                    "start_ms": segment.start_ms,
                    "end_ms": segment.end_ms,
                    "text_original": segment.text_original,
                    "text": segment.text_translated or segment.text_original,
                }
                for segment in ordered
            ],
            language=project.target_language or "pt-BR",
            character_description=(character.description_prompt if character is not None else None),
            style_name=(style.name if style is not None else None),
            scene_pacing=pacing,
            min_duration_ms=min_ms,
            max_duration_ms=max_ms,
        )
        add_project_llm_cost(project, getattr(grouped, "cost_usd", 0))
        planned = scenes_from_groups(
            grouped,
            ordered,
            project_audio_duration_ms(project, ordered, db=session),
        )
        session.execute(delete(Scene).where(Scene.project_id == project.id))
        for row in planned:
            prompt = enrich_visual_prompt(
                str(row["visual_prompt"]),
                character=character,
                style=style,
            )
            session.add(
                Scene(
                    project_id=project.id,
                    index=int(row["index"]),
                    start_ms=int(row["start_ms"]),
                    end_ms=int(row["end_ms"]),
                    source_segment_ids=list(row["source_segment_ids"]),
                    visual_prompt=prompt,
                    media_type=MediaType.IMAGE,
                    status=SceneStatus.PENDING,
                )
            )
        session.flush()
        if owns:
            session.commit()
        return {"project_id": str(project.id), "scene_count": len(planned)}
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
