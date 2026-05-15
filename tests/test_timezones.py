from datetime import datetime
from zoneinfo import ZoneInfo

from trend_system.timezones import market_window
from trend_system.trade_timeline import (
    NEXT_SESSION_MODE,
    NZ_CLOSE_US_OPEN_MODE,
    trade_timeline_items,
)


def _settings(home_timezone: str) -> dict:
    return {
        "profile": {"home_timezone": home_timezone},
        "markets": {
            "us": {
                "timezone": "America/New_York",
                "regular_open": "09:30",
                "regular_close": "16:00",
            },
            "asx": {
                "timezone": "Australia/Sydney",
                "regular_open": "10:00",
                "regular_close": "16:00",
            },
            "nzx": {
                "timezone": "Pacific/Auckland",
                "regular_open": "10:00",
                "regular_close": "16:45",
            },
        },
    }


def test_us_market_window_skips_new_year_holiday():
    settings = _settings("America/New_York")
    now = datetime(2026, 1, 1, 12, 0, tzinfo=ZoneInfo("America/New_York"))

    open_dt, close_dt = market_window(settings, "us").relevant_local_trading_window(now)

    assert open_dt == datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo("America/New_York"))
    assert close_dt == datetime(2026, 1, 2, 16, 0, tzinfo=ZoneInfo("America/New_York"))


def test_asx_market_window_skips_weekend():
    settings = _settings("Australia/Sydney")
    now = datetime(2026, 1, 3, 12, 0, tzinfo=ZoneInfo("Australia/Sydney"))

    open_dt, close_dt = market_window(settings, "asx").relevant_local_trading_window(now)

    assert open_dt == datetime(2026, 1, 5, 10, 0, tzinfo=ZoneInfo("Australia/Sydney"))
    assert close_dt == datetime(2026, 1, 5, 16, 0, tzinfo=ZoneInfo("Australia/Sydney"))


def test_trade_timeline_lists_next_session_deadline():
    settings = _settings("Pacific/Auckland")
    now = datetime(2026, 1, 5, 12, 0, tzinfo=ZoneInfo("Pacific/Auckland"))

    items = trade_timeline_items(settings, now)

    assert {item.strategy_key for item in items} == {NEXT_SESSION_MODE, NZ_CLOSE_US_OPEN_MODE}
    assert any("下个美股交易日" in item.action("zh") for item in items)


def test_trade_timeline_orders_combined_mode_deadlines():
    settings = _settings("Pacific/Auckland")
    now = datetime(2026, 1, 5, 12, 0, tzinfo=ZoneInfo("Pacific/Auckland"))

    items = trade_timeline_items(settings, now)
    combined_mode_items = [item for item in items if item.strategy_key == NZ_CLOSE_US_OPEN_MODE]

    assert [item.market_label for item in combined_mode_items] == ["NZX", "US", "US"]
    assert combined_mode_items[0].action("zh").startswith("NZX 收盘前")
    assert combined_mode_items[1].action("zh").startswith("美股开盘前")
    assert combined_mode_items[2].action("zh").startswith("美股收盘前")
    assert combined_mode_items == sorted(combined_mode_items, key=lambda item: item.deadline)


def test_trade_timeline_exposes_localized_strategy_labels():
    settings = _settings("Pacific/Auckland")
    now = datetime(2026, 1, 5, 12, 0, tzinfo=ZoneInfo("Pacific/Auckland"))

    items = trade_timeline_items(settings, now)
    next_session = next(item for item in items if item.strategy_key == NEXT_SESSION_MODE)
    combined_mode = next(item for item in items if item.strategy_key == NZ_CLOSE_US_OPEN_MODE)

    assert next_session.strategy_label("zh") == "下一交易日"
    assert next_session.strategy_label("en") == "Next Session"
    assert combined_mode.strategy_label("zh") == "NZ 盘末 / 美股开盘"
    assert combined_mode.strategy_label("en") == "NZ Close / US Open"


def test_trade_timeline_can_filter_to_one_stable_mode():
    settings = _settings("Pacific/Auckland")
    now = datetime(2026, 1, 5, 12, 0, tzinfo=ZoneInfo("Pacific/Auckland"))

    items = trade_timeline_items(settings, now, strategy_keys={NEXT_SESSION_MODE})

    assert len(items) == 1
    assert items[0].strategy_key == NEXT_SESSION_MODE


def test_trade_timeline_invalid_filter_falls_back_to_safe_default():
    settings = _settings("Pacific/Auckland")
    now = datetime(2026, 1, 5, 12, 0, tzinfo=ZoneInfo("Pacific/Auckland"))

    items = trade_timeline_items(settings, now, strategy_keys={"unknown_mode"})

    assert len(items) == 1
    assert items[0].strategy_key == NEXT_SESSION_MODE
