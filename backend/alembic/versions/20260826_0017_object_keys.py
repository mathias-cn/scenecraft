"""store object keys instead of public CDN URLs

Revision ID: 20260826_0017
Revises: 20260826_0016
Create Date: 2026-08-26
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260826_0017"
down_revision: Union[str, Sequence[str], None] = "20260826_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TO_KEY = """
CREATE OR REPLACE FUNCTION tmp_scenecraft_object_key(value text)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  t text;
  path text;
BEGIN
  t := btrim(value);
  IF t IS NULL OR t = '' THEN
    RETURN t;
  END IF;
  t := split_part(split_part(t, '?', 1), '#', 1);
  IF t ~* '^https?://cdn\\.mazting\\.studio/' THEN
    path := regexp_replace(t, '^https?://cdn\\.mazting\\.studio/', '', 'i');
  ELSIF t ~* '^s3://' THEN
    path := regexp_replace(t, '^s3://[^/]+/', '');
  ELSIF t ~* '^https?://[^/]+\\.r2\\.cloudflarestorage\\.com/' THEN
    path := regexp_replace(t, '^https?://[^/]+\\.r2\\.cloudflarestorage\\.com/', '', 'i');
    IF path LIKE 'scenecraft-media/%' THEN
      path := substring(path from length('scenecraft-media/') + 1);
    END IF;
  ELSIF t LIKE 'scenecraft-media/%' THEN
    path := substring(t from length('scenecraft-media/') + 1);
  ELSE
    RETURN t;
  END IF;
  path := btrim(path, '/');
  RETURN NULLIF(path, '');
END;
$$;
"""

_DROP = "DROP FUNCTION IF EXISTS tmp_scenecraft_object_key(text);"

_UPDATES = [
    "UPDATE scenes SET media_url = tmp_scenecraft_object_key(media_url) WHERE media_url IS NOT NULL AND media_url <> ''",
    "UPDATE characters SET base_image_url = tmp_scenecraft_object_key(base_image_url) WHERE base_image_url IS NOT NULL AND base_image_url <> ''",
    "UPDATE characters SET reference_image_url = tmp_scenecraft_object_key(reference_image_url) WHERE reference_image_url IS NOT NULL AND reference_image_url <> '' AND reference_image_url ~* '^(https?://cdn\\.mazting\\.studio/|https?://[^/]+\\.r2\\.cloudflarestorage\\.com/|s3://)'",
    "UPDATE character_assets SET image_url = tmp_scenecraft_object_key(image_url) WHERE image_url <> ''",
    "UPDATE thumbnails SET file_url = tmp_scenecraft_object_key(file_url) WHERE file_url <> ''",
    "UPDATE video_assembly SET output_url = tmp_scenecraft_object_key(output_url) WHERE output_url IS NOT NULL AND output_url <> ''",
    "UPDATE audio_tracks SET file_url = tmp_scenecraft_object_key(file_url) WHERE file_url IS NOT NULL AND file_url <> ''",
]


def upgrade() -> None:
    op.execute(_TO_KEY)
    for statement in _UPDATES:
        op.execute(statement)
    op.execute(_DROP)


def downgrade() -> None:
    prefix = "https://cdn.mazting.studio/"
    for table, column, nullable in (
        ("scenes", "media_url", True),
        ("characters", "base_image_url", True),
        ("characters", "reference_image_url", True),
        ("character_assets", "image_url", False),
        ("thumbnails", "file_url", False),
        ("video_assembly", "output_url", True),
        ("audio_tracks", "file_url", True),
    ):
        where_null = "" if not nullable else f"AND {column} IS NOT NULL"
        op.execute(
            f"""
            UPDATE {table}
            SET {column} = '{prefix}' || {column}
            WHERE {column} <> '' {where_null}
              AND {column} NOT LIKE 'http%'
              AND {column} NOT LIKE 's3://%'
            """
        )
