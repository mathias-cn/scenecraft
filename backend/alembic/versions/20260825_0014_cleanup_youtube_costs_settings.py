"""drop youtube leftovers, unused stages, scenes.style; add cost + settings

Revision ID: 20260825_0014
Revises: 20260825_0013
Create Date: 2026-08-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260825_0014"
down_revision: Union[str, None] = "20260825_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KEEP_STAGES = (
    "created",
    "transcribing",
    "transcript_review",
    "scene_planning",
    "scene_review",
    "generating_media",
    "media_review",
    "audio_stage",
    "audio_review",
    "rendering",
    "render_review",
    "thumbnail_stage",
    "description_stage",
    "completed",
    "failed",
)

_COST = sa.Numeric(precision=12, scale=6)


def upgrade() -> None:
    op.execute(
        "UPDATE projects SET current_stage = 'completed' "
        "WHERE current_stage::text IN ('ready_to_publish', 'uploading', 'published')"
    )
    op.execute(
        "UPDATE projects SET status = 'completed' "
        "WHERE current_stage = 'completed' "
        "AND status::text NOT IN ('cancelled', 'failed')"
    )
    op.execute(
        "UPDATE jobs SET stage = 'completed' "
        "WHERE stage::text IN ('ready_to_publish', 'uploading', 'published')"
    )

    bind = op.get_bind()
    postgresql.ENUM(*KEEP_STAGES, name="project_stage_new").create(bind, checkfirst=True)
    op.execute("ALTER TABLE projects ALTER COLUMN current_stage DROP DEFAULT")
    op.execute(
        "ALTER TABLE projects ALTER COLUMN current_stage TYPE project_stage_new "
        "USING current_stage::text::project_stage_new"
    )
    op.execute(
        "ALTER TABLE jobs ALTER COLUMN stage TYPE project_stage_new "
        "USING stage::text::project_stage_new"
    )
    op.execute("DROP TYPE project_stage")
    op.execute("ALTER TYPE project_stage_new RENAME TO project_stage")
    op.execute(
        "ALTER TABLE projects ALTER COLUMN current_stage SET DEFAULT 'created'::project_stage"
    )

    op.drop_index("ix_youtube_uploads_project_id", table_name="youtube_uploads")
    op.drop_table("youtube_uploads")
    postgresql.ENUM(name="youtube_upload_status").drop(bind, checkfirst=True)

    op.drop_column("scenes", "style")

    op.add_column("characters", sa.Column("cost_usd", _COST, nullable=True))
    op.add_column("character_assets", sa.Column("cost_usd", _COST, nullable=True))

    op.create_table(
        "title_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("draft_title", sa.String(length=200), nullable=False),
        sa.Column("titles", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cost_usd", _COST, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_title_suggestions_draft_title", "title_suggestions", ["draft_title"])

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_index("ix_title_suggestions_draft_title", table_name="title_suggestions")
    op.drop_table("title_suggestions")
    op.drop_column("character_assets", "cost_usd")
    op.drop_column("characters", "cost_usd")
    op.add_column("scenes", sa.Column("style", sa.String(length=100), nullable=True))

    bind = op.get_bind()
    postgresql.ENUM(
        "pending", "uploading", "published", "failed",
        name="youtube_upload_status",
    ).create(bind, checkfirst=True)
    op.create_table(
        "youtube_uploads",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("youtube_video_id", sa.String(length=32), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending", "uploading", "published", "failed",
                name="youtube_upload_status",
                create_type=False,
            ),
            server_default=sa.text("'pending'::youtube_upload_status"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_youtube_uploads_project_id", "youtube_uploads", ["project_id"])

    old = KEEP_STAGES + ("ready_to_publish", "uploading", "published")
    postgresql.ENUM(*old, name="project_stage_old").create(bind, checkfirst=True)
    op.execute("ALTER TABLE projects ALTER COLUMN current_stage DROP DEFAULT")
    op.execute(
        "ALTER TABLE projects ALTER COLUMN current_stage TYPE project_stage_old "
        "USING current_stage::text::project_stage_old"
    )
    op.execute(
        "ALTER TABLE jobs ALTER COLUMN stage TYPE project_stage_old "
        "USING stage::text::project_stage_old"
    )
    op.execute("DROP TYPE project_stage")
    op.execute("ALTER TYPE project_stage_old RENAME TO project_stage")
    op.execute(
        "ALTER TABLE projects ALTER COLUMN current_stage SET DEFAULT 'created'::project_stage"
    )
