from types import SimpleNamespace
from uuid import uuid4

from app.core.plan_scenes import plan_project_scenes
from app.models.character import Character
from app.models.enums import CharacterStatus, MediaType, SceneStatus
from app.models.project import Project
from app.models.scene import Scene
from app.models.style import Style


class FakeDB:
    def __init__(self, project, rows=None):
        self.project = project
        self.rows = list(rows or [])
        self.added = []
        self.executed = []

    def get(self, model, pid):
        if model is Project:
            return self.project if self.project.id == pid else None
        for row in self.rows:
            if getattr(row, "_model", None) is model and row.id == pid:
                return row
        return None

    def execute(self, statement):
        self.executed.append(statement)
        return None

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        return None

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


def test_plan_project_scenes_enriches_visual_prompt_with_character(monkeypatch):
    style = SimpleNamespace(id=uuid4(), name="Anime", slug="anime", _model=Style)
    character = SimpleNamespace(
        id=uuid4(),
        description_prompt="heroína de casaco vermelho",
        style_id=style.id,
        status=CharacterStatus.APPROVED,
        base_image_url="https://cdn.example.com/base.png",
        _model=Character,
    )
    project = SimpleNamespace(
        id=uuid4(),
        target_language="pt-BR",
        automation_config={
            "character_id": str(character.id),
            "scene_style_id": str(style.id),
        },
        transcript_segments=[
            SimpleNamespace(
                index=0,
                start_ms=0,
                end_ms=1200,
                text_original="olá",
                text_translated=None,
            )
        ],
    )
    db = FakeDB(project, [style, character])

    def fake_plan_scenes(segments, **kwargs):
        assert kwargs["character_description"] == "heroína de casaco vermelho"
        assert kwargs["style_name"] == "Anime"
        assert segments[0]["text_original"] == "olá"
        return [
            {
                "index": 0,
                "start_ms": 0,
                "end_ms": 1200,
                "source_segment_ids": [0],
                "visual_prompt": "Wide shot of a rainy street at night",
            }
        ]

    monkeypatch.setattr("app.core.plan_scenes.plan_scenes", fake_plan_scenes)
    result = plan_project_scenes(project.id, db=db)
    assert result["scene_count"] == 1
    assert db.executed
    scene = db.added[0]
    assert isinstance(scene, Scene)
    assert scene.media_type is MediaType.IMAGE
    assert scene.status is SceneStatus.PENDING
    assert "heroína de casaco vermelho" in scene.visual_prompt
    assert "Anime" in scene.visual_prompt
    assert scene.style is None
