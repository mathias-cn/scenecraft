"""Agrupamento de jobs (ex.: todas as cenas de um projeto)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.enums import JobStatus
from app.models.job import Job

TERMINAL_STATUSES = frozenset({JobStatus.SUCCEEDED, JobStatus.FAILED})
IN_FLIGHT_STATUSES = frozenset({JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRYING})


@dataclass(frozen=True)
class JobGroupResult:
    project_id: UUID
    job_group_id: UUID
    complete: bool
    total: int
    succeeded: int
    failed: int
    in_flight: int
    all_succeeded: bool

    @property
    def retries_exhausted_failures(self) -> bool:
        """Grupo encerrado com pelo menos um failed (retries já esgotados)."""
        return self.complete and self.failed > 0


def evaluate_job_group(
    project_id: UUID,
    job_group_id: UUID,
    statuses: list[JobStatus],
) -> JobGroupResult:
    total = len(statuses)
    succeeded = sum(1 for status in statuses if status == JobStatus.SUCCEEDED)
    failed = sum(1 for status in statuses if status == JobStatus.FAILED)
    in_flight = sum(1 for status in statuses if status not in TERMINAL_STATUSES)
    complete = total > 0 and in_flight == 0
    return JobGroupResult(
        project_id=project_id,
        job_group_id=job_group_id,
        complete=complete,
        total=total,
        succeeded=succeeded,
        failed=failed,
        in_flight=in_flight,
        all_succeeded=complete and failed == 0 and succeeded == total,
    )


def inspect_job_group(
    project_id: UUID | str,
    job_group_id: UUID | str,
    db: Session | None = None,
) -> JobGroupResult:
    """Lê os jobs do grupo e devolve contagens + se o grupo já é terminal."""
    pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
    gid = job_group_id if isinstance(job_group_id, UUID) else UUID(str(job_group_id))

    owns = False
    if db is None:
        from app.db import SessionLocal

        db = SessionLocal()
        owns = True
    try:
        jobs = list(
            db.scalars(
                select(Job).where(
                    Job.project_id == pid,
                    or_(Job.job_group_id == gid, Job.id == gid),
                )
            ).all()
        )
        return evaluate_job_group(pid, gid, [job.status for job in jobs])
    finally:
        if owns:
            db.close()


def check_job_group_complete(
    project_id: UUID | str,
    job_group_id: UUID | str,
    db: Session | None = None,
) -> bool:
    """True quando todos os jobs do grupo terminaram (succeeded ou failed após retries)."""
    return inspect_job_group(project_id, job_group_id, db=db).complete


def settle_job_group(db: Session, job: Job, project) -> JobGroupResult | None:
    """Avança o pipeline só quando 100% do grupo é terminal; falha o projeto se houver failed."""
    if project is None:
        return None
    group_id = job.job_group_id or job.id
    group = inspect_job_group(project.id, group_id, db=db)
    if not group.complete:
        return group
    from app.core.state_machine import IllegalTransition, advance_stage, fail_project

    try:
        if group.all_succeeded:
            advance_stage(project.id, job.stage, db=db)
        else:
            fail_project(db, project, job.error or "job group failed after retries")
    except IllegalTransition:
        pass
    return group
