import pandas as pd

from trend_system.backtest import (
    SWEEP_FACTORS,
    _metrics,
    build_parameter_sweep_candidate,
    run_backtest,
    run_parameter_sweep,
)


def test_backtest_includes_buy_and_hold_benchmark():
    dates = pd.bdate_range("2020-01-01", periods=420)
    price = pd.Series(range(100, 520), index=dates, dtype=float)
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 20,
            "medium_window": 50,
            "long_window": 200,
            "confirmation_days": 1,
            "exposure": {
                "below_long": 0.0,
                "above_long": 50.0,
                "medium_above_long": 80.0,
                "short_above_medium_above_long": 100.0,
            },
        },
        "position": {
            "min_exposure": 0.0,
            "max_exposure": 300.0,
            "rebalance_threshold": 0.0,
        },
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 1.2},
                {"label": "normal", "min_inclusive": 20.0, "max_exclusive": 30.0, "multiplier": 1.0},
            ]
        },
        "execution": {
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "SGOV",
            "leveraged_asset": "SPXL",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        },
        "backtest": {
            "initial_capital": 100000.0,
            "annual_cash_return": 0.0,
            "annual_leveraged_fee": 0.0,
            "signal_effective_next_day": True,
        },
    }

    result = run_backtest(price, vix, settings)

    assert "buy_hold_equity" in result.equity_curve.columns
    assert "leveraged_buy_hold_equity" in result.equity_curve.columns
    assert "ma120_timing_equity" in result.equity_curve.columns
    assert "buy_hold_cagr_pct" in result.metrics
    assert result.equity_curve["buy_hold_equity"].iloc[-1] > result.equity_curve["buy_hold_equity"].iloc[0]
    assert result.equity_curve["leveraged_buy_hold_equity"].iloc[-1] > result.equity_curve["buy_hold_equity"].iloc[-1]


def test_backtest_includes_leveraged_ma120_timing_hold_curve():
    dates = pd.to_datetime(
        ["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
    )
    price = pd.Series([100.0, 100.0, 90.0, 80.0, 110.0, 121.0], index=dates)
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 1,
            "medium_window": 1,
            "long_window": 1,
            "confirmation_days": 1,
            "exposure": {
                "below_long": 0.0,
                "above_long": 100.0,
                "medium_above_long": 100.0,
                "short_above_medium_above_long": 100.0,
            },
        },
        "position": {
            "min_exposure": 0.0,
            "max_exposure": 300.0,
            "rebalance_threshold": 0.0,
        },
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 1.0},
            ]
        },
        "execution": {
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "SGOV",
            "leveraged_asset": "SPXL",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        },
        "backtest": {
            "initial_capital": 100000.0,
            "annual_cash_return": 0.0,
            "annual_leveraged_fee": 0.0,
            "execution_timing": "next_session",
        },
    }

    result = run_backtest(price, vix, settings)

    assert "leveraged_ma120_timing_equity" in result.equity_curve.columns
    assert round(result.equity_curve["leveraged_ma120_timing_daily_return"].iloc[2], 6) == -0.3
    assert result.equity_curve["leveraged_ma120_timing_daily_return"].iloc[3] == 0.0
    assert result.equity_curve["leveraged_ma120_timing_daily_return"].iloc[4] == 0.0
    assert round(result.equity_curve["leveraged_ma120_timing_daily_return"].iloc[5], 6) == 0.3
    assert round(result.equity_curve["leveraged_ma120_timing_equity"].iloc[-1], 2) == 91000.0


def test_backtest_can_use_actual_leveraged_asset_returns():
    dates = pd.bdate_range("2020-01-01", periods=6)
    price = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0, 105.0], index=dates)
    leveraged_price = pd.Series([100.0, 105.0, 110.0, 121.0, 145.2, 174.24], index=dates)
    leveraged_open_price = leveraged_price.copy()
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 1,
            "medium_window": 2,
            "long_window": 3,
            "confirmation_days": 1,
            "exposure": {
                "below_long": 0.0,
                "above_long": 100.0,
                "medium_above_long": 100.0,
                "short_above_medium_above_long": 100.0,
            },
        },
        "position": {
            "min_exposure": 0.0,
            "max_exposure": 300.0,
            "rebalance_threshold": 0.0,
        },
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 3.0},
            ]
        },
        "execution": {
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "SGOV",
            "leveraged_asset": "SPXL",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        },
        "backtest": {
            "initial_capital": 100000.0,
            "annual_cash_return": 0.0,
            "annual_leveraged_fee": 0.0,
            "execution_timing": "same_close",
        },
    }

    result = run_backtest(
        price,
        vix,
        settings,
        leveraged_price=leveraged_price,
        leveraged_open_price=leveraged_open_price,
    )

    assert round(result.equity_curve["leveraged_buy_hold_daily_return"].iloc[-1], 6) == 0.2
    assert round(result.equity_curve["daily_return"].iloc[-1], 6) == 0.2


def test_backtest_falls_back_to_synthetic_leveraged_returns_before_actual_data_exists():
    dates = pd.bdate_range("2020-01-01", periods=4)
    price = pd.Series([100.0, 110.0, 121.0, 133.1], index=dates)
    leveraged_price = pd.Series([float("nan"), float("nan"), 100.0, 110.0], index=dates)
    leveraged_open_price = leveraged_price.copy()
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 1,
            "medium_window": 1,
            "long_window": 1,
            "confirmation_days": 1,
            "exposure": {
                "below_long": 0.0,
                "above_long": 100.0,
                "medium_above_long": 100.0,
                "short_above_medium_above_long": 100.0,
            },
        },
        "position": {
            "min_exposure": 0.0,
            "max_exposure": 300.0,
            "rebalance_threshold": 0.0,
        },
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 1.0},
            ]
        },
        "execution": {
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "SGOV",
            "leveraged_asset": "SPXL",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        },
        "backtest": {
            "initial_capital": 100000.0,
            "annual_cash_return": 0.0,
            "annual_leveraged_fee": 0.0,
            "execution_timing": "next_session",
        },
    }

    result = run_backtest(
        price,
        vix,
        settings,
        leveraged_price=leveraged_price,
        leveraged_open_price=leveraged_open_price,
    )

    assert round(result.equity_curve["leveraged_buy_hold_daily_return"].iloc[1], 6) == 0.3
    assert round(result.equity_curve["leveraged_buy_hold_daily_return"].iloc[2], 6) == 0.3
    assert round(result.equity_curve["leveraged_buy_hold_daily_return"].iloc[3], 6) == 0.1


def test_backtest_applies_foreign_asset_cap_to_positions():
    dates = pd.bdate_range("2020-01-01", periods=260)
    price = pd.Series(range(100, 360), index=dates, dtype=float)
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 20,
            "medium_window": 50,
            "long_window": 200,
            "confirmation_days": 1,
            "exposure": {
                "below_long": 0.0,
                "above_long": 50.0,
                "medium_above_long": 80.0,
                "short_above_medium_above_long": 100.0,
            },
        },
        "position": {
            "min_exposure": 0.0,
            "max_exposure": 300.0,
            "rebalance_threshold": 0.0,
        },
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 3.0},
                {"label": "normal", "min_inclusive": 20.0, "max_exclusive": 30.0, "multiplier": 1.0},
            ]
        },
        "execution": {
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "NZC.NZ",
            "nz_defensive_asset": "NZC.NZ",
            "au_defensive_asset": "BILL.AX",
            "leveraged_asset": "SPXL",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "limit_foreign_assets_nzd_value": True,
            "foreign_assets_nzd_limit": 50000.0,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        },
        "backtest": {
            "initial_capital": 1000000.0,
            "annual_cash_return": 0.0,
            "annual_leveraged_fee": 0.0,
        },
    }

    result = run_backtest(price, vix, settings)
    first_trade = result.trades.iloc[0]

    assert first_trade["core_percent"] + first_trade["leveraged_percent"] <= 5.01
    assert first_trade["local_defensive_percent"] >= 94.99
    assert first_trade["cap_note"]


def test_metrics_compound_daily_returns_instead_of_first_equity_row():
    equity_curve = pd.DataFrame(
        {
            "equity": [110.0, 121.0],
            "buy_hold_equity": [120.0, 132.0],
            "daily_return": [0.10, 0.10],
            "buy_hold_daily_return": [0.20, 0.10],
        }
    )

    metrics = _metrics(equity_curve)

    assert metrics["total_return_pct"] == 21.0
    assert metrics["buy_hold_total_return_pct"] == 32.0


def test_backtest_applies_signal_after_same_day_return():
    dates = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06", "2026-01-12"])
    price = pd.Series([100.0, 90.0, 80.0, 70.0, 200.0], index=dates)
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 1,
            "medium_window": 2,
            "long_window": 3,
            "confirmation_days": 1,
            "exposure": {
                "below_long": 0.0,
                "above_long": 100.0,
                "medium_above_long": 100.0,
                "short_above_medium_above_long": 100.0,
            },
        },
        "position": {
            "min_exposure": 0.0,
            "max_exposure": 300.0,
            "rebalance_threshold": 0.0,
        },
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 3.0},
            ]
        },
        "execution": {
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "SGOV",
            "leveraged_asset": "SPXL",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        },
        "backtest": {
            "initial_capital": 100000.0,
            "annual_cash_return": 0.0,
            "annual_leveraged_fee": 0.0,
        },
    }

    result = run_backtest(price, vix, settings)

    assert result.equity_curve["daily_return"].iloc[-1] == 0.0
    assert result.equity_curve["equity"].iloc[-1] == 100000.0
    assert result.equity_curve["actual_equivalent_exposure"].iloc[-1] == 0.0
    assert result.equity_curve["post_close_equivalent_exposure"].iloc[-1] == 300.0
    assert result.trades.iloc[-1]["target_exposure"] == 300.0


def test_backtest_result_start_uses_prior_history_without_counting_prior_trades():
    dates = pd.bdate_range("2020-01-01", periods=80)
    cycle = [100.0, 105.0, 110.0, 95.0, 90.0, 92.0, 108.0, 112.0]
    price = pd.Series([cycle[index % len(cycle)] for index in range(len(dates))], index=dates)
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 2,
            "medium_window": 3,
            "long_window": 5,
            "confirmation_days": 1,
            "exposure": {
                "below_long": 0.0,
                "above_long": 100.0,
                "medium_above_long": 100.0,
                "short_above_medium_above_long": 100.0,
            },
        },
        "position": {
            "min_exposure": 0.0,
            "max_exposure": 300.0,
            "rebalance_threshold": 20.0,
        },
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 3.0},
            ]
        },
        "execution": {
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "SGOV",
            "leveraged_asset": "SPXL",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        },
        "backtest": {
            "initial_capital": 100000.0,
            "annual_cash_return": 0.0,
            "annual_leveraged_fee": 0.0,
            "execution_timing": "next_session",
        },
    }
    result_start = dates[40]

    full = run_backtest(price, vix, settings)
    window = run_backtest(price, vix, settings, result_start=result_start)
    expected_trades = full.trades[full.trades["date"] >= result_start].reset_index(drop=True)

    assert window.equity_curve.index.min() >= result_start
    assert window.equity_curve.iloc[0]["equity"] == settings["backtest"]["initial_capital"]
    assert window.equity_curve.iloc[0]["buy_hold_equity"] == settings["backtest"]["initial_capital"]
    assert window.equity_curve.iloc[0]["leveraged_buy_hold_equity"] == settings["backtest"]["initial_capital"]
    assert window.equity_curve.iloc[0]["ma120_timing_equity"] == settings["backtest"]["initial_capital"]
    assert window.equity_curve.iloc[0]["leveraged_ma120_timing_equity"] == settings["backtest"]["initial_capital"]
    assert window.equity_curve.iloc[0]["daily_return"] == 0.0
    assert window.equity_curve.iloc[0]["buy_hold_daily_return"] == 0.0
    assert window.equity_curve.iloc[0]["leveraged_buy_hold_daily_return"] == 0.0
    assert window.equity_curve.iloc[0]["ma120_timing_daily_return"] == 0.0
    assert window.equity_curve.iloc[0]["leveraged_ma120_timing_daily_return"] == 0.0
    assert window.trades["date"].tolist() == expected_trades["date"].tolist()
    assert window.trades["target_exposure"].tolist() == expected_trades["target_exposure"].tolist()


def test_backtest_adds_weekly_contributions_after_first_visible_week():
    dates = pd.bdate_range("2026-01-05", periods=8)
    price = pd.Series(100.0, index=dates)
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 1,
            "medium_window": 1,
            "long_window": 1,
            "confirmation_days": 1,
            "exposure": {
                "below_long": 0.0,
                "above_long": 100.0,
                "medium_above_long": 100.0,
                "short_above_medium_above_long": 100.0,
            },
        },
        "position": {
            "min_exposure": 0.0,
            "max_exposure": 100.0,
            "rebalance_threshold": 0.0,
        },
        "vix": {"rules": [{"label": "low", "max_exclusive": 20.0, "multiplier": 1.0}]},
        "execution": {
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "SGOV",
            "leveraged_asset": "SPXL",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        },
        "backtest": {
            "initial_capital": 100000.0,
            "weekly_contribution": 1000.0,
            "annual_cash_return": 0.0,
            "annual_leveraged_fee": 0.0,
            "execution_timing": "next_session",
        },
    }

    result = run_backtest(price, vix, settings)

    assert result.equity_curve.iloc[0]["equity"] == 100000.0
    assert result.equity_curve["weekly_contribution"].tolist() == [
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1000.0,
        0.0,
        0.0,
    ]
    for column in [
        "equity",
        "buy_hold_equity",
        "leveraged_buy_hold_equity",
        "ma120_timing_equity",
        "leveraged_ma120_timing_equity",
    ]:
        assert result.equity_curve.iloc[-1][column] == 101000.0


def test_backtest_can_apply_signal_before_same_day_return():
    dates = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06", "2026-01-12"])
    price = pd.Series([100.0, 90.0, 80.0, 70.0, 200.0], index=dates)
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 1,
            "medium_window": 2,
            "long_window": 3,
            "confirmation_days": 1,
            "exposure": {
                "below_long": 0.0,
                "above_long": 100.0,
                "medium_above_long": 100.0,
                "short_above_medium_above_long": 100.0,
            },
        },
        "position": {
            "min_exposure": 0.0,
            "max_exposure": 300.0,
            "rebalance_threshold": 0.0,
        },
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 3.0},
            ]
        },
        "execution": {
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "SGOV",
            "leveraged_asset": "SPXL",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        },
        "backtest": {
            "initial_capital": 100000.0,
            "annual_cash_return": 0.0,
            "annual_leveraged_fee": 0.0,
            "signal_effective_next_day": False,
        },
    }

    result = run_backtest(price, vix, settings)

    assert round(result.equity_curve["daily_return"].iloc[-1], 6) == 5.571429
    assert round(result.equity_curve["equity"].iloc[-1], 2) == 657142.86
    assert result.equity_curve["actual_equivalent_exposure"].iloc[-1] == 300.0
    assert result.equity_curve["post_close_equivalent_exposure"].iloc[-1] == 300.0
    assert result.trades.iloc[-1]["target_exposure"] == 300.0


def test_backtest_nz_close_us_open_holds_nz_core_overnight_and_3x_intraday():
    dates = pd.to_datetime(
        ["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06", "2026-01-12", "2026-01-13"]
    )
    price = pd.Series([100.0, 90.0, 80.0, 70.0, 200.0, 220.0], index=dates)
    open_price = pd.Series([100.0, 90.0, 80.0, 70.0, 200.0, 210.0], index=dates)
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 1,
            "medium_window": 2,
            "long_window": 3,
            "confirmation_days": 1,
            "exposure": {
                "below_long": 0.0,
                "above_long": 100.0,
                "medium_above_long": 100.0,
                "short_above_medium_above_long": 100.0,
            },
        },
        "position": {
            "min_exposure": 0.0,
            "max_exposure": 300.0,
            "rebalance_threshold": 0.0,
        },
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 3.0},
            ]
        },
        "execution": {
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "SGOV",
            "leveraged_asset": "SPXL",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        },
        "backtest": {
            "initial_capital": 100000.0,
            "annual_cash_return": 0.0,
            "annual_leveraged_fee": 0.0,
            "execution_timing": "nz_close_us_open",
        },
    }

    result = run_backtest(price, vix, settings, open_price=open_price)

    assert result.equity_curve["actual_equivalent_exposure"].iloc[-2] == 0.0
    assert result.equity_curve["pending_next_open_equivalent_exposure"].iloc[-2] == 300.0
    assert result.equity_curve["post_close_equivalent_exposure"].iloc[-2] == 100.0
    assert round(result.equity_curve["daily_return"].iloc[-1], 6) == 0.2
    assert round(result.equity_curve["equity"].iloc[-1], 2) == 120000.0
    assert result.equity_curve["overnight_equivalent_exposure"].iloc[-1] == 100.0
    assert result.equity_curve["intraday_equivalent_exposure"].iloc[-1] == 300.0
    assert result.trades.iloc[-1]["execution_timing"] == "nz_close_us_open"


def test_backtest_nz_close_us_open_can_rebalance_on_consecutive_days():
    dates = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"])
    price = pd.Series([100.0, 200.0, 50.0, 60.0], index=dates)
    open_price = pd.Series([100.0, 100.0, 200.0, 50.0], index=dates)
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 1,
            "medium_window": 1,
            "long_window": 2,
            "confirmation_days": 1,
            "exposure": {
                "below_long": 0.0,
                "above_long": 100.0,
                "medium_above_long": 100.0,
                "short_above_medium_above_long": 100.0,
            },
        },
        "position": {
            "min_exposure": 0.0,
            "max_exposure": 300.0,
            "rebalance_threshold": 0.0,
        },
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 3.0},
            ]
        },
        "execution": {
            "core_asset": "USF.NZX",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "NZC.NZ",
            "nz_defensive_asset": "NZC.NZ",
            "leveraged_asset": "SPXL",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        },
        "backtest": {
            "initial_capital": 100000.0,
            "annual_cash_return": 0.0,
            "annual_leveraged_fee": 0.0,
            "execution_timing": "nz_close_us_open",
        },
    }

    result = run_backtest(price, vix, settings, open_price=open_price)

    assert result.trades["date"].tolist() == list(dates[1:])
    assert result.trades["target_exposure"].tolist() == [300.0, 0.0, 300.0]
    assert result.equity_curve.loc[pd.Timestamp("2026-01-06"), "post_close_equivalent_exposure"] == 100.0
    assert result.equity_curve.loc[pd.Timestamp("2026-01-06"), "pending_next_open_equivalent_exposure"] == 300.0


def test_ma120_timing_applies_signal_after_same_day_return_by_default():
    dates = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05"])
    price = pd.Series([100.0, 100.0, 50.0], index=dates)
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 1,
            "medium_window": 1,
            "long_window": 1,
            "confirmation_days": 1,
            "exposure": {
                "below_long": 0.0,
                "above_long": 100.0,
                "medium_above_long": 100.0,
                "short_above_medium_above_long": 100.0,
            },
        },
        "position": {
            "min_exposure": 0.0,
            "max_exposure": 100.0,
            "rebalance_threshold": 0.0,
        },
        "vix": {"rules": [{"label": "low", "max_exclusive": 20.0, "multiplier": 1.0}]},
        "execution": {
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "SGOV",
            "leveraged_asset": "SPXL",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        },
        "backtest": {
            "initial_capital": 100000.0,
            "annual_cash_return": 0.0,
            "annual_leveraged_fee": 0.0,
            "execution_timing": "next_session",
        },
    }

    result = run_backtest(price, vix, settings)

    assert result.equity_curve["ma120_timing_daily_return"].iloc[-1] == -0.5
    assert result.equity_curve["ma120_timing_equity"].iloc[-1] == 50000.0


def test_ma120_timing_buys_at_next_us_open_when_configured():
    dates = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"])
    price = pd.Series([100.0, 100.0, 50.0, 120.0, 143.0], index=dates)
    open_price = pd.Series([100.0, 100.0, 50.0, 120.0, 130.0], index=dates)
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 1,
            "medium_window": 1,
            "long_window": 1,
            "confirmation_days": 1,
            "exposure": {
                "below_long": 0.0,
                "above_long": 100.0,
                "medium_above_long": 100.0,
                "short_above_medium_above_long": 100.0,
            },
        },
        "position": {
            "min_exposure": 0.0,
            "max_exposure": 100.0,
            "rebalance_threshold": 0.0,
        },
        "vix": {"rules": [{"label": "low", "max_exclusive": 20.0, "multiplier": 1.0}]},
        "execution": {
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "SGOV",
            "leveraged_asset": "SPXL",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        },
        "backtest": {
            "initial_capital": 100000.0,
            "annual_cash_return": 0.0,
            "annual_leveraged_fee": 0.0,
            "execution_timing": "nz_close_us_open",
        },
    }

    result = run_backtest(price, vix, settings, open_price=open_price)

    assert result.equity_curve.loc[pd.Timestamp("2026-01-06"), "ma120_timing_daily_return"] == 0.0
    assert round(result.equity_curve.loc[pd.Timestamp("2026-01-07"), "ma120_timing_daily_return"], 6) == 0.1


def test_backtest_exits_leverage_at_us_close_before_next_overnight_gap():
    dates = pd.to_datetime(
        [
            "2026-01-01",
            "2026-01-02",
            "2026-01-05",
            "2026-01-06",
            "2026-01-12",
            "2026-01-13",
            "2026-01-19",
            "2026-01-20",
        ]
    )
    price = pd.Series([100.0, 90.0, 80.0, 70.0, 200.0, 220.0, 150.0, 140.0], index=dates)
    open_price = pd.Series([100.0, 90.0, 80.0, 70.0, 200.0, 210.0, 150.0, 100.0], index=dates)
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 1,
            "medium_window": 2,
            "long_window": 3,
            "confirmation_days": 1,
            "exposure": {
                "below_long": 0.0,
                "above_long": 100.0,
                "medium_above_long": 100.0,
                "short_above_medium_above_long": 100.0,
            },
        },
        "position": {
            "min_exposure": 0.0,
            "max_exposure": 300.0,
            "rebalance_threshold": 0.0,
        },
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 3.0},
            ]
        },
        "execution": {
            "core_asset": "USF.NZX",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "NZC.NZ",
            "nz_defensive_asset": "NZC.NZ",
            "leveraged_asset": "SPXL",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        },
        "backtest": {
            "initial_capital": 100000.0,
            "annual_cash_return": 0.0,
            "annual_leveraged_fee": 0.0,
            "execution_timing": "nz_close_us_open",
        },
    }

    result = run_backtest(price, vix, settings, open_price=open_price)

    assert result.equity_curve.loc[pd.Timestamp("2026-01-19"), "post_close_equivalent_exposure"] == 0.0
    assert result.equity_curve.loc[pd.Timestamp("2026-01-19"), "pending_next_open_equivalent_exposure"] == 0.0
    assert result.equity_curve.loc[pd.Timestamp("2026-01-20"), "overnight_equivalent_exposure"] == 0.0
    assert result.equity_curve.loc[pd.Timestamp("2026-01-20"), "intraday_equivalent_exposure"] == 0.0
    assert result.equity_curve.loc[pd.Timestamp("2026-01-20"), "daily_return"] == 0.0


def test_parameter_sweep_returns_individual_unified_and_ranges():
    dates = pd.bdate_range("2020-01-01", periods=260)
    price = pd.Series(range(100, 360), index=dates, dtype=float)
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 20,
            "medium_window": 50,
            "long_window": 200,
            "confirmation_days": 1,
            "exposure": {
                "below_long": 0.0,
                "above_long": 50.0,
                "medium_above_long": 80.0,
                "short_above_medium_above_long": 100.0,
            },
        },
        "position": {
            "min_exposure": 0.0,
            "max_exposure": 300.0,
            "rebalance_threshold": 10.0,
        },
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 1.2},
                {"label": "normal", "min_inclusive": 20.0, "max_exclusive": 30.0, "multiplier": 1.0},
            ]
        },
        "execution": {
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "SGOV",
            "leveraged_asset": "SPXL",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        },
        "backtest": {
            "initial_capital": 100000.0,
            "annual_cash_return": 0.0,
            "annual_leveraged_fee": 0.0,
            "execution_timing": "next_session",
        },
    }

    individual, unified, ranges, recommendations = run_parameter_sweep(
        price, vix, settings, factors=(0.8, 1.0, 1.2)
    )

    assert not individual.empty
    assert not unified.empty
    assert not ranges.empty
    assert not recommendations.empty
    assert set(unified["parameter"]) == {"all_parameters"}
    assert "trend.short_window" in set(individual["parameter"])
    assert "vix.rules.0.multiplier" in set(individual["parameter"])
    assert individual["total_return_pct"].iloc[0] >= individual["total_return_pct"].iloc[-1]
    assert "recommended_action" in recommendations.columns


def test_parameter_sweep_uses_50_percent_default_range_and_default_delta():
    dates = pd.bdate_range("2020-01-01", periods=420)
    price = pd.Series(range(100, 520), index=dates, dtype=float)
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 20,
            "medium_window": 50,
            "long_window": 200,
            "confirmation_days": 1,
            "exposure": {
                "below_long": 0.0,
                "above_long": 50.0,
                "medium_above_long": 80.0,
                "short_above_medium_above_long": 100.0,
            },
        },
        "position": {
            "min_exposure": 0.0,
            "max_exposure": 300.0,
            "rebalance_threshold": 10.0,
        },
        "vix": {"rules": [{"label": "low", "max_exclusive": 20.0, "multiplier": 1.2}]},
        "execution": {
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "SGOV",
            "leveraged_asset": "SPXL",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        },
        "backtest": {
            "initial_capital": 100000.0,
            "annual_cash_return": 0.0,
            "annual_leveraged_fee": 0.0,
            "execution_timing": "next_session",
        },
    }

    individual, unified, _, recommendations = run_parameter_sweep(
        price,
        vix,
        settings,
        baseline_settings=build_parameter_sweep_candidate(settings, "individual", "trend.short_window", 1.5),
    )

    assert SWEEP_FACTORS == (0.5, 0.75, 1.0, 1.25, 1.5)
    assert set(individual["factor"]) == set(SWEEP_FACTORS)
    assert set(unified["factor"]) == set(SWEEP_FACTORS)
    assert "default_baseline_delta_pct" in individual.columns
    assert "default_baseline_delta_pct" in recommendations.columns


def test_parameter_sweep_respects_strategy_ui_caps():
    settings = {
        "trend": {
            "short_window": 90,
            "medium_window": 140,
            "long_window": 260,
            "confirmation_days": 9,
            "exposure": {
                "below_long": 220.0,
                "above_long": 260.0,
                "medium_above_long": 280.0,
                "short_above_medium_above_long": 300.0,
            },
        },
        "position": {
            "min_exposure": 0.0,
            "max_exposure": 300.0,
            "rebalance_threshold": 25.0,
        },
        "vix": {"rules": [{"label": "low", "max_exclusive": 20.0, "multiplier": 4.5}]},
        "execution": {
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "SGOV",
            "leveraged_asset": "SPXL",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        },
        "backtest": {
            "initial_capital": 100000.0,
            "annual_cash_return": 0.0,
            "annual_leveraged_fee": 0.0,
            "execution_timing": "next_session",
        },
    }

    candidate = build_parameter_sweep_candidate(settings, "unified", "all_parameters", 1.5)

    assert candidate["trend"]["short_window"] == 100
    assert candidate["trend"]["medium_window"] == 150
    assert candidate["trend"]["long_window"] == 300
    assert candidate["trend"]["confirmation_days"] == 10
    assert candidate["trend"]["exposure"]["below_long"] <= 300.0
    assert candidate["trend"]["exposure"]["above_long"] <= 300.0
    assert candidate["trend"]["exposure"]["medium_above_long"] <= 300.0
    assert candidate["trend"]["exposure"]["short_above_medium_above_long"] <= 300.0
    assert candidate["position"]["max_exposure"] == 300.0
    assert candidate["position"]["rebalance_threshold"] == 30.0
    assert candidate["vix"]["rules"][0]["multiplier"] == 5.0
