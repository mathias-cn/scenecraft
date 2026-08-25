from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.style_links import STYLE_IN_USE_MESSAGE, scene_style_matches, style_is_in_use
from app.models.enums import SourceType
from app.schemas.project import MediaSettingsPatch, ProjectCreate
from app.schemas.style import StyleCreate, StylePatch


class FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class FakeDB:
    def __init__(self, configs, *, characters=False, character_hit=False):
        self.configs = configs
        self.characters = characters
        self.character_hit = character_hit

    def scalars(self, _stmt):
        return FakeScalars(self.configs)

    def get_bind(self):
        return object() if self.characters else None

    def execute(self, _stmt, _params=None):
        return SimpleNamespace(first=lambda: (1,) if self.character_hit else None)


def test_style_create_normalizes_slug():
    payload = StyleCreate(name="  Ilustração digital ", slug="Ilustracao-Digital")
    assert payload.name == "Ilustração digital"
    assert payload.slug == "ilustracao-digital"


def test_style_create_rejects_bad_slug():
    with pytest.raises(ValidationError, match="slug"):
        StyleCreate(name="X", slug="Não válido")


def test_style_patch_requires_active():
    assert StylePatch(active=False).active is False


def test_scene_style_matches_slug_or_id():
    sid = str(uuid4())
    assert scene_style_matches({"scene_style": "anime"}, slug="anime", style_id=sid)
    assert scene_style_matches({"scene_style": sid}, slug="anime", style_id=sid)
    assert not scene_style_matches({"scene_style": "cartoon"}, slug="anime", style_id=sid)
    assert not scene_style_matches({}, slug="anime", style_id=sid)


def test_style_in_use_via_project_config():
    style = SimpleNamespace(id=uuid4(), slug="anime")
    db = FakeDB([{"scene_style": "anime"}])
    assert style_is_in_use(db, style) is True
    db_free = FakeDB([{"scene_style": "fotorrealista"}])
    assert style_is_in_use(db_free, style) is False


def test_style_in_use_via_character(monkeypatch):
    class FakeInspect:
        def __init__(self, _bind):
            pass

        def has_table(self, _name):
            return True

    monkeypatch.setattr("app.core.style_links.inspect", FakeInspect)
    style = SimpleNamespace(id=uuid4(), slug="anime")
    db = FakeDB([{}], characters=True, character_hit=True)
    assert style_is_in_use(db, style) is True


def test_in_use_message():
    assert STYLE_IN_USE_MESSAGE == (
        "Este estilo está em uso e não pode ser excluído, apenas desativado"
    )


def test_project_create_keeps_scene_style():
    payload = ProjectCreate(
        title="clip",
        source_type=SourceType.YOUTUBE_LINK,
        source_ref="https://youtu.be/x",
        automation_config={"scene_style": "  anime  "},
    )
    assert payload.automation_config["scene_style"] == "anime"


def test_media_settings_patch_accepts_scene_style():
    assert MediaSettingsPatch(scene_style="fotorrealista").scene_style == "fotorrealista"
