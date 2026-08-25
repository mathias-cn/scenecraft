from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.project_cast import ProjectCastError, apply_cast_to_config, enrich_visual_prompt
from app.core.style_links import scene_style_matches
from app.models.character import Character
from app.models.enums import CharacterStatus
from app.models.style import Style


class FakeDB:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def get(self, model, pid):
        for row in self.rows:
            if getattr(row, "_model", None) is model and row.id == pid:
                return row
        return None


def _style(**kwargs):
    values = dict(id=uuid4(), name="Anime", slug="anime", active=True, _model=Style)
    values.update(kwargs)
    values.setdefault("_model", Style)
    return SimpleNamespace(**values)


def _character(**kwargs):
    style_id = kwargs.pop("style_id", uuid4())
    values = dict(
        id=uuid4(),
        description_prompt="heroína de casaco vermelho",
        style_id=style_id,
        status=CharacterStatus.APPROVED,
        base_image_url="https://cdn.example.com/base.png",
        _model=Character,
    )
    values.update(kwargs)
    values.setdefault("_model", Character)
    return SimpleNamespace(**values)


def test_character_locks_scene_style():
    style = _style()
    other = _style(name="Cartoon", slug="cartoon")
    character = _character(style_id=style.id)
    db = FakeDB([style, other, character])
    config = apply_cast_to_config(
        db,
        {},
        character_id=character.id,
        scene_style_id=other.id,
    )
    assert config["character_id"] == str(character.id)
    assert config["scene_style_id"] == str(style.id)
    assert config["scene_style"] == "anime"


def test_scene_style_without_character():
    style = _style()
    db = FakeDB([style])
    config = apply_cast_to_config(db, {}, scene_style_id=style.id)
    assert "character_id" not in config
    assert config["scene_style_id"] == str(style.id)
    assert config["scene_style"] == "anime"


def test_unapproved_character_rejected():
    style = _style()
    character = _character(style_id=style.id, status=CharacterStatus.PENDING_APPROVAL)
    db = FakeDB([style, character])
    with pytest.raises(ProjectCastError, match="aprovado"):
        apply_cast_to_config(db, {}, character_id=character.id)


def test_missing_character_rejected():
    db = FakeDB([])
    with pytest.raises(ProjectCastError, match="não encontrado"):
        apply_cast_to_config(db, {}, character_id=uuid4())


def test_enrich_prompt_appends_character_and_style():
    character = _character()
    style = _style(name="Fotorrealista")
    prompt = enrich_visual_prompt("wide shot of a street", character=character, style=style)
    assert "heroína de casaco vermelho" in prompt
    assert "Fotorrealista" in prompt


def test_style_link_matches_scene_style_id():
    sid = str(uuid4())
    assert scene_style_matches({"scene_style_id": sid}, slug="anime", style_id=sid)
    assert scene_style_matches({"scene_style": "anime"}, slug="anime", style_id=sid)
    assert not scene_style_matches({"scene_style_id": str(uuid4())}, slug="anime", style_id=sid)
