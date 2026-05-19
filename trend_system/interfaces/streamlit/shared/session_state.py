from __future__ import annotations

import streamlit as st


class SessionKeys:
    """Canonical Streamlit session_state keys for the rebuilt shell."""

    UI_LANGUAGE = "ui_language"
    UI_THEME = "ui_theme"
    UI_THEME_MODE = "ui_theme_mode"
    BROWSER_THEME = "browser_theme"
    HOME_TIMEZONE = "home_timezone"
    BASE_CURRENCY = "base_currency"

    MOBILE_UI_LANGUAGE = "app_shell_mobile_language"
    MOBILE_UI_THEME = "app_shell_mobile_theme"
    SHELL_UI_LANGUAGE = "shell_ui_language"
    SETTINGS_UI_LANGUAGE = "settings_ui_language"
    SETTINGS_UI_THEME = "settings_ui_theme"
    SETTINGS_HOME_TIMEZONE = "settings_home_timezone"
    SETTINGS_BASE_CURRENCY = "settings_base_currency"

    SHELL_ACTIVE_PAGE = "app_shell_active_page"
    SETTINGS_PENDING_DELETE = "settings_pending_delete"

    DAILY_TIMELINE_MODE = "daily_timeline_mode"
    DAILY_START_ANCHOR = "daily_start_anchor"
    DAILY_RESULT = "daily_result"
    DAILY_PRICES = "daily_prices"
    DAILY_FINGERPRINT = "daily_fingerprint"

    MARKET_HEALTH_PRICE = "market_health_price"
    MARKET_HEALTH_SYMBOL = "market_health_symbol"
    MARKET_HEALTH_DISPLAY_START = "market_health_display_start"

    BACKTEST_RESULT = "backtest_result"
    BACKTEST_FINGERPRINT = "backtest_fingerprint"
    EQUITY_CHART_RESET = "backtest_equity_chart_reset"
    EXPOSURE_CHART_RESET = "backtest_exposure_chart_reset"

    PARAMETER_SWEEP = "backtest_parameter_sweep"
    SWEEP_TARGET_DATE = "parameter_sweep_target_date"
    SWEEP_MONTHS_BEFORE = "parameter_sweep_months_before"
    SWEEP_MONTHS_AFTER = "parameter_sweep_months_after"
    SWEEP_SORT_METRIC = "parameter_sweep_sort_metric"


def migrate_legacy_keys() -> None:
    """Keep older UI sessions working while Phase 2 key names settle."""

    legacy_pairs = (
        ("equity_chart_reset", SessionKeys.EQUITY_CHART_RESET),
        ("exposure_chart_reset", SessionKeys.EXPOSURE_CHART_RESET),
        ("parameter_sweep", SessionKeys.PARAMETER_SWEEP),
    )
    for legacy_key, current_key in legacy_pairs:
        if legacy_key in st.session_state and current_key not in st.session_state:
            st.session_state[current_key] = st.session_state.pop(legacy_key)


def get_value(key: str, default=None):
    return st.session_state.get(key, default)


def set_value(key: str, value) -> None:
    st.session_state[key] = value


def pop_value(key: str, default=None):
    return st.session_state.pop(key, default)


def has_value(key: str) -> bool:
    return key in st.session_state
