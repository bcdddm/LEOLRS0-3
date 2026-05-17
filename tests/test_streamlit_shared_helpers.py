from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from trend_system.interfaces.streamlit.shared import SessionKeys
from trend_system.interfaces.streamlit.shared.release_notes import (
    release_notes_path,
    release_notes_text,
)
from trend_system.interfaces.streamlit.shared.preparing import preparing_markup
from trend_system.interfaces.streamlit.shared import session_state as session_state_module
from trend_system.interfaces.streamlit.shared.state import fingerprint
from trend_system.interfaces.streamlit.shared.theme import theme_override_text
from trend_system.interfaces.streamlit.shared.text import option_index, tr


def test_shared_text_helpers_cover_translation_and_fallback_index():
    assert tr("en", "中文", "English") == "English"
    assert tr("zh", "中文", "English") == "中文"
    assert option_index(["a", "b"], "b") == 1
    assert option_index(["a", "b"], "missing") == 0


def test_preparing_markup_uses_translated_title_and_theme_classes():
    markup = preparing_markup("zh")

    assert "准备中" in markup
    assert "leolrs-dot-blue" in markup
    assert "leolrs-dot-green" in markup
    assert "leolrs-dot-red" in markup


def test_shared_release_notes_prefers_english_when_available(tmp_path: Path):
    zh = tmp_path / "CHANGELOG.md"
    en = tmp_path / "CHANGELOG.en.md"
    zh.write_text("中文日志", encoding="utf-8")
    en.write_text("English log", encoding="utf-8")

    assert release_notes_path("en", changelog_path=zh, changelog_en_path=en) == en
    assert release_notes_text("en", changelog_path=zh, changelog_en_path=en) == "English log"


def test_shared_release_notes_falls_back_to_default_file(tmp_path: Path):
    zh = tmp_path / "CHANGELOG.md"
    en = tmp_path / "CHANGELOG.en.md"
    zh.write_text("中文日志", encoding="utf-8")

    assert release_notes_path("en", changelog_path=zh, changelog_en_path=en) == zh
    assert release_notes_text("en", changelog_path=zh, changelog_en_path=en) == "中文日志"


def test_fingerprint_ignores_chart_only_backtest_toggles():
    base = {
        "backtest": {
            "show_leveraged_buy_hold": True,
            "show_ma120_timing": True,
            "show_leveraged_ma120_timing": False,
            "execution_timing": "next_session",
        },
        "ui": {"language": "zh"},
    }
    changed = {
        "backtest": {
            "show_leveraged_buy_hold": False,
            "show_ma120_timing": False,
            "show_leveraged_ma120_timing": True,
            "execution_timing": "next_session",
        },
        "ui": {"language": "zh"},
    }

    assert fingerprint(base, {"start": "2026-01-01"}) == fingerprint(changed, {"start": "2026-01-01"})


def test_session_keys_match_historical_streamlit_state_names():
    assert SessionKeys.UI_LANGUAGE == "ui_language"
    assert SessionKeys.UI_THEME == "ui_theme"
    assert SessionKeys.HOME_TIMEZONE == "home_timezone"
    assert SessionKeys.BASE_CURRENCY == "base_currency"
    assert SessionKeys.HEADER_UI_LANGUAGE == "header_ui_language"
    assert SessionKeys.HEADER_UI_THEME == "header_ui_theme"
    assert SessionKeys.SETTINGS_UI_LANGUAGE == "settings_ui_language"
    assert SessionKeys.SETTINGS_UI_THEME == "settings_ui_theme"
    assert SessionKeys.SETTINGS_HOME_TIMEZONE == "settings_home_timezone"
    assert SessionKeys.SETTINGS_BASE_CURRENCY == "settings_base_currency"
    assert SessionKeys.SHELL_ACTIVE_PAGE == "app_shell_active_page"
    assert SessionKeys.SETTINGS_PENDING_DELETE == "settings_pending_delete"
    assert SessionKeys.DAILY_TIMELINE_MODE == "daily_timeline_mode"
    assert SessionKeys.DAILY_RESULT == "daily_result"
    assert SessionKeys.DAILY_PRICES == "daily_prices"
    assert SessionKeys.DAILY_FINGERPRINT == "daily_fingerprint"
    assert SessionKeys.MARKET_HEALTH_PRICE == "market_health_price"
    assert SessionKeys.MARKET_HEALTH_SYMBOL == "market_health_symbol"
    assert SessionKeys.MARKET_HEALTH_DISPLAY_START == "market_health_display_start"
    assert SessionKeys.BACKTEST_RESULT == "backtest_result"
    assert SessionKeys.BACKTEST_FINGERPRINT == "backtest_fingerprint"
    assert SessionKeys.EQUITY_CHART_RESET == "backtest_equity_chart_reset"
    assert SessionKeys.EXPOSURE_CHART_RESET == "backtest_exposure_chart_reset"
    assert SessionKeys.PARAMETER_SWEEP == "backtest_parameter_sweep"
    assert SessionKeys.SWEEP_TARGET_DATE == "parameter_sweep_target_date"
    assert SessionKeys.SWEEP_MONTHS_BEFORE == "parameter_sweep_months_before"
    assert SessionKeys.SWEEP_MONTHS_AFTER == "parameter_sweep_months_after"
    assert SessionKeys.SWEEP_SORT_METRIC == "parameter_sweep_sort_metric"


def test_migrate_legacy_keys_promotes_old_session_state_names(monkeypatch):
    fake_state = {
        "equity_chart_reset": 3,
        "exposure_chart_reset": 5,
        "parameter_sweep": {"status": "ready"},
    }
    monkeypatch.setattr(session_state_module, "st", SimpleNamespace(session_state=fake_state))

    session_state_module.migrate_legacy_keys()

    assert fake_state[SessionKeys.EQUITY_CHART_RESET] == 3
    assert fake_state[SessionKeys.EXPOSURE_CHART_RESET] == 5
    assert fake_state[SessionKeys.PARAMETER_SWEEP] == {"status": "ready"}
    assert "equity_chart_reset" not in fake_state
    assert "exposure_chart_reset" not in fake_state
    assert "parameter_sweep" not in fake_state


def test_theme_override_text_converts_data_theme_rules_to_root_overrides():
    dark_css = theme_override_text("dark")
    light_css = theme_override_text("light")

    assert ":root" in dark_css
    assert '[data-theme="dark"]' not in dark_css
    assert "rgba(244, 240, 232, 0.92)" in dark_css
    assert ":root" in light_css
    assert '[data-theme="light"]' not in light_css
    assert "#0A0C0D" in light_css
    assert "--leo-surface-a:    rgba(244, 240, 232, 0.25);" in light_css
    assert "--leo-page-bg:      #F5F1EB;" in light_css
    assert "--leo-sidebar-bg:   rgba(244, 240, 232, 0.55);" in light_css
