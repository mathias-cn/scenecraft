from json import JSONDecodeError
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.api.deps import DbDep
from app.core.ingest import (
    IngestError,
    assert_upload_filename,
    parse_automation_config,
    persist_upload,
    resolve_source_ref,
    sanitize_filename,
)
from app.core.state_machine import (
    IllegalTransition,
    ProjectNotFound,
    advance_stage,
    retry_stage,
    start_pipeline,
)
from app.core.transcript_edits import TranscriptEditError, apply_transcript_edits
from app.models.enums import ProjectStage, ProjectStatus, SourceType
from app.models.project import Project
from app.providers.image_provider import OPENAI_IMAGE_MODELS, parse_image_provider
from app.schemas.project import (
    AdvanceRead,
    AdvanceRequest,
    ImageModelRead,
    MediaSettingsPatch,
    ProjectCreate,
    ProjectDetail,
    ProjectRead,
    TranscriptPatchRequest,
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

    project = Project(
        id=project_id,
        title=payload.title,
        source_type=payload.source_type,
        source_ref=source_ref,
        target_language=payload.target_language,
        automation_config=payload.automation_config,
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


@router.get("/{project_id}/image-models")
def list_image_models(project_id: UUID, db: DbDep) -> list[ImageModelRead]:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    try:
        provider = parse_image_provider(project.automation_config)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if provider == "openai":
        labels = {"gpt-image-2": "GPT Image 2", "gpt-image-1-mini": "GPT Image 1 Mini"}
        return [ImageModelRead(id=model, name=labels.get(model, model)) for model in OPENAI_IMAGE_MODELS]
    from app.providers.higgsfield_client import HiggsfieldClient

    try:
        models = HiggsfieldClient().list_image_models()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"não foi possível listar modelos Higgsfield: {exc}",
        ) from exc
    return [ImageModelRead(id=model.id, name=model.name) for model in models]


@router.patch("/{project_id}/media-settings")
def patch_media_settings(
    project_id: UUID,
    payload: MediaSettingsPatch,
    db: DbDep,
) -> ProjectDetail:
    project = _detail_query(db, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.current_stage is not ProjectStage.SCENE_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="modelo de imagem só pode ser definido em scene_review",
        )
    config = dict(project.automation_config or {})
    if payload.image_model is not None:
        config["image_model"] = payload.image_model
    if payload.image_quality is not None:
        config["image_quality"] = payload.image_quality
    try:
        project.automation_config = normalize_automation_config(config)
        flag_modified(project, "automation_config")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
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
