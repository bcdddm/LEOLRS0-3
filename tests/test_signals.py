import pandas as pd

from trend_system.signals import history_start_date, latest_signal, recent_signals, required_history_days


def test_history_start_date_uses_longest_configured_signal_window():
    settings = {
        "trend": {"short_window": 20, "medium_window": 50, "long_window": 120},
        "position": {"min_exposure": 0.0, "max_exposure": 300.0},
    }

    start = pd.Timestamp("2000-01-03").date()

    assert required_history_days(settings) == 120
    assert history_start_date(start, settings) == (pd.Timestamp(start) - pd.tseries.offsets.BDay(120)).date()


def test_history_start_date_includes_enabled_longer_risk_lookbacks():
    settings = {
        "trend": {"short_window": 20, "medium_window": 50, "long_window": 120},
        "position": {
            "min_exposure": 0.0,
            "max_exposure": 300.0,
            "no_new_high_cap_enabled": True,
            "no_new_high_days": 200,
            "no_new_high_high_window": 120,
        },
    }

    assert required_history_days(settings) == 320


def test_history_start_date_includes_market_health_200_day_average():
    settings = {
        "trend": {"short_window": 20, "medium_window": 50, "long_window": 120},
        "position": {"min_exposure": 0.0, "max_exposure": 300.0},
    }

    assert required_history_days(settings, include_market_health=True) == 200


def test_latest_signal_applies_trend_and_vix_multiplier():
    dates = pd.bdate_range("2024-01-01", periods=260)
    price = pd.Series(range(100, 360), index=dates, dtype=float)
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 20,
            "medium_window": 50,
            "long_window": 200,
            "exposure": {
                "below_long": 0.0,
                "above_long": 50.0,
                "medium_above_long": 80.0,
                "short_above_medium_above_long": 100.0,
            },
        },
        "position": {"min_exposure": 0.0, "max_exposure": 120.0},
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 1.2},
                {"label": "normal", "min_inclusive": 20.0, "max_exclusive": 30.0, "multiplier": 1.0},
            ]
        },
    }

    signal = latest_signal(price, vix, settings)

    assert signal.trend_label == "accelerating_bull"
    assert signal.trend_exposure == 100.0
    assert signal.vix_label == "low"
    assert signal.target_exposure == 120.0


def test_recent_signals_returns_latest_two_signals():
    dates = pd.bdate_range("2024-01-01", periods=260)
    price = pd.Series(range(100, 360), index=dates, dtype=float)
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 20,
            "medium_window": 50,
            "long_window": 200,
            "exposure": {
                "below_long": 0.0,
                "above_long": 50.0,
                "medium_above_long": 80.0,
                "short_above_medium_above_long": 100.0,
            },
        },
        "position": {"min_exposure": 0.0, "max_exposure": 120.0},
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 1.2},
                {"label": "normal", "min_inclusive": 20.0, "max_exclusive": 30.0, "multiplier": 1.0},
            ]
        },
    }

    signals = recent_signals(price, vix, settings, count=2)

    assert len(signals) == 2
    assert signals[0].date == dates[-2]
    assert signals[1].date == dates[-1]


def test_latest_signal_can_snap_target_to_fixed_exposure_tiers():
    dates = pd.bdate_range("2024-01-01", periods=260)
    price = pd.Series(range(100, 360), index=dates, dtype=float)
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 20,
            "medium_window": 50,
            "long_window": 200,
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
            "fixed_exposure_tiers_enabled": True,
            "fixed_exposure_tiers": [0.0, 100.0, 300.0],
        },
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 1.2},
                {"label": "normal", "min_inclusive": 20.0, "max_exclusive": 30.0, "multiplier": 1.0},
            ]
        },
    }

    signal = latest_signal(price, vix, settings)

    assert signal.trend_exposure == 100.0
    assert signal.target_exposure == 100.0


def test_latest_signal_applies_minimum_equivalent_exposure_floor():
    dates = pd.bdate_range("2024-01-01", periods=260)
    price = pd.Series(range(100, 360), index=dates, dtype=float)
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 20,
            "medium_window": 50,
            "long_window": 200,
            "exposure": {
                "below_long": 0.0,
                "above_long": 20.0,
                "medium_above_long": 30.0,
                "short_above_medium_above_long": 40.0,
            },
        },
        "position": {"min_exposure": 60.0, "max_exposure": 300.0},
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 1.0},
                {"label": "normal", "min_inclusive": 20.0, "max_exclusive": 30.0, "multiplier": 1.0},
            ]
        },
    }

    signal = latest_signal(price, vix, settings)

    assert signal.trend_label == "accelerating_bull"
    assert signal.trend_exposure == 40.0
    assert signal.target_exposure == 60.0


def test_latest_signal_applies_vix_exposure_cap_curve_when_enabled():
    dates = pd.bdate_range("2024-01-01", periods=260)
    price = pd.Series(range(100, 360), index=dates, dtype=float)
    vix = pd.Series(23.0, index=dates)
    settings = {
        "trend": {
            "short_window": 20,
            "medium_window": 50,
            "long_window": 200,
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
            "vix_exposure_cap_enabled": True,
            "vix_exposure_caps": [
                {"max_exclusive": 18.0, "max_exposure": 300.0},
                {"min_inclusive": 18.0, "max_exclusive": 22.0, "max_exposure": 250.0},
                {"min_inclusive": 22.0, "max_exclusive": 26.0, "max_exposure": 200.0},
                {"min_inclusive": 26.0, "max_exclusive": 30.0, "max_exposure": 150.0},
                {"min_inclusive": 30.0, "max_exposure": 100.0},
            ],
        },
        "vix": {
            "rules": [
                {"label": "normal", "max_exclusive": 30.0, "multiplier": 3.0},
            ]
        },
    }

    signal = latest_signal(price, vix, settings)

    assert signal.trend_exposure == 100.0
    assert signal.target_exposure == 200.0


def test_latest_signal_ignores_vix_exposure_cap_curve_when_disabled():
    dates = pd.bdate_range("2024-01-01", periods=260)
    price = pd.Series(range(100, 360), index=dates, dtype=float)
    vix = pd.Series(23.0, index=dates)
    settings = {
        "trend": {
            "short_window": 20,
            "medium_window": 50,
            "long_window": 200,
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
            "vix_exposure_cap_enabled": False,
            "vix_exposure_caps": [
                {"min_inclusive": 22.0, "max_exclusive": 26.0, "max_exposure": 200.0},
            ],
        },
        "vix": {
            "rules": [
                {"label": "normal", "max_exclusive": 30.0, "multiplier": 3.0},
            ]
        },
    }

    signal = latest_signal(price, vix, settings)

    assert signal.target_exposure == 300.0


def test_latest_signal_applies_drawdown_exposure_cap_curve_when_enabled():
    dates = pd.bdate_range("2024-01-01", periods=260)
    price = pd.Series(range(100, 360), index=dates, dtype=float)
    price.iloc[-1] = 330.0
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 20,
            "medium_window": 50,
            "long_window": 200,
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
            "drawdown_exposure_cap_enabled": True,
            "drawdown_lookback_days": 252,
            "drawdown_exposure_caps": [
                {"max_exclusive": 5.0, "max_exposure": 300.0},
                {"min_inclusive": 5.0, "max_exclusive": 10.0, "max_exposure": 250.0},
                {"min_inclusive": 10.0, "max_exclusive": 15.0, "max_exposure": 200.0},
                {"min_inclusive": 15.0, "max_exclusive": 20.0, "max_exposure": 150.0},
                {"min_inclusive": 20.0, "max_exposure": 100.0},
            ],
        },
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 3.0},
            ]
        },
    }

    signal = latest_signal(price, vix, settings)

    assert signal.trend_exposure == 100.0
    assert signal.target_exposure == 250.0


def test_latest_signal_caps_exposure_when_no_new_high_for_configured_days():
    dates = pd.bdate_range("2024-01-01", periods=80)
    price = pd.concat(
        [
            pd.Series(range(100, 140), index=dates[:40], dtype=float),
            pd.Series([139.0 - index * 0.1 for index in range(40)], index=dates[40:], dtype=float),
        ]
    )
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 5,
            "medium_window": 10,
            "long_window": 20,
            "exposure": {
                "below_long": 100.0,
                "above_long": 100.0,
                "medium_above_long": 100.0,
                "short_above_medium_above_long": 100.0,
            },
        },
        "position": {
            "min_exposure": 0.0,
            "max_exposure": 300.0,
            "no_new_high_cap_enabled": True,
            "no_new_high_days": 10,
            "no_new_high_high_window": 20,
            "no_new_high_max_exposure": 150.0,
        },
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 3.0},
            ]
        },
    }

    signal = latest_signal(price, vix, settings)

    assert signal.target_exposure == 150.0


def test_latest_signal_applies_trend_quality_cap_when_price_falls_below_ma():
    dates = pd.bdate_range("2024-01-01", periods=260)
    price = pd.Series(range(100, 360), index=dates, dtype=float)
    price.iloc[-30:] = pd.Series(range(359, 329, -1), index=dates[-30:], dtype=float)
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 20,
            "medium_window": 50,
            "long_window": 200,
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
            "trend_quality_cap_enabled": True,
            "trend_quality_ma_window": 20,
            "trend_quality_slope_lookback_days": 10,
            "trend_quality_rising_slope_min_pct": 0.5,
            "trend_quality_falling_slope_max_pct": 0.0,
            "trend_quality_rising_max_exposure": 300.0,
            "trend_quality_flat_max_exposure": 220.0,
            "trend_quality_falling_max_exposure": 150.0,
            "trend_quality_below_ma_max_exposure": 100.0,
        },
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 3.0},
            ]
        },
    }

    signal = latest_signal(price, vix, settings)

    assert signal.trend_exposure == 100.0
    assert signal.target_exposure == 100.0


def test_latest_signal_applies_trend_quality_cap_when_120_ma_is_below_200_ma():
    dates = pd.bdate_range("2024-01-01", periods=260)
    early_high = pd.Series([300.0] * 80, index=dates[:80])
    low_base = pd.Series([100.0] * 120, index=dates[80:200])
    recent_rally = pd.Series(range(150, 210), index=dates[200:], dtype=float)
    price = pd.concat([early_high, low_base, recent_rally])
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 20,
            "medium_window": 50,
            "long_window": 200,
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
            "trend_quality_cap_enabled": True,
            "trend_quality_ma_cross_slow_decline_enabled": True,
            "trend_quality_ma_window": 20,
            "trend_quality_slope_lookback_days": 10,
            "trend_quality_rising_slope_min_pct": 0.5,
            "trend_quality_falling_slope_max_pct": 0.0,
            "trend_quality_rising_max_exposure": 300.0,
            "trend_quality_flat_max_exposure": 220.0,
            "trend_quality_falling_max_exposure": 150.0,
            "trend_quality_below_ma_max_exposure": 100.0,
        },
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 3.0},
            ]
        },
    }

    signal = latest_signal(price, vix, settings)

    assert signal.trend_quality_slow_decline is True
    assert signal.trend_quality_ma_120 < signal.trend_quality_ma_200
    assert signal.target_exposure == 100.0


def test_latest_signal_allows_zero_exposure_floor_during_slow_decline():
    dates = pd.bdate_range("2024-01-01", periods=260)
    early_high = pd.Series([300.0] * 80, index=dates[:80])
    slow_decline = pd.Series([100.0] * 180, index=dates[80:])
    price = pd.concat([early_high, slow_decline])
    vix = pd.Series(16.0, index=dates)
    settings = {
        "trend": {
            "short_window": 20,
            "medium_window": 50,
            "long_window": 200,
            "exposure": {
                "below_long": 0.0,
                "above_long": 50.0,
                "medium_above_long": 80.0,
                "short_above_medium_above_long": 100.0,
            },
        },
        "position": {
            "min_exposure": 100.0,
            "max_exposure": 300.0,
            "trend_quality_cap_enabled": True,
            "trend_quality_ma_cross_slow_decline_enabled": True,
            "trend_quality_slow_decline_zero_floor_enabled": True,
            "trend_quality_ma_window": 20,
            "trend_quality_slope_lookback_days": 10,
            "trend_quality_rising_slope_min_pct": 0.5,
            "trend_quality_falling_slope_max_pct": 0.0,
            "trend_quality_rising_max_exposure": 300.0,
            "trend_quality_flat_max_exposure": 220.0,
            "trend_quality_falling_max_exposure": 150.0,
            "trend_quality_below_ma_max_exposure": 100.0,
        },
        "vix": {
            "rules": [
                {"label": "low", "max_exclusive": 20.0, "multiplier": 3.0},
            ]
        },
    }

    signal = latest_signal(price, vix, settings)

    assert signal.trend_label == "risk_off"
    assert signal.trend_quality_slow_decline is True
    assert signal.trend_quality_ma_120 < signal.trend_quality_ma_200
    assert signal.target_exposure == 0.0
