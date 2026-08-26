from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.core.project_cost import project_cost_breakdown
from app.providers.pricing import (
    HIGGSFIELD_IMAGE_USD,
    add_project_llm_cost,
    add_usd,
    as_usd,
    estimate_elevenlabs_cost_usd,
    estimate_higgsfield_cost_usd,
    estimate_llm_cost_usd,
    unpack_priced_text,
)


def test_as_usd_quantizes_to_micros():
    assert as_usd("0.041") == Decimal("0.041000")
    assert as_usd(None) == Decimal("0")


def test_estimate_llm_cost_uses_published_rates():
    cost = estimate_llm_cost_usd("gpt-4o-mini", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert cost == Decimal("0.750000")
    nano = estimate_llm_cost_usd("gpt-5-nano", prompt_tokens=1_000_000, completion_tokens=0)
    assert nano == Decimal("0.050000")


def test_estimate_elevenlabs_cost_from_character_count():
    assert estimate_elevenlabs_cost_usd("abcd") == Decimal("0.001200")
    assert estimate_elevenlabs_cost_usd("") == Decimal("0")


def test_estimate_higgsfield_prefers_payload_then_fallback():
    assert estimate_higgsfield_cost_usd({"cost_usd": 0.12}) == Decimal("0.120000")
    assert estimate_higgsfield_cost_usd({}) == as_usd(HIGGSFIELD_IMAGE_USD)


def test_add_project_llm_cost_accumulates():
    project = SimpleNamespace()
    add_project_llm_cost(project, "0.01")
    add_project_llm_cost(project, "0.02")
    assert project.llm_cost_usd == Decimal("0.030000")


def test_unpack_priced_text_accepts_str_mocks():
    text, cost = unpack_priced_text("hello")
    assert text == "hello"
    assert cost == Decimal("0")


def test_project_cost_breakdown_sums_all_buckets():
    pid = uuid4()
    project = SimpleNamespace(
        id=pid,
        llm_cost_usd=Decimal("0.010000"),
        scenes=[SimpleNamespace(cost_usd=Decimal("0.041000")), SimpleNamespace(cost_usd=None)],
        audio_tracks=[SimpleNamespace(cost_usd=Decimal("0.003000"))],
        descriptions=[SimpleNamespace(cost_usd=Decimal("0.002000"))],
        thumbnails=[SimpleNamespace(cost_usd=Decimal("0.041000"))],
    )
    payload = project_cost_breakdown(project)
    assert payload["project_id"] == pid
    assert payload["scenes_usd"] == Decimal("0.041000")
    assert payload["audio_tracks_usd"] == Decimal("0.003000")
    assert payload["descriptions_usd"] == Decimal("0.002000")
    assert payload["thumbnails_usd"] == Decimal("0.041000")
    assert payload["llm_usd"] == Decimal("0.010000")
    assert payload["total_usd"] == add_usd("0.041", "0.003", "0.002", "0.041", "0.010")


def test_build_cost_series_pads_daily_and_monthly_windows():
    from datetime import date, datetime, timedelta, timezone

    from app.core.project_cost import DAILY_WINDOW_DAYS, MONTHLY_WINDOW_MONTHS, build_cost_series

    now = datetime(2026, 8, 25, 21, 0, tzinfo=timezone(timedelta(hours=-3)))
    series = build_cost_series(
        [
            (date(2026, 8, 25), Decimal("0.10")),
            (date(2026, 7, 1), Decimal("1.00")),
        ],
        now=now,
    )
    assert series["timezone"] == "America/Sao_Paulo"
    assert series["total_usd"] == Decimal("1.100000")
    assert len(series["daily"]) == DAILY_WINDOW_DAYS
    assert series["daily"][-1]["period"] == "2026-08-25"
    assert series["daily"][-1]["total_usd"] == Decimal("0.100000")
    assert series["daily"][0]["period"] == "2026-07-27"
    assert series["daily"][0]["total_usd"] == Decimal("0")
    assert len(series["monthly"]) == MONTHLY_WINDOW_MONTHS
    assert series["monthly"][-1]["period"] == "2026-08"
    assert series["monthly"][-1]["total_usd"] == Decimal("0.100000")
    assert series["monthly"][-2]["period"] == "2026-07"
    assert series["monthly"][-2]["total_usd"] == Decimal("1.000000")


def test_daily_cost_sql_unions_tables_and_groups_by_day():
    from sqlalchemy.dialects import postgresql

    from app.core.project_cost import daily_cost_totals_stmt

    sql = str(daily_cost_totals_stmt().compile(dialect=postgresql.dialect())).lower()
    assert "union all" in sql
    assert "date_trunc" in sql
    assert "group by" in sql
    assert "scenes" in sql
    assert "audio_tracks" in sql
    assert "descriptions" in sql
    assert "thumbnails" in sql
    assert "llm_cost_usd" in sql


def test_load_cost_series_uses_grouped_query_rows():
    from datetime import datetime, timedelta, timezone

    from app.core.project_cost import load_cost_series

    class FakeResult:
        def all(self):
            return [SimpleNamespace(period=datetime(2026, 8, 25), total_usd=Decimal("0.5"))]

    class FakeDB:
        def execute(self, _stmt):
            return FakeResult()

    now = datetime(2026, 8, 25, tzinfo=timezone(timedelta(hours=-3)))
    series = load_cost_series(FakeDB(), now=now)
    assert series["daily"][-1]["total_usd"] == Decimal("0.500000")
    assert series["total_usd"] == Decimal("0.500000")
