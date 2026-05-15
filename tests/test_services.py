from __future__ import annotations

from pathlib import Path

import pandas as pd

from trend_system.config import load_settings
from trend_system.models import BacktestRequest, DailySignalRequest, HealthcheckRequest
from trend_system.services.backtest_service import run_backtest_use_case
from trend_system.services.daily_signal_service import run_daily_signal
from trend_system.services.healthcheck_service import run_healthcheck


def _fake_price_loader(symbols: list[str], start, end=None, *, auto_adjust=True):
    del start, end, auto_adjust
    dates = pd.date_range("2025-01-01", periods=260, freq="B")
    prices: dict[str, pd.DataFrame] = {}
    for index, symbol in enumerate(symbols):
        base = 100 + index * 5
        series = pd.Series(range(len(dates)), index=dates, dtype=float)
        close = base + series
        prices[symbol] = pd.DataFrame({"Close": close})
    return prices


def test_run_daily_signal_returns_report_and_signal():
    settings = load_settings("config/settings.toml")

    result = run_daily_signal(
        DailySignalRequest(settings=settings, start="2025-01-01"),
        price_loader=_fake_price_loader,
    )

    assert result.report
    assert result.signal.date is not None
    assert result.allocation.equivalent_exposure >= 0.0


def test_run_backtest_use_case_can_write_outputs(tmp_path: Path):
    settings = load_settings("config/settings.toml")
    output = tmp_path / "equity.csv"
    trades_output = tmp_path / "trades.csv"

    result = run_backtest_use_case(
        BacktestRequest(
            settings=settings,
            start="2025-01-01",
            end="2025-12-31",
            output=output,
            trades_output=trades_output,
        ),
        price_loader=_fake_price_loader,
    )

    assert output.exists()
    assert trades_output.exists()
    assert not result.result.equity_curve.empty


def test_run_healthcheck_returns_market_health_summary():
    settings = load_settings("config/settings.toml")

    result = run_healthcheck(
        HealthcheckRequest(settings=settings, start="2025-01-01"),
        price_loader=_fake_price_loader,
    )

    assert result.symbol == settings.primary_symbol
    assert result.latest_price > 0.0
    assert result.stage in {"warning", "recovery", "neutral"}
