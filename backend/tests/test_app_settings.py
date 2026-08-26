from decimal import Decimal

from app.core.app_settings import (
    DAILY_COST_LIMIT_KEY,
    load_daily_cost_limit_usd,
    parse_daily_limit,
    save_daily_cost_limit_usd,
)
from app.models.app_setting import AppSetting


class SettingsDB:
    def __init__(self):
        self.rows: dict[str, AppSetting] = {}

    def get(self, _model, key):
        return self.rows.get(key)

    def add(self, row):
        self.rows[row.key] = row

    def delete(self, row):
        self.rows.pop(row.key, None)


def test_parse_daily_limit_treats_blank_and_zero_as_disabled():
    assert parse_daily_limit(None) is None
    assert parse_daily_limit("") is None
    assert parse_daily_limit("0") is None
    assert parse_daily_limit("-1") is None
    assert parse_daily_limit("not-a-number") is None
    assert parse_daily_limit("12.5") == Decimal("12.500000")


def test_save_and_load_daily_cost_limit_roundtrip():
    db = SettingsDB()
    assert load_daily_cost_limit_usd(db) is None
    saved = save_daily_cost_limit_usd(db, Decimal("7.50"))
    assert saved == Decimal("7.500000")
    assert db.rows[DAILY_COST_LIMIT_KEY].value == "7.500000"
    assert load_daily_cost_limit_usd(db) == Decimal("7.500000")


def test_save_none_or_zero_removes_daily_limit():
    db = SettingsDB()
    save_daily_cost_limit_usd(db, Decimal("3"))
    assert DAILY_COST_LIMIT_KEY in db.rows
    save_daily_cost_limit_usd(db, None)
    assert DAILY_COST_LIMIT_KEY not in db.rows
    save_daily_cost_limit_usd(db, Decimal("3"))
    save_daily_cost_limit_usd(db, Decimal("0"))
    assert DAILY_COST_LIMIT_KEY not in db.rows
    assert load_daily_cost_limit_usd(db) is None
