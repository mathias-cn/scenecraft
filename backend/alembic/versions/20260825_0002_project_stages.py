"""replace project_stage enum and add paused_for_review

Revision ID: 20260825_0002
Revises: 20260825_0001
Create Date: 2026-08-25

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260825_0002"
down_revision: Union[str, None] = "20260825_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_STAGES = (
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
    "ready_to_publish",
    "uploading",
    "published",
    "failed",
)

OLD_STAGES = (
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
)

_UP_MAP = """
CASE {col}::text
  WHEN 'ingest' THEN 'created'
  WHEN 'transcribe' THEN 'transcribing'
  WHEN 'translate' THEN 'transcript_review'
  WHEN 'scene' THEN 'scene_planning'
  WHEN 'audio' THEN 'audio_stage'
  WHEN 'assemble' THEN 'rendering'
  WHEN 'thumbnail' THEN 'thumbnail_stage'
  WHEN 'describe' THEN 'description_stage'
  WHEN 'upload' THEN 'uploading'
  WHEN 'complete' THEN 'published'
  ELSE 'created'
END
"""

_DOWN_MAP = """
CASE {col}::text
  WHEN 'created' THEN 'ingest'
  WHEN 'transcribing' THEN 'transcribe'
  WHEN 'transcript_review' THEN 'translate'
  WHEN 'scene_planning' THEN 'scene'
  WHEN 'scene_review' THEN 'scene'
  WHEN 'generating_media' THEN 'scene'
  WHEN 'media_review' THEN 'scene'
  WHEN 'audio_stage' THEN 'audio'
  WHEN 'audio_review' THEN 'audio'
  WHEN 'rendering' THEN 'assemble'
  WHEN 'render_review' THEN 'assemble'
  WHEN 'thumbnail_stage' THEN 'thumbnail'
  WHEN 'description_stage' THEN 'describe'
  WHEN 'ready_to_publish' THEN 'describe'
  WHEN 'uploading' THEN 'upload'
  WHEN 'published' THEN 'complete'
  WHEN 'failed' THEN 'ingest'
  ELSE 'ingest'
END
"""


def upgrade() -> None:
    op.execute("ALTER TYPE project_status ADD VALUE IF NOT EXISTS 'paused_for_review'")

    bind = op.get_bind()
    postgresql.ENUM(*NEW_STAGES, name="project_stage_new").create(bind, checkfirst=True)
    op.execute("ALTER TABLE projects ALTER COLUMN current_stage DROP DEFAULT")
    op.execute(
        f"ALTER TABLE projects ALTER COLUMN current_stage TYPE project_stage_new "
        f"USING ({_UP_MAP.format(col='current_stage')})::project_stage_new"
    )
    op.execute(
        f"ALTER TABLE jobs ALTER COLUMN stage TYPE project_stage_new "
        f"USING ({_UP_MAP.format(col='stage')})::project_stage_new"
    )
    op.execute("DROP TYPE project_stage")
    op.execute("ALTER TYPE project_stage_new RENAME TO project_stage")
    op.execute("ALTER TABLE projects ALTER COLUMN current_stage SET DEFAULT 'created'::project_stage")


def downgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM(*OLD_STAGES, name="project_stage_old").create(bind, checkfirst=True)
    op.execute("ALTER TABLE projects ALTER COLUMN current_stage DROP DEFAULT")
    op.execute(
        f"ALTER TABLE projects ALTER COLUMN current_stage TYPE project_stage_old "
        f"USING ({_DOWN_MAP.format(col='current_stage')})::project_stage_old"
    )
    op.execute(
        f"ALTER TABLE jobs ALTER COLUMN stage TYPE project_stage_old "
        f"USING ({_DOWN_MAP.format(col='stage')})::project_stage_old"
    )
    op.execute("DROP TYPE project_stage")
    op.execute("ALTER TYPE project_stage_old RENAME TO project_stage")
    op.execute("ALTER TABLE projects ALTER COLUMN current_stage SET DEFAULT 'ingest'::project_stage")
