from json import JSONDecodeError
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.api.deps import DbDep
from app.core.generate_scene_media import enqueue_scene_regenerate
from app.core.ingest import (
    IngestError,
    assert_audio_upload_filename,
    assert_upload_filename,
    parse_automation_config,
    persist_upload,
    resolve_source_ref,
    sanitize_filename,
)
from app.core.project_audio import (
    audio_generation_mode,
    set_final_audio,
    should_skip_audio_stage,
    start_audio_stage_job,
)
from app.core.project_cast import ProjectCastError, apply_cast_to_config
from app.core.state_machine import (
    IllegalTransition,
    ProjectNotFound,
    advance_stage,
    retry_stage,
    start_pipeline,
)
from app.core.transcript_edits import TranscriptEditError, apply_transcript_edits
from app.models.audio_track import AudioTrack
from app.models.enums import AudioTrackSource, ProjectStage, ProjectStatus, SourceType
from app.models.project import Project
from app.models.scene import Scene
from app.schemas.project import (
    AdvanceRead,
    AdvanceRequest,
    AudioGenerateRequest,
    ProjectCreate,
    ProjectDetail,
    ProjectRead,
    TranscriptPatchRequest,
    VoiceRead,
    normalize_automation_config,
)
from app.storage import StorageError

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProjectInput:
    def __init__(self, payload: ProjectCreate, file: UploadFile | None) -> None:
        self.payload = payload
        self.file = file


async def parse_create_input(request: Request) -> CreateProjectInput:
    content_type = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" in content_type:
        form = await request.form()
        raw_file = form.get("file")
        file = raw_file if isinstance(raw_file, UploadFile) else None
        try:
            source_type = SourceType(str(form.get("source_type") or ""))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="source_type inválido",
            ) from exc
        try:
            payload = ProjectCreate(
                title=str(form.get("title") or ""),
                source_type=source_type,
                source_ref=str(form.get("source_ref") or "") or None,
                target_language=str(form.get("target_language") or "pt-BR"),
                automation_config=parse_automation_config(form.get("automation_config")),
                image_provider=str(form.get("image_provider") or "") or None,
                character_id=str(form.get("character_id") or "") or None,
                scene_style_id=str(form.get("scene_style_id") or "") or None,
            )
        except (IngestError, ValidationError) as exc:
            _raise_create_validation(exc)
        return CreateProjectInput(payload, file)

    try:
        body = await request.json()
    except JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="JSON inválido") from exc
    try:
        payload = ProjectCreate.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
    return CreateProjectInput(payload, None)


def _raise_create_validation(exc: Exception) -> None:
    if isinstance(exc, ValidationError):
        raise RequestValidationError(exc.errors()) from exc
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


CreateInputDep = Annotated[CreateProjectInput, Depends(parse_create_input)]


def _http_for_transition(exc: Exception) -> HTTPException:
    if isinstance(exc, ProjectNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if isinstance(exc, IllegalTransition):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


def _detail_query(db, project_id: UUID) -> Project | None:
    return db.scalars(
        select(Project)
        .options(
            selectinload(Project.scenes),
            selectinload(Project.audio_tracks),
            selectinload(Project.video_assemblies),
            selectinload(Project.transcript_segments),
            selectinload(Project.jobs),
            selectinload(Project.thumbnails),
            selectinload(Project.descriptions),
        )
        .where(Project.id == project_id)
    ).first()


@router.get("")
def list_projects(db: DbDep) -> list[ProjectRead]:
    projects = list(db.scalars(select(Project).order_by(Project.created_at.desc())).all())
    return [ProjectRead.model_validate(project) for project in projects]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(parsed: CreateInputDep, db: DbDep) -> ProjectRead:
    payload = parsed.payload
    upload = parsed.file
    has_file = upload is not None and bool(upload.filename)
    try:
        source_ref = resolve_source_ref(
            source_type=payload.source_type,
            source_ref=payload.source_ref,
            has_file=has_file,
        )
    except IngestError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    project_id = uuid4()
    if has_file:
        filename = sanitize_filename(upload.filename, payload.source_type)
        try:
            assert_upload_filename(filename, payload.source_type)
            source_ref = persist_upload(
                upload.file,
                project_id=project_id,
                filename=filename,
                content_type=upload.content_type,
            )
        except IngestError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    if not source_ref:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="source_ref ausente após o upload",
        )

    try:
        automation_config = apply_cast_to_config(
            db,
            payload.automation_config,
            character_id=payload.character_id,
            scene_style_id=payload.scene_style_id,
        )
        automation_config = normalize_automation_config(
            automation_config,
            image_provider=payload.image_provider,
        )
    except ProjectCastError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    project = Project(
        id=project_id,
        title=payload.title,
        source_type=payload.source_type,
        source_ref=source_ref,
        target_language=payload.target_language,
        automation_config=automation_config,
        current_stage=ProjectStage.CREATED,
        status=ProjectStatus.PENDING,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    start_pipeline(db, project)
    db.refresh(project)
    return ProjectRead.model_validate(project)


@router.post("/{project_id}/advance")
def advance_project(
    project_id: UUID,
    db: DbDep,
    payload: AdvanceRequest | None = None,
) -> AdvanceRead:
    body = payload or AdvanceRequest()
    from_stage = body.from_stage
    if from_stage is None:
        project = db.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        from_stage = project.current_stage
    try:
        result = advance_stage(project_id, from_stage, db=db)
    except (ProjectNotFound, IllegalTransition) as exc:
        raise _http_for_transition(exc) from exc
    return AdvanceRead.model_validate(result)


@router.post("/{project_id}/retry-stage")
def retry_project_stage(project_id: UUID, db: DbDep) -> AdvanceRead:
    try:
        result = retry_stage(project_id, db=db)
    except (ProjectNotFound, IllegalTransition) as exc:
        raise _http_for_transition(exc) from exc
    return AdvanceRead.model_validate(result)


@router.patch("/{project_id}/transcript")
def patch_transcript(
    project_id: UUID,
    payload: TranscriptPatchRequest,
    db: DbDep,
) -> ProjectDetail:
    project = _detail_query(db, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if (
        project.current_stage is not ProjectStage.TRANSCRIPT_REVIEW
        or project.status is not ProjectStatus.PAUSED_FOR_REVIEW
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="transcript só pode ser editado em transcript_review",
        )
    try:
        apply_transcript_edits(list(project.transcript_segments), payload.segments)
    except TranscriptEditError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    project = _detail_query(db, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return ProjectDetail.model_validate(project)


@router.post("/{project_id}/scenes/{scene_id}/regenerate")
def regenerate_project_scene(
    project_id: UUID,
    scene_id: UUID,
    db: DbDep,
) -> ProjectDetail:
    project = _detail_query(db, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    scene = db.get(Scene, scene_id)
    if scene is None or scene.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    try:
        enqueue_scene_regenerate(project.id, scene.id, db=db)
    except (ProjectNotFound, IllegalTransition) as exc:
        raise _http_for_transition(exc) from exc
    db.commit()
    project = _detail_query(db, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return ProjectDetail.model_validate(project)


def _require_audio_input(project: Project, expected_mode: str) -> None:
    if project.current_stage is not ProjectStage.AUDIO_STAGE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="áudio só pode ser definido em audio_stage",
        )
    if project.status is not ProjectStatus.PAUSED_FOR_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="projeto não está aguardando áudio",
        )
    if should_skip_audio_stage(project):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="este projeto reutiliza o áudio original",
        )
    mode = audio_generation_mode(project.automation_config)
    if mode != expected_mode:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"audio_generation_mode deste projeto é '{mode}'",
        )


@router.get("/{project_id}/audio/voices")
def list_audio_voices(project_id: UUID, db: DbDep) -> list[VoiceRead]:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    from app.providers.elevenlabs import ElevenLabsError, list_voices

    try:
        voices = list_voices()
    except ElevenLabsError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return [VoiceRead(id=voice.id, name=voice.name) for voice in voices]


@router.post("/{project_id}/audio/generate")
def generate_project_narration(
    project_id: UUID,
    payload: AudioGenerateRequest,
    db: DbDep,
) -> ProjectDetail:
    project = _detail_query(db, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    _require_audio_input(project, "elevenlabs")
    config = dict(project.automation_config or {})
    config["voice_id"] = payload.voice_id.strip()
    project.automation_config = config
    flag_modified(project, "automation_config")
    project.status = ProjectStatus.RUNNING
    start_audio_stage_job(
        db,
        project,
        {"audio_generation_mode": "elevenlabs", "voice_id": payload.voice_id.strip()},
    )
    db.commit()
    project = _detail_query(db, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return ProjectDetail.model_validate(project)


@router.post("/{project_id}/audio/upload")
def upload_project_audio(
    project_id: UUID,
    db: DbDep,
    file: Annotated[UploadFile, File()],
) -> ProjectDetail:
    project = _detail_query(db, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    _require_audio_input(project, "user_upload")
    filename = sanitize_filename(file.filename, SourceType.UPLOAD_AUDIO)
    try:
        assert_audio_upload_filename(filename)
        url = persist_upload(
            file.file,
            project_id=project.id,
            filename=f"user_{filename}",
            content_type=file.content_type,
        )
    except IngestError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    track = AudioTrack(
        project_id=project.id,
        source=AudioTrackSource.USER_UPLOAD,
        provider="user_upload",
        file_url=url,
    )
    db.add(track)
    set_final_audio(db, project, url, AudioTrackSource.USER_UPLOAD.value)
    project.status = ProjectStatus.RUNNING
    start_audio_stage_job(db, project, {"audio_generation_mode": "user_upload"})
    db.commit()
    project = _detail_query(db, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return ProjectDetail.model_validate(project)


@router.get("/{project_id}")
def get_project(project_id: UUID, db: DbDep) -> ProjectDetail:
    project = _detail_query(db, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return ProjectDetail.model_validate(project)
