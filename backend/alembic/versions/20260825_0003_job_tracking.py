"""initial job tracking statuses and job_group_id

Revision ID: 20260825_0003
Revises: 20260825_0002
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260825_0003"
down_revision: Union[str, None] = "20260825_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'queued'")
        op.execute("ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'succeeded'")
        op.execute("ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'retrying'")

    op.execute("UPDATE jobs SET status = 'queued' WHERE status = 'pending'")
    op.execute("UPDATE jobs SET status = 'succeeded' WHERE status = 'completed'")
    op.execute("ALTER TABLE jobs ALTER COLUMN status SET DEFAULT 'queued'")
    op.add_column("jobs", sa.Column("job_group_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_jobs_job_group_id", "jobs", ["job_group_id"])
    op.create_index("ix_jobs_project_id_job_group_id", "jobs", ["project_id", "job_group_id"])
    op.execute("UPDATE jobs SET job_group_id = id WHERE job_group_id IS NULL")


def downgrade() -> None:
    op.execute("UPDATE jobs SET status = 'pending' WHERE status = 'queued'")
    op.execute("UPDATE jobs SET status = 'completed' WHERE status = 'succeeded'")
    op.execute("ALTER TABLE jobs ALTER COLUMN status SET DEFAULT 'pending'")
    op.drop_index("ix_jobs_project_id_job_group_id", table_name="jobs")
    op.drop_index("ix_jobs_job_group_id", table_name="jobs")
    op.drop_column("jobs", "job_group_id")
