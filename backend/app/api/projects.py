from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.db import get_db
from app.models.enums import JobStatus, ProjectStage, ProjectStatus
from app.models.job import Job
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectRead

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[Project]:
    return list(db.scalars(select(Project).order_by(Project.created_at.desc())).all())


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> Project:
    project = Project(
        title=payload.title,
        source_type=payload.source_type,
        source_ref=payload.source_ref,
        target_language=payload.target_language,
        current_stage=ProjectStage.INGEST,
        status=ProjectStatus.PENDING,
    )
    db.add(project)
    db.flush()

    job = Job(
        project_id=project.id,
        stage=ProjectStage.INGEST,
        job_type="run_pipeline",
        status=JobStatus.PENDING,
        payload={"source_type": payload.source_type.value, "source_ref": payload.source_ref},
    )
    db.add(job)
    db.commit()
    db.refresh(project)
    celery_app.send_task("scenecraft.run_pipeline", args=[str(job.id)])
    return project


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: UUID, db: Session = Depends(get_db)) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project
