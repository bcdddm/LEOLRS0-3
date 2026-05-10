from types import SimpleNamespace

import pandas as pd

from trend_system.portfolio import Allocation
from trend_system.report import daily_report
from trend_system.signals import Signal


def test_daily_report_ma_label_follows_configured_windows(monkeypatch):
    def fake_market_window(settings_raw: dict, market: str) -> SimpleNamespace:
        return SimpleNamespace(
            relevant_local_trading_window=lambda now: (
                pd.Timestamp("2026-01-02 09:30").to_pydatetime(),
                pd.Timestamp("2026-01-02 16:00").to_pydatetime(),
            )
        )

    monkeypatch.setattr("trend_system.report.market_window", fake_market_window)
    signal = Signal(
        date=pd.Timestamp("2026-01-02"),
        price=100.0,
        ma_short=98.0,
        ma_medium=95.0,
        ma_long=90.0,
        trend_label="allowed",
        trend_exposure=60.0,
        vix=16.0,
        vix_label="low",
        vix_multiplier=1.0,
        target_exposure=60.0,
    )
    allocation = Allocation(
        core_asset="VOO",
        core_percent=60.0,
        leveraged_asset=None,
        leveraged_percent=0.0,
        defensive_asset="SGOV",
        defensive_percent=40.0,
        equivalent_exposure=60.0,
        notes=[],
    )
    settings = {
        "profile": {"name": "Test", "home_timezone": "Pacific/Auckland"},
        "trend": {"short_window": 10, "medium_window": 40, "long_window": 120},
    }

    report = daily_report(signal, allocation, settings)

    assert "- MA10/40/120: 98.00 / 95.00 / 90.00" in report
    assert "MA20/50/200" not in report
