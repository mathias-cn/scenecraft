from uuid import uuid4

from app.storage import object_key, public_url, relative_object_key, versioned_filename


def test_object_key_is_relative_to_bucket_without_bucket_name(monkeypatch):
    monkeypatch.setattr("app.storage.settings.s3_bucket", "scenecraft-media")
    character_id = uuid4()
    key = object_key(f"characters/{character_id}", "base.png")
    assert key == f"characters/{character_id}/base.png"
    assert not key.startswith("scenecraft-media/")
    assert "scenecraft-media" not in key.split("/")


def test_object_key_strips_accidental_bucket_prefix(monkeypatch):
    monkeypatch.setattr("app.storage.settings.s3_bucket", "scenecraft-media")
    key = object_key("scenecraft-media/characters/abc", "base.png")
    assert key == "characters/abc/base.png"


def test_public_url_uses_cdn_without_bucket_name(monkeypatch):
    monkeypatch.setattr("app.storage.settings.r2_public_base_url", "https://cdn.mazting.studio")
    monkeypatch.setattr("app.storage.settings.s3_bucket", "scenecraft-media")
    character_id = uuid4()
    key = object_key(f"characters/{character_id}", "base.png")
    url = public_url(key)
    assert url == f"https://cdn.mazting.studio/characters/{character_id}/base.png"
    assert "scenecraft-media" not in url


def test_public_url_strips_bucket_prefixed_key(monkeypatch):
    monkeypatch.setattr("app.storage.settings.r2_public_base_url", "https://cdn.mazting.studio/")
    monkeypatch.setattr("app.storage.settings.s3_bucket", "scenecraft-media")
    url = public_url("scenecraft-media/characters/abc/base.png")
    assert url == "https://cdn.mazting.studio/characters/abc/base.png"


def test_relative_object_key_leaves_normal_paths(monkeypatch):
    monkeypatch.setattr("app.storage.settings.s3_bucket", "scenecraft-media")
    assert relative_object_key("characters/abc/base.png") == "characters/abc/base.png"


def test_versioned_filename_is_unique_per_call():
    first = versioned_filename("base")
    second = versioned_filename("base")
    assert first.startswith("base_")
    assert first.endswith(".png")
    assert first != second
    assert versioned_filename("scene_0001") != versioned_filename("scene_0001")
    jpeg = versioned_filename("cover", ".JPG")
    assert jpeg.startswith("cover_")
    assert jpeg.endswith(".jpg")
