from datetime import datetime
from zoneinfo import ZoneInfo

from trend_system.timezones import market_window
from trend_system.trade_timeline import trade_timeline_items


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

    assert {item.strategy_key for item in items} == {"next_session"}
    assert any("下个美股交易日" in item.action("zh") for item in items)
