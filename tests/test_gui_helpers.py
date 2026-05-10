from datetime import datetime, timedelta
import re
import tomllib
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd

from trend_system.config import load_settings
from trend_system.exposure_rules import counts_toward_foreign_cap
from trend_system import __version__
from trend_system.gui import (
    BACKTEST_PRESETS,
    _asset_currency,
    _backtest_date_defaults,
    _build_pdf_report,
    _build_rebalance_advice,
    _config_options,
    _exposure_columns_for_timing,
    _format_duration,
    _market_segments,
    _parameter_ui_name,
    _pdf_filename,
    _price_series,
    _profile_path_for_name,
    _rebalance_action,
    _release_notes_text,
    _series_label,
    _save_config,
    _state_label,
    _trend_ma_labels,
    _tr,
    _widget_key_prefix,
)


def test_foreign_cap_excludes_nz_and_asx_suffixes():
    assert not counts_toward_foreign_cap("USF.NZ")
    assert not counts_toward_foreign_cap("USF.nzx")
    assert not counts_toward_foreign_cap("IVV.AX")
    assert not counts_toward_foreign_cap("IVV.asx")
    assert counts_toward_foreign_cap("VOO")
    assert counts_toward_foreign_cap("SPXL")


def test_asset_currency_uses_suffix():
    settings = {"profile": {"base_currency": "NZD"}}
    assert _asset_currency("USF.NZX", settings) == "NZD"
    assert _asset_currency("IVV.ASX", settings) == "AUD"
    assert _asset_currency("SPXL", settings) == "USD"


def test_price_series_handles_single_symbol_multiindex_download():
    dates = pd.bdate_range("2026-01-01", periods=2)
    frame = pd.DataFrame(
        {
            ("SPY", "Open"): [99.0, 100.0],
            ("SPY", "Close"): [100.0, 101.0],
        },
        index=dates,
    )

    price = _price_series(frame, "Close")

    assert price.tolist() == [100.0, 101.0]


def test_english_ui_helpers_translate_labels():
    assert _tr("en", "中文", "English") == "English"
    assert _format_duration(timedelta(minutes=65), "en") == "1h 5m"
    assert _state_label("risk_off", "en") == "Risk off"
    assert _rebalance_action("SPY", 10.0, "en") == "Buy"


def test_market_segments_split_overlapping_windows():
    tz = ZoneInfo("Pacific/Auckland")
    start = datetime(2026, 1, 5, 9, 0, tzinfo=tz)
    end = datetime(2026, 1, 5, 13, 0, tzinfo=tz)
    windows = [
        {"label": "NZ", "open": datetime(2026, 1, 5, 10, 0, tzinfo=tz), "close": datetime(2026, 1, 5, 12, 0, tzinfo=tz)},
        {"label": "AU", "open": datetime(2026, 1, 5, 11, 0, tzinfo=tz), "close": datetime(2026, 1, 5, 13, 0, tzinfo=tz)},
    ]

    segments = _market_segments(windows, start, end)

    assert [segment["start"].hour for segment in segments] == [10, 11, 12]
    assert [[window["label"] for window in segment["active"]] for segment in segments] == [
        ["NZ"],
        ["NZ", "AU"],
        ["AU"],
    ]


def test_leveraged_ma120_timing_label_describes_cash_switch():
    assert _series_label("leveraged_ma120_timing_equity", "zh") == "三倍持有：跌破 120 日均线转现金"
    assert _series_label("leveraged_ma120_timing_equity", "en") == "3x Hold: Cash Below 120MA"


def test_nz_close_us_open_exposure_chart_uses_intraday_and_overnight_series():
    assert _exposure_columns_for_timing("nz_close_us_open") == [
        "target_exposure",
        "overnight_equivalent_exposure",
        "intraday_equivalent_exposure",
    ]
    assert _series_label("overnight_equivalent_exposure", "zh") == "隔夜等效仓位"
    assert _series_label("intraday_equivalent_exposure", "en") == "Intraday equivalent exposure"


def test_backtest_presets_include_2021_to_2023_window():
    assert BACKTEST_PRESETS["2021-01-01 到 2023-12-31"] == (
        pd.Timestamp("2021-01-01").date(),
        pd.Timestamp("2023-12-31").date(),
    )


def test_backtest_preset_controls_start_and_end_dates():
    settings = {"backtest": {"start": "2015-06-15"}}

    fixed_start, fixed_end = _backtest_date_defaults("2021-01-01 到 2023-12-31", settings)
    custom_start, custom_end = _backtest_date_defaults(
        "自定义",
        settings,
        today=pd.Timestamp("2026-05-10").date(),
    )

    assert fixed_start == pd.Timestamp("2021-01-01").date()
    assert fixed_end == pd.Timestamp("2023-12-31").date()
    assert custom_start == pd.Timestamp("2015-06-15").date()
    assert custom_end == pd.Timestamp("2026-05-10").date()


def test_trend_ma_labels_follow_configured_windows():
    settings = {"trend": {"short_window": 10, "medium_window": 40, "long_window": 120}}

    assert _trend_ma_labels(settings) == ("MA10", "MA40", "MA120")


def test_settings_profile_save_writes_loadable_toml(tmp_path):
    target = tmp_path / "profiles" / "Aggressive.toml"
    settings = {
        "profile": {
            "name": "Aggressive",
            "home_timezone": "America/New_York",
            "base_currency": "USD",
        },
        "ui": {"language": "en"},
        "backtest": {"start": "2021-01-01"},
    }

    _save_config(target, settings)
    loaded = load_settings(target).raw

    assert loaded["profile"]["name"] == "Aggressive"
    assert loaded["profile"]["home_timezone"] == "America/New_York"
    assert loaded["profile"]["base_currency"] == "USD"
    assert loaded["ui"]["language"] == "en"
    assert loaded["backtest"]["start"] == "2021-01-01"


def test_pdf_report_generation_and_backtest_filename():
    settings = {
        "profile": {"name": "SAFE"},
        "signals": {"primary": "SPY"},
        "trend": {"short_window": 20, "medium_window": 50, "long_window": 120, "confirmation_days": 2},
        "position": {
            "min_exposure": 0.0,
            "max_exposure": 300.0,
            "trend_quality_ma_cross_slow_decline_enabled": True,
            "trend_quality_slow_decline_zero_floor_enabled": True,
        },
        "execution": {
            "default_market": "us",
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "leveraged_asset": "SPXL",
            "defensive_asset": "SGOV",
            "allow_leverage": True,
        },
        "vix": {"rules": [{"label": "low", "multiplier": 1.2}]},
    }

    pdf = _build_pdf_report(
        "历史回测",
        settings,
        "zh",
        sections=[("回测表现", [("CAGR", "12.34%")])],
    )
    filename = _pdf_filename("backtest", settings, range_text="2021-01-01_to_2023-12-31", cagr=12.34)

    assert pdf.startswith(b"%PDF")
    assert "backtest" in filename
    assert "2021-01-01_to_2023-12-31" in filename
    assert "cagr-12.34pct" in filename
    assert filename.endswith(".pdf")


def test_pdf_report_can_embed_line_charts():
    settings = {
        "profile": {"name": "SAFE"},
        "signals": {"primary": "SPY"},
        "trend": {"short_window": 20, "medium_window": 50, "long_window": 120, "confirmation_days": 2},
        "position": {"min_exposure": 0.0, "max_exposure": 300.0},
        "execution": {
            "default_market": "us",
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "leveraged_asset": "SPXL",
            "defensive_asset": "SGOV",
        },
        "vix": {"rules": []},
    }
    frame = pd.DataFrame(
        {"equity": [100000.0, 101000.0], "buy_hold_equity": [100000.0, 100500.0]},
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    )

    pdf = _build_pdf_report(
        "历史回测",
        settings,
        "zh",
        sections=[("回测表现", [("CAGR", "12.34%")])],
        charts=[("净值曲线", frame, ["equity", "buy_hold_equity"])],
    )

    assert pdf.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) >= 2


def test_pdf_report_prints_strategy_information_on_separate_page():
    settings = {
        "profile": {"name": "SAFE"},
        "signals": {"primary": "SPY"},
        "trend": {"short_window": 20, "medium_window": 50, "long_window": 120, "confirmation_days": 2},
        "position": {"min_exposure": 0.0, "max_exposure": 300.0},
        "execution": {
            "default_market": "us",
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "leveraged_asset": "SPXL",
            "defensive_asset": "SGOV",
        },
        "vix": {"rules": []},
    }

    pdf = _build_pdf_report(
        "今日信号",
        settings,
        "zh",
        sections=[
            ("市场状态", [("目标等效仓位", "100%")]),
            ("策略信息", [("趋势均线", "20 / 50 / 120")]),
        ],
    )

    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) == 2


def test_project_metadata_uses_leolrs_name():
    with open("pyproject.toml", "rb") as file:
        metadata = tomllib.load(file)

    assert metadata["project"]["name"] == "LEOLRS0-3"
    assert metadata["project"]["version"] == __version__


def test_settings_overview_release_notes_include_bug_fix_log():
    notes = _release_notes_text()

    assert "回测区间起点" in notes
    assert "区段无新高锁仓" in notes
    assert "默认参考线" in notes


def test_settings_overview_release_notes_can_render_english_translation():
    notes = _release_notes_text("en")

    assert "Update and Fix Log" in notes
    assert "backtest start-date truncation" in notes
    assert "区段无新高锁仓" not in notes


def test_parameter_ui_name_follows_language_and_vix_rule_label():
    settings = {
        "vix": {
            "rules": [
                {"label": "low", "multiplier": 4.0},
                {"label": "normal", "multiplier": 1.0},
            ]
        }
    }

    assert _parameter_ui_name("trend.short_window", settings, "zh") == "短期均线"
    assert _parameter_ui_name("trend.short_window", settings, "en") == "Short moving average"
    assert _parameter_ui_name("vix.rules.0.multiplier", settings, "zh") == "low 系数"
    assert _parameter_ui_name("vix.rules.0.multiplier", settings, "en") == "low multiplier"


def test_streamlit_page_title_uses_leolrs_name():
    source = open("trend_system/gui.py", encoding="utf-8").read()

    assert 'st.title("LEOLRS0-3")' in source
    assert "st.expander(_tr(language, \"区段无新高锁仓模块\"" in source
    assert "st.expander(_tr(language, \"趋势质量模块\"" in source
    assert "st.expander(_tr(language, \"回撤风险模块\"" in source
    assert "st.expander(_tr(language, \"VIX 风险模块\"" in source
    assert "美股指数 0 到 3 倍动态交易系统" not in source
    assert "US Index 0x to 3x Dynamic Trading System" not in source


def test_config_options_switch_between_profile_packages(monkeypatch, tmp_path):
    default_path = tmp_path / "settings.toml"
    profile_dir = tmp_path / "profiles"
    conservative_path = profile_dir / "Conservative.toml"
    aggressive_path = profile_dir / "Aggressive.toml"
    base = {
        "ui": {"language": "zh"},
        "profile": {"name": "Default", "home_timezone": "Pacific/Auckland", "base_currency": "NZD"},
        "backtest": {"start": "2010-01-01"},
        "position": {"min_exposure": 100.0, "max_exposure": 300.0},
    }
    conservative = {
        **base,
        "profile": {"name": "Conservative", "home_timezone": "Pacific/Auckland", "base_currency": "NZD"},
        "position": {"min_exposure": 0.0, "max_exposure": 100.0},
    }
    aggressive = {
        **base,
        "ui": {"language": "en"},
        "profile": {"name": "Aggressive", "home_timezone": "America/New_York", "base_currency": "USD"},
        "position": {"min_exposure": 100.0, "max_exposure": 300.0},
    }
    _save_config(default_path, base)
    _save_config(conservative_path, conservative)
    _save_config(aggressive_path, aggressive)
    monkeypatch.setattr("trend_system.gui.DEFAULT_CONFIG", str(default_path))
    monkeypatch.setattr("trend_system.gui.PROFILE_DIR", profile_dir)

    options = _config_options()
    selected_conservative = load_settings(options["Conservative"]).raw
    selected_aggressive = load_settings(options["Aggressive"]).raw

    assert options["默认配置"] == default_path
    assert selected_conservative["position"]["max_exposure"] == 100.0
    assert selected_conservative["ui"]["language"] == "zh"
    assert selected_aggressive["position"]["max_exposure"] == 300.0
    assert selected_aggressive["profile"]["home_timezone"] == "America/New_York"
    assert selected_aggressive["profile"]["base_currency"] == "USD"


def test_profile_path_sanitizes_profile_package_name(monkeypatch, tmp_path):
    monkeypatch.setattr("trend_system.gui.PROFILE_DIR", tmp_path / "profiles")

    path = _profile_path_for_name("  Safe / Growth: 2026  ")

    assert path == tmp_path / "profiles" / "Safe  Growth 2026.toml"


def test_widget_key_prefix_is_scoped_to_config_path(tmp_path):
    first = _widget_key_prefix(str(tmp_path / "first.toml"))
    second = _widget_key_prefix(str(tmp_path / "second.toml"))

    assert first.startswith("settings_")
    assert second.startswith("settings_")
    assert first != second


def test_rebalance_advice_includes_nzd_and_trade_currency_amounts(monkeypatch):
    def fake_fx_rate(source: str, target: str) -> float | None:
        rates = {
            ("NZD", "USD"): 0.6,
            ("USD", "NZD"): 1.6666666667,
        }
        return rates.get((source, target), 1.0)

    monkeypatch.setattr("trend_system.gui._fx_rate", fake_fx_rate)
    settings = {
        "profile": {"base_currency": "NZD", "home_timezone": "Pacific/Auckland"},
        "ui": {"language": "zh"},
        "execution": {
            "default_market": "us",
            "leveraged_asset": "SPXL",
        },
        "markets": {
            "us": {
                "timezone": "America/New_York",
                "regular_open": "09:30",
                "regular_close": "16:00",
            }
        },
    }
    allocation = SimpleNamespace(
        core_asset="SPXL",
        core_percent=100.0,
        leveraged_asset=None,
        leveraged_percent=0.0,
        defensive_asset="NZC.NZ",
        defensive_percent=0.0,
    )
    holdings = pd.DataFrame(
        [{"asset": "cash", "quantity": 0.0, "amount": 1000.0, "currency": "NZD"}]
    )

    operation_frame, summary_frame, notes = _build_rebalance_advice(
        holdings,
        allocation,
        settings,
        prices={},
        base_currency="NZD",
        signal_date=pd.Timestamp("2026-01-02"),
    )

    assert not notes
    spxl_summary = summary_frame[summary_frame["资产"] == "SPXL"].iloc[0]
    spxl_operation = operation_frame[operation_frame["资产"] == "SPXL"].iloc[0]
    assert spxl_summary["操作货币"] == "USD"
    assert spxl_summary["目标市值(NZD)"] == 1000.0
    assert spxl_summary["目标市值(USD)"] == 600.0
    assert spxl_operation["金额(NZD)"] == 1000.0
    assert spxl_operation["金额(USD)"] == 600.0
