"""initial schema

Revision ID: 20260825_0001
Revises:
Create Date: 2026-08-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260825_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ENUMS: dict[str, tuple[str, ...]] = {
    "source_type": ("youtube_link", "upload_video", "upload_audio"),
    "project_stage": (
        "ingest",
        "transcribe",
        "translate",
        "scene",
        "audio",
        "assemble",
        "thumbnail",
        "describe",
        "upload",
        "complete",
    ),
    "project_status": ("pending", "running", "completed", "failed", "cancelled"),
    "media_type": ("image", "video"),
    "scene_status": ("pending", "generating", "completed", "failed"),
    "audio_track_source": ("original", "generated"),
    "assembly_status": ("pending", "rendering", "completed", "failed"),
    "thumbnail_source": ("generated", "uploaded"),
    "description_source": ("generated", "manual"),
    "youtube_upload_status": ("pending", "uploading", "published", "failed"),
    "job_status": ("pending", "running", "completed", "failed"),
}


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("source_type", _enum("source_type"), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("target_language", sa.String(length=16), nullable=False),
        sa.Column(
            "automation_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "current_stage",
            _enum("project_stage"),
            server_default=sa.text("'ingest'::project_stage"),
            nullable=False,
        ),
        sa.Column(
            "status",
            _enum("project_status"),
            server_default=sa.text("'pending'::project_status"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "transcript_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text_original", sa.Text(), nullable=False),
        sa.Column("text_translated", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "index", name="uq_transcript_segments_project_index"),
    )
    op.create_index("ix_transcript_segments_project_id", "transcript_segments", ["project_id"])

    op.create_table(
        "scenes",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column(
            "source_segment_ids",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{}'::integer[]"),
            nullable=False,
        ),
        sa.Column("visual_prompt", sa.Text(), nullable=False),
        sa.Column("media_type", _enum("media_type"), nullable=False),
        sa.Column("style", sa.String(length=100), nullable=True),
        sa.Column("media_url", sa.Text(), nullable=True),
        sa.Column("generation_provider", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            _enum("scene_status"),
            server_default=sa.text("'pending'::scene_status"),
            nullable=False,
        ),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "index", name="uq_scenes_project_index"),
    )
    op.create_index("ix_scenes_project_id", "scenes", ["project_id"])

    op.create_table(
        "audio_tracks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", _enum("audio_track_source"), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("voice_id", sa.String(length=128), nullable=True),
        sa.Column("file_url", sa.Text(), nullable=True),
        sa.Column("word_timestamps", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audio_tracks_project_id", "audio_tracks", ["project_id"])

    op.create_table(
        "video_assembly",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ffmpeg_job_id", sa.String(length=128), nullable=True),
        sa.Column("output_url", sa.Text(), nullable=True),
        sa.Column(
            "status",
            _enum("assembly_status"),
            server_default=sa.text("'pending'::assembly_status"),
            nullable=False,
        ),
        sa.Column("render_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_assembly_project_id", "video_assembly", ["project_id"])

    op.create_table(
        "thumbnails",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", _enum("thumbnail_source"), nullable=False),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_thumbnails_project_id", "thumbnails", ["project_id"])

    op.create_table(
        "descriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source", _enum("description_source"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_descriptions_project_id", "descriptions", ["project_id"])

    op.create_table(
        "youtube_uploads",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("youtube_video_id", sa.String(length=32), nullable=True),
        sa.Column(
            "status",
            _enum("youtube_upload_status"),
            server_default=sa.text("'pending'::youtube_upload_status"),
            nullable=False,
        ),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_youtube_uploads_project_id", "youtube_uploads", ["project_id"])

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", _enum("project_stage"), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            _enum("job_status"),
            server_default=sa.text("'pending'::job_status"),
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jobs_project_id", "jobs", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_project_id", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_youtube_uploads_project_id", table_name="youtube_uploads")
    op.drop_table("youtube_uploads")
    op.drop_index("ix_descriptions_project_id", table_name="descriptions")
    op.drop_table("descriptions")
    op.drop_index("ix_thumbnails_project_id", table_name="thumbnails")
    op.drop_table("thumbnails")
    op.drop_index("ix_video_assembly_project_id", table_name="video_assembly")
    op.drop_table("video_assembly")
    op.drop_index("ix_audio_tracks_project_id", table_name="audio_tracks")
    op.drop_table("audio_tracks")
    op.drop_index("ix_scenes_project_id", table_name="scenes")
    op.drop_table("scenes")
    op.drop_index("ix_transcript_segments_project_id", table_name="transcript_segments")
    op.drop_table("transcript_segments")
    op.drop_table("projects")

    bind = op.get_bind()
    for name, values in reversed(list(ENUMS.items())):
        postgresql.ENUM(*values, name=name).drop(bind, checkfirst=True)
