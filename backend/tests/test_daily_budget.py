from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.daily_budget import (
    DailyCostLimitReached,
    assert_paid_job_allowed,
    daily_budget_snapshot,
    is_paid_stage,
)
from app.models.enums import ProjectStage


def test_paid_stages_exclude_render():
    assert is_paid_stage(ProjectStage.TRANSCRIBING)
    assert is_paid_stage(ProjectStage.GENERATING_MEDIA)
    assert is_paid_stage(ProjectStage.DESCRIPTION_STAGE)
    assert not is_paid_stage(ProjectStage.RENDERING)
    assert not is_paid_stage(ProjectStage.COMPLETED)


def test_assert_skips_query_when_limit_disabled(monkeypatch):
    monkeypatch.setattr("app.core.daily_budget.configured_daily_limit_usd", lambda: None)

    def boom(_db):
        raise AssertionError("não deve consultar o gasto do dia sem teto")

    monkeypatch.setattr("app.core.daily_budget.load_today_cost", boom)
    assert_paid_job_allowed(SimpleNamespace())


def test_assert_skips_unpaid_stage_even_when_over_limit(monkeypatch):
    monkeypatch.setattr("app.core.daily_budget.configured_daily_limit_usd", lambda: Decimal("1"))
    monkeypatch.setattr("app.core.daily_budget.load_today_cost", lambda _db, **_k: Decimal("9"))
    assert_paid_job_allowed(SimpleNamespace(), ProjectStage.RENDERING)


def test_assert_raises_when_today_meets_limit(monkeypatch):
    monkeypatch.setattr("app.core.daily_budget.configured_daily_limit_usd", lambda: Decimal("1.00"))
    monkeypatch.setattr("app.core.daily_budget.load_today_cost", lambda _db, **_k: Decimal("1.00"))
    with pytest.raises(DailyCostLimitReached, match="Limite diário"):
        assert_paid_job_allowed(SimpleNamespace(), ProjectStage.SCENE_PLANNING)


def test_snapshot_marks_limit_reached(monkeypatch):
    monkeypatch.setattr("app.core.daily_budget.configured_daily_limit_usd", lambda: Decimal("2.50"))
    monkeypatch.setattr("app.core.daily_budget.load_today_cost", lambda _db, **_k: Decimal("3.00"))
    snap = daily_budget_snapshot(SimpleNamespace())
    assert snap["limit_reached"] is True
    assert snap["today_usd"] == Decimal("3.000000")
    assert snap["daily_limit_usd"] == Decimal("2.500000")
