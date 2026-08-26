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
