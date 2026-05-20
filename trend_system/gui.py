from __future__ import annotations

from io import BytesIO
from copy import deepcopy
from datetime import date, datetime, timedelta
import hashlib
import html
from pathlib import Path
import re
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import toml
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Line, String
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from trend_system.backtest import run_backtest
from trend_system import __version__
from trend_system.config import Settings, load_settings, required_symbols
from trend_system.data import download_prices
from trend_system.adapters.github.content_store import GitHubRepoConfig, delete_file, push_text_file
from trend_system.adapters.github.workflow_store import (
    DEFAULT_NZ_TIME,
    DEFAULT_PUSH_CONFIG,
    DEFAULT_US_TIME,
    read_push_config,
    update_push_config,
)
from trend_system.exposure_rules import (
    apply_foreign_asset_cap_to_values,
    counts_toward_foreign_cap,
)
from trend_system.interfaces.streamlit.components import (
    render_info_panel,
    render_section_head,
    render_sidebar_control_cluster,
    render_sidebar_section_plate,
    render_strategy_console_intro,
)
from trend_system.models import BacktestRequest, DailySignalRequest, HealthcheckRequest
from trend_system.interfaces.streamlit.app_shell import render_app_shell, render_sidebar_navigation
from trend_system.interfaces.streamlit.pages.market_health_page import (
    MarketHealthPageDeps,
    render_market_health_page as render_market_health_page_module,
)
from trend_system.interfaces.streamlit.pages.daily_page import (
    DailyPageDeps,
    render_daily_page as render_daily_page_module,
)
from trend_system.interfaces.streamlit.pages.backtest_page import (
    BacktestPageDeps,
    render_backtest_page as render_backtest_page_module,
)
from trend_system.interfaces.streamlit.pages.settings_page import (
    SettingsPageDeps,
    render_settings_page as render_settings_page_module,
)
from trend_system.interfaces.streamlit.shared import (
    SessionKeys,
    fingerprint as shared_fingerprint,
    inject_styles as shared_inject_styles,
    is_stale as shared_is_stale,
    migrate_legacy_keys as shared_migrate_legacy_keys,
    option_index as shared_option_index,
    render_theme_bridge as shared_render_theme_bridge,
    release_notes_path as shared_release_notes_path,
    release_notes_text as shared_release_notes_text,
    render_lightweight_chart as shared_render_lightweight_chart,
    render_release_notes as shared_render_release_notes,
    resolve_theme as shared_resolve_theme,
    resolve_theme_mode as shared_resolve_theme_mode,
    tr as shared_tr,
    ui_language as shared_ui_language,
)
from trend_system.interfaces.streamlit.shared.theme import _normalize_theme, _normalize_theme_mode
from trend_system.interfaces.streamlit.shared.cobe_globe import build_cobe_globe_html
from trend_system.portfolio import build_allocation
from trend_system.services.backtest_service import run_backtest_use_case
from trend_system.services.daily_signal_service import run_daily_signal
from trend_system.services.healthcheck_service import run_healthcheck
from trend_system.trade_timeline import (
    NEXT_SESSION_MODE,
    SAME_CLOSE_MODE,
    NZ_CLOSE_US_OPEN_MODE,
    SUPPORTED_TIMELINE_MODES,
    trade_timeline_items,
)
from trend_system.timezones import market_window


APP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = APP_ROOT / "config/settings.toml"
PROFILE_DIR = APP_ROOT / "config/profiles"
CHANGELOG_PATH = APP_ROOT / "docs/CHANGELOG.md"
CHANGELOG_EN_PATH = APP_ROOT / "docs/CHANGELOG.en.md"
BACKTEST_MIN_DATE = date(1990, 1, 1)
BACKTEST_MAX_DATE = date(2036, 12, 31)
BACKTEST_PRESETS = {
    "自定义": None,
    "2000-01-01 到 2010-01-01": (date(2000, 1, 1), date(2010, 1, 1)),
    "2010-01-01 到现在": (date(2010, 1, 1), date.today()),
    "2021-01-01 到 2023-12-31": (date(2021, 1, 1), date(2023, 12, 31)),
    "2000-01-01 到现在": (date(2000, 1, 1), date.today()),
}
CURRENCIES = ["NZD", "USD", "AUD", "CNY"]


def _ui_language(settings: dict[str, Any]) -> str:
    return shared_ui_language(settings)


def _tr(language: str, zh: str, en: str) -> str:
    return shared_tr(language, zh, en)


def _as_settings(settings: dict[str, Any]) -> Settings:
    return Settings(raw=settings, path=DEFAULT_CONFIG)


def _apply_session_preferences(settings: dict[str, Any]) -> None:
    ui = settings.setdefault("ui", {})
    profile = settings.setdefault("profile", {})

    def _language_value(value: Any) -> str:
        if value == "EN":
            return "en"
        if value == "中文":
            return "zh"
        return str(value) if str(value) in {"en", "zh"} else "zh"

    if SessionKeys.SETTINGS_UI_LANGUAGE in st.session_state:
        st.session_state[SessionKeys.UI_LANGUAGE] = _language_value(st.session_state[SessionKeys.SETTINGS_UI_LANGUAGE])
    if SessionKeys.SHELL_UI_LANGUAGE in st.session_state:
        st.session_state[SessionKeys.UI_LANGUAGE] = _language_value(st.session_state[SessionKeys.SHELL_UI_LANGUAGE])
    if SessionKeys.MOBILE_UI_LANGUAGE in st.session_state:
        st.session_state[SessionKeys.UI_LANGUAGE] = _language_value(st.session_state[SessionKeys.MOBILE_UI_LANGUAGE])
    if SessionKeys.SETTINGS_UI_THEME in st.session_state:
        normalized_mode = _normalize_theme_mode(st.session_state[SessionKeys.SETTINGS_UI_THEME]) or "dark"
        st.session_state[SessionKeys.UI_THEME_MODE] = normalized_mode
        manual_theme = _normalize_theme(normalized_mode)
        if manual_theme is not None:
            st.session_state[SessionKeys.UI_THEME] = manual_theme
    if SessionKeys.SETTINGS_HOME_TIMEZONE in st.session_state:
        st.session_state[SessionKeys.HOME_TIMEZONE] = st.session_state[SessionKeys.SETTINGS_HOME_TIMEZONE]
    if SessionKeys.SETTINGS_BASE_CURRENCY in st.session_state:
        st.session_state[SessionKeys.BASE_CURRENCY] = st.session_state[SessionKeys.SETTINGS_BASE_CURRENCY]
    if SessionKeys.UI_LANGUAGE in st.session_state:
        ui["language"] = st.session_state[SessionKeys.UI_LANGUAGE]
    if SessionKeys.UI_THEME_MODE in st.session_state:
        ui["theme"] = st.session_state[SessionKeys.UI_THEME_MODE]
    elif SessionKeys.UI_THEME in st.session_state:
        ui["theme"] = st.session_state[SessionKeys.UI_THEME]
    if SessionKeys.HOME_TIMEZONE in st.session_state:
        profile["home_timezone"] = st.session_state[SessionKeys.HOME_TIMEZONE]
    if SessionKeys.BASE_CURRENCY in st.session_state:
        profile["base_currency"] = st.session_state[SessionKeys.BASE_CURRENCY]


def main() -> None:
    st.set_page_config(
        page_title="LEOLRS0-3",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    shared_migrate_legacy_keys()
    sidebar_nav_slot = st.sidebar.empty()
    config_options = _config_options()
    selected_config = st.sidebar.selectbox(
        "配置文件包",
        list(config_options.keys()),
        format_func=lambda name: f"{name} ({config_options[name]})" if name == "自定义路径" else name,
    )
    if selected_config == "自定义路径":
        config_path = st.sidebar.text_input("配置文件路径", str(DEFAULT_CONFIG))
    else:
        config_path = str(config_options[selected_config])
    st.sidebar.caption(f"当前配置：{Path(config_path).resolve()}")
    settings = load_settings(config_path)
    working_settings = deepcopy(settings.raw)

    # ── Streamlit → App sync ─────────────────────────────────────────────────
    # Detect when the user changes Streamlit's native theme via the hamburger
    # menu and propagate it to the app's own settings widget.
    try:
        _st_native = _normalize_theme(st.context.theme.type)
    except Exception:
        _st_native = None

    _last_st_native = _normalize_theme(st.session_state.get("_last_st_native_type"))
    _last_settings_theme = _normalize_theme_mode(st.session_state.get("_last_settings_ui_theme"))
    _curr_settings_theme = _normalize_theme_mode(st.session_state.get(SessionKeys.SETTINGS_UI_THEME))
    _current_mode = _normalize_theme_mode(st.session_state.get(SessionKeys.UI_THEME_MODE)) or "dark"

    # Settings widget just changed in this rerun (user picked from settings page)
    _settings_just_changed = (
        _last_settings_theme is not None
        and _curr_settings_theme != _last_settings_theme
    )

    # Streamlit's native theme changed AND it wasn't triggered by our JS sync
    if (
        _st_native is not None
        and _last_st_native is not None
        and _st_native != _last_st_native
        and not _settings_just_changed
        and _current_mode in ("light", "dark")
        and _st_native != _current_mode
    ):
        st.session_state[SessionKeys.SETTINGS_UI_THEME] = _st_native
        st.session_state[SessionKeys.UI_THEME_MODE] = _st_native
    # ─────────────────────────────────────────────────────────────────────────

    _apply_session_preferences(working_settings)
    resolved_theme_mode = shared_resolve_theme_mode(working_settings)

    resolved_theme = shared_resolve_theme(working_settings)
    st.session_state[SessionKeys.UI_THEME_MODE] = resolved_theme_mode
    st.session_state[SessionKeys.UI_THEME] = resolved_theme
    shared_render_theme_bridge(resolved_theme_mode)
    shared_inject_styles(resolved_theme)

    # Save comparison values for the next rerun
    st.session_state["_last_st_native_type"] = _st_native
    st.session_state["_last_settings_ui_theme"] = st.session_state.get(SessionKeys.SETTINGS_UI_THEME)
    # ─────────────────────────────────────────────────────────────────────────
    working_settings = _settings_sidebar(working_settings, config_path)
    language = _ui_language(working_settings)
    render_sidebar_navigation(
        sidebar_nav_slot,
        language=language,
        daily_renderer=_daily_tab,
        market_health_renderer=_market_health_tab,
        backtest_renderer=_backtest_tab,
        settings_renderer=_settings_tab,
    )
    _render_shell_header(working_settings, language)
    _render_global_cobe_globe_background(working_settings)

    render_app_shell(
        settings=working_settings,
        language=language,
        config_path=config_path,
        daily_renderer=_daily_tab,
        market_health_renderer=_market_health_tab,
        backtest_renderer=_backtest_tab,
        settings_renderer=_settings_tab,
    )


def _render_shell_header(settings: dict[str, Any], language: str) -> None:
    current_language_label = "EN" if language == "en" else "中文"
    st.session_state[SessionKeys.SHELL_UI_LANGUAGE] = current_language_label
    title_cols = st.columns([1, 0.42], vertical_alignment="center")
    title_cols[0].markdown(
        f"""
<div class="shell-title-band">
  <div class="shell-title">LEOLRS0-3</div>
</div>
""",
        unsafe_allow_html=True,
    )
    title_cols[1].segmented_control(
        "Language",
        ["EN", "中文"],
        default=current_language_label,
        key=SessionKeys.SHELL_UI_LANGUAGE,
        label_visibility="collapsed",
        width="stretch",
    )

def _active_background_markets(settings: dict[str, Any]) -> set[str]:
    now = pd.Timestamp.now(tz=settings["profile"]["home_timezone"]).to_pydatetime()
    active: set[str] = set()
    for market in ("us", "asx", "nzx"):
        local_open, local_close = _relevant_local_window(settings, market, now)
        if local_open <= now <= local_close:
            active.add(market)
    return active


def _render_global_cobe_globe_background(settings: dict[str, Any]) -> None:
    theme = shared_resolve_theme(settings)
    active_markets = _active_background_markets(settings)
    globe_size = 980
    top = "52%" if theme == "dark" else "54%"
    right = "clamp(-360px, -11vw, -140px)" if theme == "dark" else "clamp(-340px, -10vw, -120px)"
    opacity = "0.58" if theme == "dark" else "0.42"
    st.markdown(
        f"""
<style>
.stApp {{
  isolation: isolate;
}}
[data-testid="stSidebar"] > div:first-child {{
  height: 100vh !important;
  overflow-y: auto !important;
  overscroll-behavior: contain;
}}
[data-testid="stMain"],
[data-testid="stMainBlockContainer"],
.main .block-container,
[data-testid="stSidebar"] {{
  position: relative;
  z-index: 2;
}}
[class*="st-key-global_cobe_globe_bg"] {{
  position: fixed;
  top: {top};
  right: {right};
  transform: translateY(-50%);
  width: {globe_size}px;
  height: {globe_size}px;
  z-index: 0;
  opacity: {opacity};
  pointer-events: none;
  overflow: visible;
}}
[class*="st-key-global_cobe_globe_bg"] iframe {{
  background: transparent !important;
  border: 0 !important;
  pointer-events: none;
  width: {globe_size}px !important;
  height: {globe_size}px !important;
}}
@media (max-width: 900px) {{
  [class*="st-key-global_cobe_globe_bg"] {{
    top: 60%;
    right: -440px;
    width: {globe_size}px;
    height: {globe_size}px;
    opacity: {"0.42" if theme == "dark" else "0.28"};
  }}
}}
</style>
""",
        unsafe_allow_html=True,
    )
    try:
        with st.container(key="global_cobe_globe_bg"):
            components.html(
                build_cobe_globe_html(active_markets, theme=theme, size=globe_size),
                height=globe_size,
                scrolling=False,
            )
    except Exception:
        pass


def _normalize_trend_windows(short: int, medium: int, long: int) -> tuple[int, int, int]:
    ordered = sorted((int(short), int(medium), int(long)))
    return ordered[0], ordered[1], ordered[2]


def _render_sidebar_console_intro(settings: dict[str, Any], language: str) -> None:
    execution = settings["execution"]
    position = settings["position"]
    trend = settings["trend"]
    chips = [
        f"Market {str(execution.get('default_market', 'us')).upper()}",
        _tr(language, f"{float(position.get('min_exposure', 0)):.0f}% -> {float(position.get('max_exposure', 0)):.0f}% 仓位", f"{float(position.get('min_exposure', 0)):.0f}% -> {float(position.get('max_exposure', 0)):.0f}% exposure"),
        f"MA {trend.get('short_window')} / {trend.get('medium_window')} / {trend.get('long_window')}",
        _tr(language, "杠杆开启" if execution.get("allow_leverage", False) else "杠杆关闭", "Leverage on" if execution.get("allow_leverage", False) else "Leverage off"),
        _tr(language, "高级模块待命", "Advanced overlays ready"),
    ]
    render_strategy_console_intro(
        st,
        title=_tr(language, "策略控制台", "Strategy Console"),
        note=_tr(
            language,
            "先看控制台，再深入每一组参数。这个面板开始按决策意图，而不是按原始配置文件来理解。",
            "Scan the control deck first, then dive into each parameter group. This panel now starts to read by decision intent, not by raw config order.",
        ),
        chips=chips,
    )

def _settings_sidebar(settings: dict[str, Any], config_path: str) -> dict[str, Any]:
    key_prefix = _widget_key_prefix(config_path)
    with st.sidebar.form("settings_form"):
        language = _ui_language(settings)
        st.header(_tr(language, "策略参数", "Strategy Parameters"))
        _render_sidebar_console_intro(settings, language)

        execution = settings["execution"]
        render_sidebar_section_plate(
            st,
            overline=_tr(language, "第一组", "Group One"),
            title=_tr(language, "Session & Market Context", "Session & Market Context"),
            summary=_tr(language, "先定义执行市场、本地与海外资产边界，再让后续信号有明确的执行语境。", "Define market selection and account asset boundaries first so every later signal has a clear execution context."),
        )
        st.subheader(_tr(language, "执行资产与账户限制", "Execution Assets and Account Limits"))
        execution["default_market"] = st.radio(
            _tr(language, "执行市场", "Execution market"),
            ["us", "asx"],
            index=_option_index(["us", "asx"], execution.get("default_market", "us")),
            horizontal=True,
            key=f"{key_prefix}_execution_default_market",
        )
        execution["core_asset"] = st.text_input(
            _tr(language, "美股核心资产", "US core asset"),
            execution["core_asset"],
            key=f"{key_prefix}_execution_core_asset",
        )
        st.caption(_tr(language, "美股执行时的核心 S&P 500 持仓，例如 VOO。", "Core S&P 500 holding for US execution, for example VOO."))
        execution["asx_core_asset"] = st.text_input(
            _tr(language, "ASX 核心资产", "ASX core asset"),
            execution["asx_core_asset"],
            key=f"{key_prefix}_execution_asx_core_asset",
        )
        st.caption(_tr(language, "澳洲市场执行时的核心 S&P 500 持仓，例如 IVV.AX。", "Core S&P 500 holding for ASX execution, for example IVV.AX."))
        execution["leveraged_asset"] = st.text_input(
            _tr(language, "杠杆资产", "Leveraged asset"),
            execution["leveraged_asset"],
            key=f"{key_prefix}_execution_leveraged_asset",
        )
        st.caption(_tr(language, "用于放大等效仓位的 3x ETF。调高仓位时系统会逐步增加它的比例。", "3x ETF used to increase equivalent exposure gradually."))
        execution["defensive_asset"] = st.text_input(
            _tr(language, "防御资产", "Defensive asset"),
            execution["defensive_asset"],
            key=f"{key_prefix}_execution_defensive_asset",
        )
        st.caption(_tr(language, "默认防御资产。建议用本地现金 ETF，例如新西兰 NZC.NZ 或澳洲 BILL.AX。", "Default defensive asset. A local cash ETF such as NZC.NZ or BILL.AX is preferred."))
        execution["nz_defensive_asset"] = st.text_input(
            _tr(language, "新西兰本地现金ETF", "New Zealand local cash ETF"),
            execution.get("nz_defensive_asset", "NZC.NZ"),
            key=f"{key_prefix}_execution_nz_defensive_asset",
        )
        st.caption(_tr(language, "新西兰本地现金/短债类 ETF。当前默认 NZC.NZ。", "New Zealand local cash or short-duration bond ETF. Default is NZC.NZ."))
        execution["au_defensive_asset"] = st.text_input(
            _tr(language, "澳洲本地现金ETF", "Australia local cash ETF"),
            execution.get("au_defensive_asset", "BILL.AX"),
            key=f"{key_prefix}_execution_au_defensive_asset",
        )
        st.caption(_tr(language, "澳洲本地现金类 ETF。当前默认 BILL.AX。", "Australia local cash ETF. Default is BILL.AX."))
        execution["limit_foreign_assets_nzd_value"] = st.toggle(
            _tr(language, "海外/FIF资产折合NZD不超过50,000", "Cap foreign/FIF assets at 50,000 NZD"),
            bool(
                execution.get(
                    "limit_foreign_assets_nzd_value",
                    execution.get("limit_usd_assets_nzd_value", False),
                )
            ),
            key=f"{key_prefix}_execution_limit_foreign_assets_nzd_value",
        )
        execution["foreign_assets_nzd_limit"] = st.number_input(
            _tr(language, "海外/FIF资产NZD上限", "Foreign/FIF NZD limit"),
            0.0,
            10_000_000.0,
            float(
                execution.get(
                    "foreign_assets_nzd_limit",
                    execution.get("usd_assets_nzd_limit", 50000.0),
                )
            ),
            1000.0,
            key=f"{key_prefix}_execution_foreign_assets_nzd_limit",
        )
        render_info_panel(
            st,
            [
                _tr(language, "打开后，VOO、SPXL 等非 NZX/ASX 标的目标市值合计折算后不超过这个纽币金额。IVV.AX、USF.NZ 不计入此限制。", "When enabled, non-NZX/ASX targets such as VOO and SPXL are capped at this NZD value. IVV.AX and USF.NZ are excluded."),
                _tr(language, "备注：这是基于新西兰 FIF 50,000 NZD 门槛的辅助监控。部分 ASX 标的是否豁免需以 IRD 规则和实际标的为准。", "Note: this is a helper for New Zealand's 50,000 NZD FIF threshold. Confirm actual treatment with IRD rules and the fund details."),
            ],
            title=_tr(language, "海外 FIF/NZ 资产说明", "Foreign FIF/NZ asset note"),
            compact=True,
        )

        trend = settings["trend"]
        position = settings["position"]

        # ── 复合模块 ─────────────────────────────────────────────────────────
        st.divider()
        render_sidebar_section_plate(
            st,
            overline=_tr(language, "第二组", "Group Two"),
            title=_tr(language, "Signal Construction", "Signal Construction"),
            summary=_tr(language, "先定义趋势感应器与简单门控，再决定后面的主仓位引擎如何解释它们。", "Define the trend sensors and simple gate first, then let the main position engine interpret them."),
        )
        st.subheader(_tr(language, "趋势信号", "Trend Signal"))
        ma_cols = st.columns(3)
        short_window = ma_cols[0].slider(
            _tr(language, "短期均线", "Short moving average"),
            5,
            100,
            int(trend["short_window"]),
            key=f"{key_prefix}_trend_short_window",
        )
        medium_window = ma_cols[1].slider(
            _tr(language, "中期均线", "Medium moving average"),
            10,
            150,
            int(trend["medium_window"]),
            key=f"{key_prefix}_trend_medium_window",
        )
        long_window = ma_cols[2].slider(
            _tr(language, "长期均线", "Long moving average"),
            50,
            300,
            int(trend["long_window"]),
            key=f"{key_prefix}_trend_long_window",
        )
        trend["short_window"], trend["medium_window"], trend["long_window"] = _normalize_trend_windows(
            short_window,
            medium_window,
            long_window,
        )
        st.caption(_tr(language, "判断牛熊环境的主过滤器。越长越保守，越短越容易频繁切换。", "Main bull/bear environment filter. Longer is more conservative."))
        trend["confirmation_days"] = st.slider(
            _tr(language, "连续确认天数", "Confirmation days"),
            1,
            10,
            int(trend["confirmation_days"]),
            1,
            key=f"{key_prefix}_trend_confirmation_days",
        )
        st.caption(_tr(language, "要求信号连续成立多少天才确认。调高可减少假突破，但会牺牲反应速度。", "Requires a signal to hold for this many days. Higher values reduce false breaks but react slower."))

        st.divider()
        st.subheader(_tr(language, "简单模块", "Simple Module"))
        position["simple_module_enabled"] = st.toggle(
            _tr(language, "启用简单模块", "Enable simple module"),
            bool(position.get("simple_module_enabled", False)),
            help=_tr(
                language,
                "开启后，系统用双均线条件判断是否入场。可单独使用（纯简单模式），也可与复合模块同时开启（简单条件作为复合模块的入场门控）。",
                "When enabled, the system uses dual-MA conditions to gate market entry. Can be used standalone or with the composite module as an entry gate.",
            ),
            key=f"{key_prefix}_simple_module_enabled",
        )
        _composite_on = bool(position.get("composite_module_enabled", True))
        _simple_on = bool(position.get("simple_module_enabled", False))
        simple_cols = st.columns(3)
        position["simple_module_fast_ma_window"] = simple_cols[0].number_input(
            _tr(language, "快速均线窗口", "Fast MA window"),
            10,
            300,
            int(position.get("simple_module_fast_ma_window", 120)),
            5,
            help=_tr(language, "默认 120 日均线，用于判断短期方向。", "Default is 120-day MA for short-term direction."),
            key=f"{key_prefix}_simple_module_fast_ma_window",
        )
        position["simple_module_slow_ma_window"] = simple_cols[1].number_input(
            _tr(language, "慢速均线窗口", "Slow MA window"),
            10,
            300,
            int(position.get("simple_module_slow_ma_window", 200)),
            5,
            help=_tr(language, "默认 200 日均线，用于判断长期趋势。", "Default is 200-day MA for long-term trend."),
            key=f"{key_prefix}_simple_module_slow_ma_window",
        )
        position["simple_module_threshold_pct"] = simple_cols[2].number_input(
            _tr(language, "超出均线阈值 (%)", "Above-MA threshold (%)"),
            0.0,
            20.0,
            float(position.get("simple_module_threshold_pct", 2.0)),
            0.5,
            help=_tr(language, "收盘价须超出两条均线此百分比才触发。默认 2%。", "Close must exceed both MAs by this percentage to trigger. Default is 2%."),
            key=f"{key_prefix}_simple_module_threshold_pct",
        )
        simple_off_default = min(float(position.get("simple_module_off_exposure", 0.0)), 300.0)
        if _simple_on and not _composite_on:
            simple_on_default = min(float(position.get("simple_module_on_exposure", 300.0)), 300.0)
            simple_range = st.slider(
                _tr(language, "简单模块目标仓位范围 (%)", "Simple module exposure range (%)"),
                0.0,
                300.0,
                (
                    min(simple_off_default, simple_on_default),
                    max(simple_off_default, simple_on_default),
                ),
                5.0,
                help=_tr(
                    language,
                    "双滑块分别表示简单模块条件不满足时与满足时的目标仓位。",
                    "The two thumbs represent target exposure when the simple module is off and on.",
                ),
                key=f"{key_prefix}_simple_module_exposure_range",
            )
            position["simple_module_off_exposure"], position["simple_module_on_exposure"] = simple_range
        else:
            position["simple_module_off_exposure"] = st.slider(
                _tr(language, "条件不满足时的目标仓位 (%)", "Off-state target exposure (%)"),
                0.0,
                300.0,
                simple_off_default,
                5.0,
                help=_tr(
                    language,
                    "简单模块条件不满足时（价格未超过均线阈值）使用的目标仓位。",
                    "Target exposure when simple module conditions are not met (price not above MA threshold).",
                ),
                key=f"{key_prefix}_simple_module_off_exposure",
            )
        st.caption(
            _tr(
                language,
                "触发条件：快速均线在慢速均线上方，且收盘价在两条均线上方超过阈值百分比。",
                "Trigger: fast MA above slow MA, and close price more than threshold % above both MAs.",
            )
        )
        if _simple_on and _composite_on:
            st.caption(
                _tr(
                    language,
                    "两个模块同时开启：简单条件满足 → 使用复合模块完整结果；简单条件不满足 → 使用上方【条件不满足时的目标仓位】。",
                    "Both modules on: simple conditions met → full composite result; simple conditions not met → off-state target exposure above.",
                )
            )

        st.divider()
        render_sidebar_section_plate(
            st,
            overline=_tr(language, "第三组", "Group Three"),
            title=_tr(language, "Core Position Engine", "Core Position Engine"),
            summary=_tr(language, "这里决定基础仓位边界、复合引擎与 VIX 系数如何形成主要仓位姿态。", "This group shapes the base exposure range, composite engine, and VIX tiers that form the main posture."),
        )
        st.subheader(_tr(language, "复合模块", "Composite Module"))
        position["composite_module_enabled"] = st.toggle(
            _tr(language, "启用复合模块", "Enable composite module"),
            bool(position.get("composite_module_enabled", True)),
            help=_tr(
                language,
                "开启后，系统使用趋势信号、VIX 乘数和高级模块的完整计算流程确定目标仓位。与简单模块同时开启时，复合模块在简单条件满足时运行。",
                "When enabled, the full trend signal, VIX multiplier, and advanced module pipeline determines target exposure. When both modules are on, composite runs only when simple conditions are met.",
            ),
            key=f"{key_prefix}_composite_module_enabled",
        )
        st.caption(
            _tr(
                language,
                "复合模块包含以下所有参数：趋势信号均线、基础仓位边界以及 VIX 分档乘数。",
                "The composite module includes all parameters below: trend signal MAs, base exposure bounds, and VIX tier multipliers.",
            )
        )
        st.subheader(_tr(language, "基础仓位边界", "Base Exposure Bounds"))
        render_sidebar_control_cluster(
            st,
            overline=_tr(language, "主控制节点", "Primary Control Cluster"),
            title=_tr(language, "仓位地板 / 顶盖 / 调仓阈值", "Exposure floor / cap / rebalance threshold"),
            summary=_tr(
                language,
                "这一组是策略控制台裡最重要的三根推杆，决定系统愿意压到多低、拉到多高，以及变化多大才值得执行。",
                "This trio is the key control cluster in the strategy console: how low the system can compress, how high it can extend, and how much change is worth executing.",
            ),
            chips=[_tr(language, "Floor", "Floor"), _tr(language, "Cap", "Cap"), _tr(language, "Trigger", "Trigger")],
        )
        exposure_range = st.slider(
            _tr(language, "等效仓位范围", "Equivalent exposure range"),
            0.0,
            300.0,
            (
                min(float(position.get("min_exposure", 0.0)), 300.0),
                max(
                    min(float(position.get("min_exposure", 0.0)), 300.0),
                    min(float(position.get("max_exposure", 300.0)), 300.0),
                ),
            ),
            5.0,
            help=_tr(
                language,
                "双滑块分别表示最小等效仓位和最大等效仓位。",
                "The two thumbs represent the minimum and maximum equivalent exposure.",
            ),
            key=f"{key_prefix}_base_exposure_range",
        )
        position["min_exposure"], position["max_exposure"] = exposure_range
        st.caption(
            _tr(
                language,
                "这是仓位下限，不是目标仓位。实际目标 = 趋势仓位 × VIX 系数，再受这个下限保护。",
                "This is a floor, not the target. Target = trend exposure x VIX multiplier, floored here.",
            )
        )
        st.caption(_tr(language, "这是仓位上限，不是目标仓位。实际目标 = 趋势仓位 × VIX 系数，再受这个上限限制。", "This is a cap, not the target. Target = trend exposure x VIX multiplier, capped here."))
        position["rebalance_threshold"] = st.slider(
            _tr(language, "最小调仓阈值", "Minimum rebalance threshold"), 0.0, 30.0, float(position["rebalance_threshold"]), 1.0
        )
        st.caption(_tr(language, "仓位变化小于这个百分比时不调仓。调高可减少交易，调低会更贴近模型。", "Skip rebalancing when the exposure change is below this percentage."))
        position["fixed_exposure_tiers_enabled"] = st.toggle(
            _tr(language, "只使用固定仓位档位", "Use fixed exposure tiers only"),
            bool(position.get("fixed_exposure_tiers_enabled", False)),
        )
        position["fixed_exposure_tiers"] = [0.0, 100.0, 300.0]
        st.caption(
            _tr(
                language,
                "开启后，目标仓位会映射到最接近的 0%、100% 或 300%，不会停留在中间数值。",
                "When enabled, target exposure maps to the nearest 0%, 100%, or 300% tier and never stays between tiers.",
            )
        )
        st.subheader(_tr(language, "VIX 分档乘数", "VIX Tier Multipliers"))
        vix_rules = settings["vix"]["rules"]
        vix_rules_by_label = {rule["label"]: rule for rule in vix_rules}
        low_rule = vix_rules_by_label.get("low", vix_rules[0])
        normal_rule = vix_rules_by_label.get("normal", vix_rules[1])
        danger_rule = vix_rules_by_label.get("danger", vix_rules[2])
        crisis_rule = vix_rules_by_label.get("crisis", vix_rules[3])
        low_vix_upper = st.number_input(
            _tr(language, "低波动上限", "Low VIX upper bound"),
            0.0,
            80.0,
            min(80.0, float(low_rule.get("max_exclusive", 20.0))),
            0.5,
            key=f"{key_prefix}_vix_low_upper",
        )
        normal_vix_upper = st.number_input(
            _tr(language, "正常波动上限", "Normal VIX upper bound"),
            low_vix_upper + 0.5,
            80.0,
            min(80.0, max(low_vix_upper + 0.5, float(normal_rule.get("max_exclusive", 30.0)))),
            0.5,
            key=f"{key_prefix}_vix_normal_upper",
        )
        danger_vix_upper = st.number_input(
            _tr(language, "高风险上限", "Danger VIX upper bound"),
            normal_vix_upper + 0.5,
            80.0,
            min(80.0, max(normal_vix_upper + 0.5, float(danger_rule.get("max_exclusive", 40.0)))),
            0.5,
            key=f"{key_prefix}_vix_danger_upper",
        )
        low_rule.pop("min_inclusive", None)
        low_rule["max_exclusive"] = low_vix_upper
        normal_rule["min_inclusive"] = low_vix_upper
        normal_rule["max_exclusive"] = normal_vix_upper
        danger_rule["min_inclusive"] = normal_vix_upper
        danger_rule["max_exclusive"] = danger_vix_upper
        crisis_rule["min_inclusive"] = danger_vix_upper
        crisis_rule.pop("max_exclusive", None)
        st.caption(
            _tr(
                language,
                f"当前分档：VIX < {low_vix_upper:g} 为 low；{low_vix_upper:g} 到 {normal_vix_upper:g} 为 normal；{normal_vix_upper:g} 到 {danger_vix_upper:g} 为 danger；≥ {danger_vix_upper:g} 为 crisis。",
                f"Current tiers: VIX < {low_vix_upper:g} is low; {low_vix_upper:g} to {normal_vix_upper:g} is normal; {normal_vix_upper:g} to {danger_vix_upper:g} is danger; >= {danger_vix_upper:g} is crisis.",
            )
        )
        render_sidebar_control_cluster(
            st,
            overline=_tr(language, "波动引擎", "Volatility Engine"),
            title=_tr(language, "VIX 分档与乘数", "VIX thresholds and multipliers"),
            summary=_tr(
                language,
                "这段决定系统在低波动、正常和危险环境之间如何变速，是主仓位引擎后面的第一层节奏控制。",
                "This block controls how the system changes speed across low, normal, and dangerous volatility regimes. It is the first tempo control after the main exposure engine.",
            ),
            chips=[_tr(language, "Low", "Low"), _tr(language, "Normal", "Normal"), _tr(language, "Danger", "Danger"), _tr(language, "Crisis", "Crisis")],
        )
        for rule in settings["vix"]["rules"]:
            label = rule["label"]
            rule["multiplier"] = st.slider(
                _tr(language, f"{label} 系数", f"{label} multiplier"),
                0.0,
                5.0,
                float(rule["multiplier"]),
                0.05,
                key=f"{key_prefix}_vix_multiplier_{label}",
            )
            render_info_panel(st, _vix_multiplier_note(label, language), compact=True)

        st.divider()
        render_sidebar_section_plate(
            st,
            overline=_tr(language, "第四组", "Group Four"),
            title=_tr(language, "Leverage & Safety Gate", "Leverage & Safety Gate"),
            summary=_tr(language, "先定义杠杆放行条件，再进入附加安全阀与异常覆盖。", "Define leverage permission before entering the extra safety gates and exception overrides."),
        )
        st.subheader(_tr(language, "杠杆门槛", "Leverage Gates"))
        execution["allow_leverage"] = st.toggle(
            _tr(language, "允许杠杆 ETF", "Allow leveraged ETF"),
            execution["allow_leverage"],
            key=f"{key_prefix}_execution_allow_leverage",
        )
        st.caption(_tr(language, "关闭后，目标仓位即使高于 100%，也会被限制在非杠杆核心资产内。", "When off, targets above 100% are capped to unleveraged core exposure."))
        execution["leverage_only_when_vix_below"] = st.number_input(
            _tr(language, "杠杆允许 VIX 上限", "Leverage allowed below VIX"),
            0.0,
            80.0,
            min(float(execution.get("leverage_only_when_vix_below", 20.0)), 80.0),
            0.5,
            help=_tr(language, "只有 VIX 低于这个数值时，系统才允许使用杠杆 ETF。", "Leveraged ETFs are allowed only when VIX is below this value."),
            key=f"{key_prefix}_execution_leverage_only_when_vix_below",
        )
        execution["clear_leverage_when_vix_at_or_above"] = st.number_input(
            _tr(language, "杠杆清退 VIX 水平", "Clear leverage at or above VIX"),
            float(execution["leverage_only_when_vix_below"]),
            80.0,
            min(
                80.0,
                max(
                    float(execution["leverage_only_when_vix_below"]),
                    float(execution.get("clear_leverage_when_vix_at_or_above", 30.0)),
                ),
            ),
            0.5,
            help=_tr(language, "VIX 达到或高于这个数值时，系统会清掉杠杆暴露。", "When VIX reaches or exceeds this value, leveraged exposure is cleared."),
            key=f"{key_prefix}_execution_clear_leverage_when_vix_at_or_above",
        )
        st.caption(
            _tr(
                language,
                "这两个门槛只控制是否允许杠杆 ETF；基础仓位仍由趋势信号和 VIX 分档系数决定。",
                "These thresholds only control leveraged ETF permission; base exposure still comes from trend signals and VIX tiers.",
            )
        )

        st.divider()
        render_sidebar_section_plate(
            st,
            overline=_tr(language, "第五组", "Group Five"),
            title=_tr(language, "Advanced Caps & Exception Modules", "Advanced Caps & Exception Modules"),
            summary=_tr(language, "把回撤、无新高、周期涨幅、趋势质量与极端风险模块视作附加的安全阀门。", "Treat drawdown, no-new-high, period-rise, trend-quality, and extreme-risk modules as additional safety valves."),
        )
        _any_advanced = any([
            bool(position.get("vix_exposure_cap_enabled", False)),
            bool(position.get("drawdown_exposure_cap_enabled", False)),
            bool(position.get("no_new_high_cap_enabled", False)),
            bool(position.get("period_rise_cap_enabled", False)),
            bool(position.get("trend_quality_cap_enabled", False)),
            bool(position.get("trend_quality_ma_cross_slow_decline_enabled", False)),
            bool(position.get("extreme_risk_cap_enabled", False)),
        ])
        with st.expander(_tr(language, "高级模块", "Advanced Modules"), expanded=_any_advanced):
            st.caption(
                _tr(
                    language,
                    "高级模块在复合/简单模块的基础目标仓位之上进行额外的上限或地板调整，对两种基础模块同等适用。",
                    "Advanced modules apply additional caps or floor adjustments on top of the composite/simple module base target, and apply equally to both base modules.",
                )
            )

            # ── VIX 风险模块
            st.subheader(_tr(language, "VIX 风险模块", "VIX Risk Module"))
            render_sidebar_control_cluster(
                st,
                overline=_tr(language, "安全阀 A", "Safety Valve A"),
                title=_tr(language, "VIX 仓位上限曲线", "VIX exposure cap curve"),
                summary=_tr(
                    language,
                    "当波动真正升高时，这条曲线会直接压低允许的上限，比前面的乘数更像一条硬护栏。",
                    "When volatility truly rises, this curve directly compresses the allowed cap. It behaves more like a hard guardrail than the softer multipliers above.",
                ),
                chips=[_tr(language, "Cap ladder", "Cap ladder"), _tr(language, "5 bands", "5 bands")],
                tone="green",
            )
            position["vix_exposure_cap_enabled"] = st.toggle(
                _tr(language, "启用 VIX 仓位上限曲线", "Enable VIX exposure cap curve"),
                bool(position.get("vix_exposure_cap_enabled", False)),
                help=_tr(
                    language,
                    "开启后，VIX 升高会逐步压低最大允许等效仓位，例如从 300% 降到 250%、200%。",
                    "When enabled, higher VIX gradually lowers the maximum allowed equivalent exposure, for example from 300% to 250% or 200%.",
                ),
            )
            cap_rules = position.get(
                "vix_exposure_caps",
                [
                    {"max_exclusive": 18.0, "max_exposure": 300.0},
                    {"min_inclusive": 18.0, "max_exclusive": 22.0, "max_exposure": 250.0},
                    {"min_inclusive": 22.0, "max_exclusive": 26.0, "max_exposure": 200.0},
                    {"min_inclusive": 26.0, "max_exclusive": 30.0, "max_exposure": 150.0},
                    {"min_inclusive": 30.0, "max_exposure": 100.0},
                ],
            )
            while len(cap_rules) < 5:
                cap_rules.append({"max_exposure": 100.0})
            cap_1 = st.number_input(
                _tr(language, "VIX 仓位上限边界 1", "VIX exposure cap boundary 1"),
                0.0,
                80.0,
                min(80.0, float(cap_rules[0].get("max_exclusive", 18.0))),
                0.5,
            )
            cap_2 = st.number_input(
                _tr(language, "VIX 仓位上限边界 2", "VIX exposure cap boundary 2"),
                cap_1 + 0.5,
                80.0,
                min(80.0, max(cap_1 + 0.5, float(cap_rules[1].get("max_exclusive", 22.0)))),
                0.5,
            )
            cap_3 = st.number_input(
                _tr(language, "VIX 仓位上限边界 3", "VIX exposure cap boundary 3"),
                cap_2 + 0.5,
                80.0,
                min(80.0, max(cap_2 + 0.5, float(cap_rules[2].get("max_exclusive", 26.0)))),
                0.5,
            )
            cap_4 = st.number_input(
                _tr(language, "VIX 仓位上限边界 4", "VIX exposure cap boundary 4"),
                cap_3 + 0.5,
                80.0,
                min(80.0, max(cap_3 + 0.5, float(cap_rules[3].get("max_exclusive", 30.0)))),
                0.5,
            )
            cap_cols = st.columns(5)
            cap_exposures = [
                cap_cols[0].number_input(
                    _tr(language, f"VIX < {cap_1:g}", f"VIX < {cap_1:g}"),
                    0.0,
                    300.0,
                    min(300.0, max(0.0, float(cap_rules[0].get("max_exposure", 300.0)))),
                    5.0,
                ),
                cap_cols[1].number_input(
                    _tr(language, f"{cap_1:g}-{cap_2:g}", f"{cap_1:g}-{cap_2:g}"),
                    0.0,
                    300.0,
                    min(300.0, max(0.0, float(cap_rules[1].get("max_exposure", 250.0)))),
                    5.0,
                ),
                cap_cols[2].number_input(
                    _tr(language, f"{cap_2:g}-{cap_3:g}", f"{cap_2:g}-{cap_3:g}"),
                    0.0,
                    300.0,
                    min(300.0, max(0.0, float(cap_rules[2].get("max_exposure", 200.0)))),
                    5.0,
                ),
                cap_cols[3].number_input(
                    _tr(language, f"{cap_3:g}-{cap_4:g}", f"{cap_3:g}-{cap_4:g}"),
                    0.0,
                    300.0,
                    min(300.0, max(0.0, float(cap_rules[3].get("max_exposure", 150.0)))),
                    5.0,
                ),
                cap_cols[4].number_input(
                    _tr(language, f"VIX ≥ {cap_4:g}", f"VIX >= {cap_4:g}"),
                    0.0,
                    300.0,
                    min(300.0, max(0.0, float(cap_rules[4].get("max_exposure", 100.0)))),
                    5.0,
                ),
            ]
            position["vix_exposure_caps"] = [
                {"max_exclusive": cap_1, "max_exposure": cap_exposures[0]},
                {"min_inclusive": cap_1, "max_exclusive": cap_2, "max_exposure": cap_exposures[1]},
                {"min_inclusive": cap_2, "max_exclusive": cap_3, "max_exposure": cap_exposures[2]},
                {"min_inclusive": cap_3, "max_exclusive": cap_4, "max_exposure": cap_exposures[3]},
                {"min_inclusive": cap_4, "max_exposure": cap_exposures[4]},
            ]
            st.caption(
                _tr(
                    language,
                    "这条曲线会限制目标等效仓位上限；开启后，中等 VIX 可以保留部分杠杆，而不是直接从 300% 掉到 100%。",
                    "This curve caps target equivalent exposure; when enabled, moderate VIX can keep partial leverage instead of dropping directly from 300% to 100%.",
                )
            )

            st.divider()
            st.subheader(_tr(language, "回撤风险模块", "Drawdown Risk Module"))
            render_sidebar_control_cluster(
                st,
                overline=_tr(language, "安全阀 B", "Safety Valve B"),
                title=_tr(language, "回撤仓位上限曲线", "Drawdown exposure cap curve"),
                summary=_tr(
                    language,
                    "这一段处理的是慢性走弱而不是瞬时恐慌，让系统在连续失血阶段更早降低上限。",
                    "This block is for slow deterioration rather than panic spikes, helping the system lower its cap earlier during extended drawdown phases.",
                ),
                chips=[_tr(language, "Lookback", "Lookback"), _tr(language, "Cap ladder", "Cap ladder")],
                tone="green",
            )
            position["drawdown_exposure_cap_enabled"] = st.toggle(
                _tr(language, "启用回撤仓位上限曲线", "Enable drawdown exposure cap curve"),
                bool(position.get("drawdown_exposure_cap_enabled", False)),
                help=_tr(
                    language,
                    "开启后，指数从近 N 日高点回撤越深，最大允许等效仓位越低，用来防范慢性阴跌。",
                    "When enabled, deeper drawdowns from the recent N-day high lower maximum allowed equivalent exposure to reduce slow-grind losses.",
                ),
            )
            position["drawdown_lookback_days"] = st.number_input(
                _tr(language, "回撤观察窗口", "Drawdown lookback window"),
                20,
                756,
                int(position.get("drawdown_lookback_days", 252)),
                10,
                help=_tr(
                    language,
                    "用于计算最近高点的交易日窗口。252 约等于一年交易日。",
                    "Trading-day window used to calculate the recent high. 252 is roughly one trading year.",
                ),
            )
            drawdown_rules = position.get(
                "drawdown_exposure_caps",
                [
                    {"max_exclusive": 5.0, "max_exposure": 300.0},
                    {"min_inclusive": 5.0, "max_exclusive": 10.0, "max_exposure": 250.0},
                    {"min_inclusive": 10.0, "max_exclusive": 15.0, "max_exposure": 200.0},
                    {"min_inclusive": 15.0, "max_exclusive": 20.0, "max_exposure": 150.0},
                    {"min_inclusive": 20.0, "max_exposure": 100.0},
                ],
            )
            while len(drawdown_rules) < 5:
                drawdown_rules.append({"max_exposure": 100.0})
            dd_1 = st.number_input(
                _tr(language, "回撤上限边界 1", "Drawdown cap boundary 1"),
                0.0,
                80.0,
                float(drawdown_rules[0].get("max_exclusive", 5.0)),
                0.5,
            )
            dd_2 = st.number_input(
                _tr(language, "回撤上限边界 2", "Drawdown cap boundary 2"),
                dd_1 + 0.5,
                80.0,
                max(dd_1 + 0.5, float(drawdown_rules[1].get("max_exclusive", 10.0))),
                0.5,
            )
            dd_3 = st.number_input(
                _tr(language, "回撤上限边界 3", "Drawdown cap boundary 3"),
                dd_2 + 0.5,
                80.0,
                max(dd_2 + 0.5, float(drawdown_rules[2].get("max_exclusive", 15.0))),
                0.5,
            )
            dd_4 = st.number_input(
                _tr(language, "回撤上限边界 4", "Drawdown cap boundary 4"),
                dd_3 + 0.5,
                80.0,
                max(dd_3 + 0.5, float(drawdown_rules[3].get("max_exclusive", 20.0))),
                0.5,
            )
            drawdown_cols = st.columns(5)
            drawdown_exposures = [
                drawdown_cols[0].number_input(
                    _tr(language, f"回撤 < {dd_1:g}%", f"Drawdown < {dd_1:g}%"),
                    0.0,
                    300.0,
                    min(300.0, max(0.0, float(drawdown_rules[0].get("max_exposure", 300.0)))),
                    5.0,
                ),
                drawdown_cols[1].number_input(
                    _tr(language, f"{dd_1:g}%-{dd_2:g}%", f"{dd_1:g}%-{dd_2:g}%"),
                    0.0,
                    300.0,
                    min(300.0, max(0.0, float(drawdown_rules[1].get("max_exposure", 250.0)))),
                    5.0,
                ),
                drawdown_cols[2].number_input(
                    _tr(language, f"{dd_2:g}%-{dd_3:g}%", f"{dd_2:g}%-{dd_3:g}%"),
                    0.0,
                    300.0,
                    min(300.0, max(0.0, float(drawdown_rules[2].get("max_exposure", 200.0)))),
                    5.0,
                ),
                drawdown_cols[3].number_input(
                    _tr(language, f"{dd_3:g}%-{dd_4:g}%", f"{dd_3:g}%-{dd_4:g}%"),
                    0.0,
                    300.0,
                    min(300.0, max(0.0, float(drawdown_rules[3].get("max_exposure", 150.0)))),
                    5.0,
                ),
                drawdown_cols[4].number_input(
                    _tr(language, f"回撤 ≥ {dd_4:g}%", f"Drawdown >= {dd_4:g}%"),
                    0.0,
                    300.0,
                    min(300.0, max(0.0, float(drawdown_rules[4].get("max_exposure", 100.0)))),
                    5.0,
                ),
            ]
            position["drawdown_exposure_caps"] = [
                {"max_exclusive": dd_1, "max_exposure": drawdown_exposures[0]},
                {"min_inclusive": dd_1, "max_exclusive": dd_2, "max_exposure": drawdown_exposures[1]},
                {"min_inclusive": dd_2, "max_exclusive": dd_3, "max_exposure": drawdown_exposures[2]},
                {"min_inclusive": dd_3, "max_exclusive": dd_4, "max_exposure": drawdown_exposures[3]},
                {"min_inclusive": dd_4, "max_exposure": drawdown_exposures[4]},
            ]
            st.caption(
                _tr(
                    language,
                    "这条曲线按指数从近期高点的回撤限制最大仓位；它和 VIX 曲线会共同取更保守的上限。",
                    "This curve caps exposure by the index drawdown from its recent high; it combines with the VIX curve by taking the more conservative cap.",
                )
            )

            st.divider()
            st.subheader(_tr(language, "区段无新高锁仓模块", "Windowed No-New-High Lock Module"))
            render_sidebar_control_cluster(
                st,
                overline=_tr(language, "安全阀 C", "Safety Valve C"),
                title=_tr(language, "区段无新高锁仓", "Windowed no-new-high lock"),
                summary=_tr(
                    language,
                    "这段针对的是长期修复不足的市场，即便短线没崩，也可以因为迟迟不创新高而压低允许仓位。",
                    "This valve targets markets that fail to repair over time, lowering allowed exposure when price action cannot make fresh highs for too long.",
                ),
                chips=[_tr(language, "Observation", "Observation"), _tr(language, "High window", "High window")],
                tone="green",
            )
            position["no_new_high_cap_enabled"] = st.toggle(
                _tr(
                    language,
                    "如果观察期内没有创区段新高，则锁定仓位",
                    "Lock exposure if the observation window has no windowed new high",
                ),
                bool(position.get("no_new_high_cap_enabled", False)),
                help=_tr(
                    language,
                    "开启后，如果指数在观察期内没有创出指定日期区段的新高，目标等效仓位会被限制到锁定仓位比例。",
                    "When enabled, if the index has not made a new high over the configured high window during the observation period, target equivalent exposure is capped to the lock exposure.",
                ),
            )
            no_new_high_cols = st.columns(3)
            position["no_new_high_max_exposure"] = no_new_high_cols[0].number_input(
                _tr(language, "锁定仓位比例", "Locked exposure cap"),
                0.0,
                300.0,
                min(300.0, max(0.0, float(position.get("no_new_high_max_exposure", 100.0)))),
                5.0,
                help=_tr(language, "触发锁仓后允许的最高等效仓位，默认 100%，可按策略调整。", "Maximum equivalent exposure after the lock triggers. Default is 100% and can be adjusted."),
            )
            position["no_new_high_days"] = no_new_high_cols[1].number_input(
                _tr(language, "无新高观察天数", "Observation days without high"),
                5,
                756,
                int(position.get("no_new_high_days", 100)),
                5,
                help=_tr(language, "如果这段交易日内没有出现区段新高，则触发锁仓。", "If no windowed new high appears during this many trading days, the lock triggers."),
            )
            position["no_new_high_high_window"] = no_new_high_cols[2].number_input(
                _tr(language, "日期区段新高", "New-high window"),
                5,
                756,
                int(position.get("no_new_high_high_window", position.get("no_new_high_days", 100))),
                5,
                help=_tr(language, "定义“创多少日新高”。例如 200 表示创 200 日收盘新高。", "Defines the new-high window. For example, 200 means a 200-day closing high."),
            )
            st.caption(
                _tr(
                    language,
                    "逻辑：如果“无新高观察天数”内没有创出“日期区段新高”，则目标等效仓位不超过锁定仓位比例；它和 VIX、回撤、趋势质量上限共同取更保守的结果。",
                    "Logic: if the observation period contains no new high over the configured high window, target equivalent exposure is capped to the locked exposure cap; it combines conservatively with VIX, drawdown, and trend-quality caps.",
                )
            )

            st.divider()
            st.subheader(_tr(language, "周期涨幅锁仓模块", "Period Rise Lock Module"))
            render_sidebar_control_cluster(
                st,
                overline=_tr(language, "安全阀 D", "Safety Valve D"),
                title=_tr(language, "周期涨幅锁仓", "Period-rise lock"),
                summary=_tr(
                    language,
                    "这段处理的是涨得太快的阶段，让系统在周期内已经大幅上冲后先锁住部分成果，不再无限追高。",
                    "This valve handles markets that rise too far too fast, locking in part of the gain after a sharp period move instead of endlessly chasing higher.",
                ),
                chips=[_tr(language, "Bi-monthly", "Bi-monthly"), _tr(language, "Rise trigger", "Rise trigger")],
                tone="green",
            )
            position["period_rise_cap_enabled"] = st.toggle(
                _tr(
                    language,
                    "当双月周期内涨幅达到触发比例时锁定仓位",
                    "Lock exposure when bi-monthly period rise reaches threshold",
                ),
                bool(position.get("period_rise_cap_enabled", False)),
                help=_tr(
                    language,
                    "开启后，当当前双月周期（1-2月、3-4月等）内指数涨幅达到触发比例，目标等效仓位将被限制到锁定比例。",
                    "When enabled, if the index rises by the trigger percentage within the current bi-monthly period (Jan-Feb, Mar-Apr, etc.), target exposure is capped to the lock ratio.",
                ),
            )
            period_cols = st.columns(2)
            position["period_rise_threshold"] = period_cols[0].number_input(
                _tr(language, "触发涨幅比例 (%)", "Trigger rise threshold (%)"),
                0.0,
                100.0,
                float(position.get("period_rise_threshold", 15.0)),
                0.5,
                help=_tr(
                    language,
                    "当前双月周期内指数涨幅达到此比例时触发锁仓，例如 15 表示周期内涨幅 ≥ 15%。",
                    "Lock triggers when the period rise reaches this percentage, e.g. 15 means ≥ 15% rise in the period.",
                ),
                key=f"{key_prefix}_period_rise_threshold",
            )
            position["period_rise_max_exposure"] = period_cols[1].number_input(
                _tr(language, "触发后锁定仓位比例 (%)", "Locked exposure cap after trigger (%)"),
                0.0,
                300.0,
                float(position.get("period_rise_max_exposure", 200.0)),
                5.0,
                help=_tr(
                    language,
                    "触发锁仓后允许的最高等效仓位，例如 200 或 100。",
                    "Maximum equivalent exposure after the lock triggers, e.g. 200 or 100.",
                ),
                key=f"{key_prefix}_period_rise_max_exposure",
            )
            st.caption(
                _tr(
                    language,
                    "双月周期定义：1-2月、3-4月、5-6月、7-8月、9-10月、11-12月，以每个周期第一个交易日收盘价为基准。",
                    "Bi-monthly periods: Jan-Feb, Mar-Apr, May-Jun, Jul-Aug, Sep-Oct, Nov-Dec. Rise is measured from the first trading day close of each period.",
                )
            )

            st.divider()
            st.subheader(_tr(language, "趋势质量模块", "Trend Quality Module"))
            render_sidebar_control_cluster(
                st,
                overline=_tr(language, "安全阀 E", "Safety Valve E"),
                title=_tr(language, "趋势质量上限", "Trend-quality cap"),
                summary=_tr(
                    language,
                    "这段更像结构诊断器：它通过 120/200 日均线关系与斜率变化，提前识别慢性走弱，而不是等到回撤已经很深。",
                    "This one behaves like a structural diagnostic layer, using 120/200-day MA relationships and slope changes to catch slow deterioration before drawdown gets deep.",
                ),
                chips=[_tr(language, "MA slope", "MA slope"), _tr(language, "120/200", "120/200")],
                tone="green",
            )
            position["trend_quality_cap_enabled"] = st.toggle(
                _tr(language, "启用 120 日趋势质量上限", "Enable 120-day trend quality cap"),
                bool(position.get("trend_quality_cap_enabled", False)),
                help=_tr(
                    language,
                    "开启后，系统会根据中期均线斜率和价格是否跌破均线限制最大仓位，用来更早识别（阴跌）。",
                    "When enabled, the system caps exposure by medium-term moving-average slope and whether price is below that average to catch slow declines earlier.",
                ),
            )
            position["trend_quality_ma_cross_slow_decline_enabled"] = st.toggle(
                _tr(
                    language,
                    "用 120/200 日均线识别（阴跌）状态",
                    "Use 120/200-day MAs to detect slow-decline state",
                ),
                bool(position.get("trend_quality_ma_cross_slow_decline_enabled", False)),
                help=_tr(
                    language,
                    "开启后，120 日均线低于 200 日均线时视为处于（阴跌）状态，并使用“跌破均线上限”；120 日均线重新站上 200 日均线时视为（阴跌）结束。",
                    "When enabled, a 120-day MA below the 200-day MA is treated as slow-decline state and uses the below-MA cap; the state ends when the 120-day MA rises back above the 200-day MA.",
                ),
            )
            position["trend_quality_slow_decline_zero_floor_enabled"] = st.toggle(
                _tr(
                    language,
                    "阴跌时允许最低仓位降至 0",
                    "Allow 0% minimum exposure during slow decline",
                ),
                bool(position.get("trend_quality_slow_decline_zero_floor_enabled", False)),
                help=_tr(
                    language,
                    "开启后，即使基础最小仓位设为 100%，当 120 日均线低于 200 日均线且趋势信号风险关闭时，目标仓位也可以降到 0%。",
                    "When enabled, even if the base minimum exposure is 100%, the target can fall to 0% when the 120-day MA is below the 200-day MA and the trend signal is risk-off.",
                ),
                disabled=not bool(position.get("trend_quality_ma_cross_slow_decline_enabled", False)),
            )
            position["trend_quality_ma_window"] = st.number_input(
                _tr(language, "趋势质量均线窗口", "Trend quality MA window"),
                20,
                300,
                int(position.get("trend_quality_ma_window", 120)),
                5,
            )
            position["trend_quality_slope_lookback_days"] = st.number_input(
                _tr(language, "均线斜率观察期", "MA slope lookback"),
                5,
                120,
                int(position.get("trend_quality_slope_lookback_days", 20)),
                5,
            )
            slope_cols = st.columns(2)
            position["trend_quality_rising_slope_min_pct"] = slope_cols[0].number_input(
                _tr(language, "明显上行斜率下限", "Rising slope minimum"),
                -10.0,
                10.0,
                float(position.get("trend_quality_rising_slope_min_pct", 0.5)),
                0.1,
                help=_tr(language, "均线在观察期内上涨超过此百分比，视为趋势健康。", "MA gain over the lookback above this percent is treated as healthy."),
            )
            position["trend_quality_falling_slope_max_pct"] = slope_cols[1].number_input(
                _tr(language, "下行斜率上限", "Falling slope maximum"),
                -10.0,
                10.0,
                min(
                    float(position.get("trend_quality_falling_slope_max_pct", 0.0)),
                    float(position["trend_quality_rising_slope_min_pct"]),
                ),
                0.1,
                help=_tr(language, "均线在观察期内涨幅低于此百分比，视为趋势下行。", "MA gain over the lookback below this percent is treated as falling."),
            )
            quality_cols = st.columns(4)
            position["trend_quality_rising_max_exposure"] = quality_cols[0].number_input(
                _tr(language, "均线上行上限", "Rising MA cap"),
                0.0,
                300.0,
                min(300.0, max(0.0, float(position.get("trend_quality_rising_max_exposure", 300.0)))),
                5.0,
            )
            position["trend_quality_flat_max_exposure"] = quality_cols[1].number_input(
                _tr(language, "均线走平上限", "Flat MA cap"),
                0.0,
                300.0,
                min(300.0, max(0.0, float(position.get("trend_quality_flat_max_exposure", 220.0)))),
                5.0,
            )
            position["trend_quality_falling_max_exposure"] = quality_cols[2].number_input(
                _tr(language, "均线下行上限", "Falling MA cap"),
                0.0,
                300.0,
                min(300.0, max(0.0, float(position.get("trend_quality_falling_max_exposure", 150.0)))),
                5.0,
            )
            position["trend_quality_below_ma_max_exposure"] = quality_cols[3].number_input(
                _tr(language, "跌破均线上限", "Below MA cap"),
                0.0,
                300.0,
                min(300.0, max(0.0, float(position.get("trend_quality_below_ma_max_exposure", 100.0)))),
                5.0,
            )
            st.caption(
                _tr(
                    language,
                    "这层上限会和趋势目标、VIX 上限、回撤上限共同取更保守值；它比回撤曲线更早处理慢性走弱（阴跌）。",
                    "This cap combines conservatively with the trend target, VIX cap, and drawdown cap; it reacts earlier than drawdown to slow deterioration.",
                )
            )

            st.divider()
            st.subheader(_tr(language, "极端风险模块", "Extreme Risk Module"))
            render_sidebar_control_cluster(
                st,
                overline=_tr(language, "安全阀 F", "Safety Valve F"),
                title=_tr(language, "极端风险地板覆盖", "Extreme-risk floor override"),
                summary=_tr(
                    language,
                    "这段不是压上限，而是允许系统在真正失控的行情里把仓位地板也降下去，留出彻底防守的空间。",
                    "This valve does not cap the upside; it lowers the minimum floor during truly broken markets so the system can move fully defensive when needed.",
                ),
                chips=[_tr(language, "Floor override", "Floor override"), _tr(language, "200MA", "200MA")],
                tone="green",
            )
            position["extreme_risk_cap_enabled"] = st.toggle(
                _tr(language, "启用极端风险最低仓位覆盖", "Enable extreme risk floor override"),
                bool(position.get("extreme_risk_cap_enabled", False)),
                help=_tr(
                    language,
                    "开启后，当价格跌至 200 日均线下方超过阈值百分比时，允许最低仓位下降到设定值（可低于正常最低仓位）。",
                    "When enabled, if price falls more than the threshold % below the slow MA, the exposure floor is overridden to the configured minimum, which can go below the normal minimum exposure.",
                ),
                key=f"{key_prefix}_extreme_risk_cap_enabled",
            )
            extreme_risk_cols = st.columns(3)
            position["extreme_risk_ma_window"] = extreme_risk_cols[0].number_input(
                _tr(language, "均线窗口", "MA window"),
                10,
                300,
                int(position.get("extreme_risk_ma_window", 200)),
                5,
                help=_tr(language, "用于极端风险判断的均线长度。默认 200 日。", "MA window for extreme risk detection. Default is 200 days."),
                key=f"{key_prefix}_extreme_risk_ma_window",
            )
            position["extreme_risk_threshold_pct"] = extreme_risk_cols[1].number_input(
                _tr(language, "触发阈值 (%)", "Trigger threshold (%)"),
                0.0,
                20.0,
                float(position.get("extreme_risk_threshold_pct", 2.0)),
                0.5,
                help=_tr(language, "价格跌至均线下方超过此百分比时触发。默认 2%。", "Triggers when price falls more than this % below the MA. Default is 2%."),
                key=f"{key_prefix}_extreme_risk_threshold_pct",
            )
            position["extreme_risk_min_exposure"] = extreme_risk_cols[2].number_input(
                _tr(language, "强制最低仓位 (%)", "Override minimum exposure (%)"),
                0.0,
                300.0,
                min(300.0, max(0.0, float(position.get("extreme_risk_min_exposure", 0.0)))),
                5.0,
                help=_tr(language, "极端风险条件触发时的最低仓位覆盖值。设为 0% 允许完全空仓。", "Floor override when extreme risk conditions are met. Set 0% to allow fully defensive positioning."),
                key=f"{key_prefix}_extreme_risk_min_exposure",
            )
            st.caption(
                _tr(
                    language,
                    "极端风险模块修改的是仓位地板，而非上限。它允许最低仓位在价格大幅低于均线时降到 0% 或更低的值。",
                    "The extreme risk module overrides the exposure floor, not the cap. It allows minimum exposure to drop to 0% or a configured level when price is well below the MA.",
                )
            )

        st.form_submit_button(_tr(language, "应用设置", "Apply settings"), type="primary", use_container_width=True)
        st.caption(_tr(language, "调整多个参数后再应用，可减少页面重算和按钮卡顿。", "Apply several changes at once to reduce recalculation and UI pauses."))

    return settings


def _daily_tab(settings: dict[str, Any]) -> None:
    language = _ui_language(settings)
    render_daily_page_module(
        settings,
        language,
        deps=DailyPageDeps(
            as_settings=_as_settings,
            cached_prices=_cached_prices,
            tr=_tr,
            aligned_button=_aligned_button,
            disabled_pdf_button=_disabled_pdf_button,
            pdf_download_button=_pdf_download_button,
            build_pdf_report=_build_pdf_report,
            strategy_summary_rows=_strategy_summary_rows,
            pdf_filename=_pdf_filename,
            state_label=_state_label,
            trend_ma_labels=_trend_ma_labels,
            daily_timeline_mode_labels=_daily_timeline_mode_labels,
            market_windows=_market_windows,
            portfolio_adjustment_section=_portfolio_adjustment_section,
            fingerprint=_fingerprint,
            is_stale=_is_stale,
            required_symbols_from_raw=required_symbols_from_raw,
        ),
    )


def _market_health_tab(settings: dict[str, Any]) -> None:
    language = _ui_language(settings)
    render_market_health_page_module(
        settings,
        language,
        deps=MarketHealthPageDeps(
            as_settings=_as_settings,
            cached_prices=_cached_prices,
            tr=_tr,
            aligned_button=_aligned_button,
            disabled_pdf_button=_disabled_pdf_button,
            pdf_download_button=_pdf_download_button,
            build_pdf_report=_build_pdf_report,
            strategy_summary_rows=_strategy_summary_rows,
            pdf_filename=_pdf_filename,
            zoomable_line_chart=_zoomable_line_chart,
        ),
    )


def _aligned_button(container: Any, label: str, **kwargs: Any) -> bool:
    container.markdown('<div style="height: 1.75rem;"></div>', unsafe_allow_html=True)
    return container.button(label, **kwargs)


def _backtest_tab(settings: dict[str, Any]) -> None:
    language = _ui_language(settings)
    render_backtest_page_module(
        settings,
        language,
        deps=BacktestPageDeps(
            as_settings=_as_settings,
            tr=_tr,
            aligned_button=_aligned_button,
            option_index=_option_index,
            disabled_pdf_button=_disabled_pdf_button,
            pdf_download_button=_pdf_download_button,
            build_pdf_report=_build_pdf_report,
            pdf_filename=_pdf_filename,
            cached_prices=_cached_prices,
            strategy_summary_rows=_strategy_summary_rows,
            trade_summary_rows=_trade_summary_rows,
            equity_columns_for_pdf=equity_columns_for_pdf,
            exposure_columns_for_timing=_exposure_columns_for_timing,
            zoomable_line_chart=_zoomable_line_chart,
            execution_timing_labels=_execution_timing_labels,
            backtest_date_defaults=_backtest_date_defaults,
            fingerprint=_fingerprint,
            is_stale=_is_stale,
            default_raw_settings=lambda: load_settings(DEFAULT_CONFIG).raw,
        ),
    )


def _settings_tab(settings: dict[str, Any], config_path: str) -> None:
    render_settings_page_module(
        settings,
        config_path,
        deps=SettingsPageDeps(
            tr=_tr,
            ui_language=_ui_language,
            option_index=_option_index,
            aligned_button=_aligned_button,
            save_config=_save_config,
            save_config_github=_save_config_github,
            profile_path_for_name=_profile_path_for_name,
            config_options=_config_options,
            delete_config_github=_delete_config_github,
            read_workflow_push_config=_read_workflow_push_config,
            update_workflow_github=_update_workflow_github,
            default_push_config=DEFAULT_PUSH_CONFIG,
            default_nz_time=DEFAULT_NZ_TIME,
            default_us_time=DEFAULT_US_TIME,
            release_notes_renderer=_render_release_notes,
            version=__version__,
            app_root=APP_ROOT,
            default_config=str(DEFAULT_CONFIG),
        ),
    )


def _render_release_notes(language: str) -> None:
    shared_render_release_notes(
        language,
        tr=_tr,
        changelog_path=CHANGELOG_PATH,
        changelog_en_path=CHANGELOG_EN_PATH,
    )


def _release_notes_text(language: str = "zh") -> str:
    return shared_release_notes_text(
        language,
        changelog_path=CHANGELOG_PATH,
        changelog_en_path=CHANGELOG_EN_PATH,
    )


def _release_notes_path(language: str = "zh") -> Path:
    return shared_release_notes_path(
        language,
        changelog_path=CHANGELOG_PATH,
        changelog_en_path=CHANGELOG_EN_PATH,
    )


def _parameter_ui_name(parameter: str, settings: dict[str, Any], language: str) -> str:
    labels = {
        "trend.short_window": ("短期均线", "Short moving average"),
        "trend.medium_window": ("中期均线", "Medium moving average"),
        "trend.long_window": ("长期均线", "Long moving average"),
        "trend.confirmation_days": ("连续确认天数", "Confirmation days"),
        "trend.exposure.below_long": ("跌破长期均线仓位", "Below long MA exposure"),
        "trend.exposure.above_long": ("站上长期均线仓位", "Above long MA exposure"),
        "trend.exposure.medium_above_long": ("中期均线站上长期均线仓位", "Medium MA above long MA exposure"),
        "trend.exposure.short_above_medium_above_long": ("短期/中期/长期均线多头排列仓位", "Short/medium/long MA bullish stack exposure"),
        "position.max_exposure": ("最大等效仓位", "Maximum equivalent exposure"),
        "position.rebalance_threshold": ("最小调仓阈值", "Minimum rebalance threshold"),
        "all_parameters": ("全部参数统一调整", "All parameters scaled together"),
    }
    if parameter.startswith("vix.rules.") and parameter.endswith(".multiplier"):
        label = _vix_rule_label(parameter, settings)
        return _tr(language, f"{label} 系数", f"{label} multiplier")
    zh, en = labels.get(parameter, (parameter, parameter))
    return _tr(language, zh, en)


def _vix_rule_label(parameter: str, settings: dict[str, Any]) -> str:
    try:
        index = int(parameter.split(".")[2])
        return str(settings.get("vix", {}).get("rules", [])[index].get("label", f"rule {index + 1}"))
    except (IndexError, ValueError, AttributeError):
        return parameter


def equity_columns_for_pdf(
    show_leveraged_buy_hold: bool,
    show_ma120_timing: bool,
    show_leveraged_ma120_timing: bool,
) -> list[str]:
    columns = ["equity", "buy_hold_equity"]
    if show_leveraged_buy_hold:
        columns.append("leveraged_buy_hold_equity")
    if show_ma120_timing:
        columns.append("ma120_timing_equity")
    if show_leveraged_ma120_timing:
        columns.append("leveraged_ma120_timing_equity")
    return columns


def _exposure_columns_for_timing(execution_timing: str) -> list[str]:
    return ["target_exposure", "actual_equivalent_exposure"]


def _execution_timing_labels(language: str) -> dict[str, str]:
    return {
        _tr(language, "下一交易日收盘生效", "Next session close-to-close"): "next_session",
        _tr(language, "同日收盘生效（激进）", "Same close, aggressive"): "same_close",
    }


def _daily_timeline_mode_labels(language: str) -> dict[str, str]:
    return {
        _tr(language, "下一交易日", "Next session"): NEXT_SESSION_MODE,
        _tr(language, "NZ 盘末 / 美股开盘", "NZ close / US open"): NZ_CLOSE_US_OPEN_MODE,
    }


def _trend_ma_labels(settings: dict[str, Any]) -> tuple[str, str, str]:
    trend = settings["trend"]
    return (
        f"MA{trend.get('short_window')}",
        f"MA{trend.get('medium_window')}",
        f"MA{trend.get('long_window')}",
    )


def _backtest_date_defaults(
    preset: str,
    settings: dict[str, Any],
    *,
    today: date | None = None,
) -> tuple[date, date]:
    preset_range = BACKTEST_PRESETS[preset]
    if preset_range:
        return preset_range
    return date.fromisoformat(settings["backtest"]["start"]), today or date.today()


def _widget_key_prefix(config_path: str) -> str:
    digest = hashlib.sha1(str(Path(config_path).resolve()).encode("utf-8")).hexdigest()[:12]
    return f"settings_{digest}"


def _config_options() -> dict[str, Path]:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    options: dict[str, Path] = {"默认配置": Path(DEFAULT_CONFIG)}
    for path in sorted(PROFILE_DIR.glob("*.toml")):
        try:
            raw = load_settings(path).raw
            name = raw.get("profile", {}).get("name") or path.stem
        except Exception:
            name = path.stem
        options[name] = path
    options["自定义路径"] = Path(DEFAULT_CONFIG)
    return options


def _profile_path_for_name(name: str) -> Path:
    safe = "".join(ch for ch in name.strip() if ch.isalnum() or ch in ("-", "_", " ")).strip()
    if not safe:
        safe = "profile"
    return PROFILE_DIR / f"{safe}.toml"


def _save_config(path: Path, settings: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(toml.dumps(settings), encoding="utf-8")


def _save_config_github(relative_path: str, content: str) -> tuple[bool, str]:
    return push_text_file(_github_repo_config(), relative_path, content)


def _delete_config_github(relative_path: str) -> tuple[bool, str]:
    return delete_file(_github_repo_config(), relative_path)


def _github_repo_config() -> GitHubRepoConfig:
    try:
        token = st.secrets.get("GITHUB_TOKEN", "")
        repo = st.secrets.get("GITHUB_REPO", "")
        branch = st.secrets.get("GITHUB_BRANCH", "main")
    except Exception:
        token = ""
        repo = ""
        branch = "main"
    return GitHubRepoConfig(token=token, repo=repo, branch=branch)


def _read_workflow_push_config() -> tuple[str, str, str]:
    return read_push_config(_github_repo_config())


def _update_workflow_github(config_rel: str, nz_time: str, us_time: str) -> tuple[bool, str]:
    return update_push_config(_github_repo_config(), config_rel, nz_time, us_time)


def _market_windows(settings: dict[str, Any], timeline_mode: str | None = None) -> None:
    language = _ui_language(settings)
    st.subheader(_tr(language, "新西兰本地交易窗口", "Local Trading Windows"))
    now = pd.Timestamp.now(tz=settings["profile"]["home_timezone"]).to_pydatetime()
    us_open, us_close = _relevant_local_window(settings, "us", now)
    asx_open, asx_close = _relevant_local_window(settings, "asx", now)
    nzx_open, nzx_close = _relevant_local_window(settings, "nzx", now)
    market_windows = [
        {"key": "nzx", "label": "NZ", "open": nzx_open, "close": nzx_close, "color": "#9e2f2f"},
        {"key": "asx", "label": "AU", "open": asx_open, "close": asx_close, "color": "#1f6a53"},
        {"key": "us", "label": "US", "open": us_open, "close": us_close, "color": "#12395b"},
    ]
    selected_timeline_mode = timeline_mode or settings.get("backtest", {}).get("execution_timing", "next_session")
    if selected_timeline_mode not in SUPPORTED_TIMELINE_MODES:
        selected_timeline_mode = NEXT_SESSION_MODE
    trade_items = trade_timeline_items(settings, now, strategy_keys={selected_timeline_mode})
    _parallel_market_trade_timeline(market_windows, trade_items, now, language)
    _timeline_countdowns(market_windows, trade_items, now, language)
    cols = st.columns(3)
    cols[0].metric(_tr(language, "美股常规时段", "US regular session"), f"{us_open:%H:%M} - {us_close:%H:%M}", f"{us_open:%Y-%m-%d}")
    cols[1].metric(_tr(language, "ASX 常规时段", "ASX regular session"), f"{asx_open:%H:%M} - {asx_close:%H:%M}", f"{asx_open:%Y-%m-%d}")
    cols[2].metric(_tr(language, "NZX 常规时段", "NZX regular session"), f"{nzx_open:%H:%M} - {nzx_close:%H:%M}", f"{nzx_open:%Y-%m-%d}")


def _relevant_local_window(settings: dict[str, Any], market: str, now: datetime) -> tuple[datetime, datetime]:
    return market_window(settings, market).relevant_local_trading_window(now)


def _parallel_market_trade_timeline(
    market_windows: list[dict[str, Any]],
    trade_items: list[Any],
    now: datetime,
    language: str,
) -> None:
    start, end = _timeline_bounds(market_windows, trade_items, now)
    total_seconds = max((end - start).total_seconds(), 1)
    market_segments = _market_segments(market_windows, start, end)
    market_html = "\n".join(
        _market_segment_html(segment, start, total_seconds)
        for segment in market_segments
    )
    now_marker_html = _now_marker_html(now, start, end, total_seconds, language)
    visible_trade_items = [
        item
        for item in trade_items
        if start <= item.deadline <= end
    ]
    deadline_html = "\n".join(
        _trade_deadline_html(item, start, total_seconds, language)
        for item in visible_trade_items
    )
    action_list_html = "\n".join(
        _trade_action_item_html(item, language)
        for item in visible_trade_items
    )
    warning_html = "\n".join(
        _trade_warning_window_html(item, start, end, total_seconds)
        for item in trade_items
    )
    legend_html = "\n".join(
        f'<span class="timeline-legend-item"><span style="background:{window["color"]}"></span>{html.escape(window["label"])}</span>'
        for window in market_windows
    )
    st.markdown(
        f"""
<style>
.trade-timeline-wrap {{
  border: 2px solid var(--leo-surface-rim);
  border-top: 3px solid rgba(174, 143, 84, 0.24);
  border-radius: 0;
  padding: 14px 14px 32px;
  margin: 10px 0 12px;
  background: linear-gradient(145deg, var(--leo-surface-a), var(--leo-surface-b));
  box-shadow: inset 0 1px 0 var(--leo-surface-top), inset 0 -1px 0 var(--leo-surface-bot), 0 0 14px var(--leo-metal-glow);
  backdrop-filter: blur(8px);
  overflow: visible;
}}
.trade-timeline-head {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  color: inherit;
  font-size: 13px;
  margin-bottom: 8px;
}}
.trade-timeline-row {{
  margin: 14px 0 16px;
}}
.trade-timeline-row.mode-row {{
  margin-bottom: 20px;
}}
.trade-timeline-label {{
  color: inherit;
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 6px;
}}
.trade-timeline-track {{
  position: relative;
  height: 34px;
  border-radius: 0;
  clip-path: polygon(0.35rem 0, calc(100% - 0.35rem) 0, 100% 0.35rem, 100% calc(100% - 0.35rem), calc(100% - 0.35rem) 100%, 0.35rem 100%, 0 calc(100% - 0.35rem), 0 0.35rem);
  background: linear-gradient(145deg, rgba(244,240,232,0.12), rgba(26,29,31,0.10));
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.10), inset 0 -1px 0 rgba(174,143,84,0.05);
  overflow: visible;
}}
.trade-timeline-segment {{
  position: absolute;
  top: 0;
  bottom: 0;
  border-radius: 0;
  clip-path: polygon(0.3rem 0, calc(100% - 0.3rem) 0, 100% 0.3rem, 100% calc(100% - 0.3rem), calc(100% - 0.3rem) 100%, 0.3rem 100%, 0 calc(100% - 0.3rem), 0 0.3rem);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.20);
}}
.trade-timeline-segment span {{
  position: absolute;
  left: 8px;
  top: 50%;
  transform: translateY(-50%);
  color: #ffffff;
  font-size: 12px;
  font-weight: 800;
  text-shadow: 0 1px 2px rgba(0,0,0,.35);
  white-space: nowrap;
}}
.trade-timeline-marker {{
  position: absolute;
  top: -6px;
  bottom: -6px;
  width: 2px;
  background: currentColor;
  z-index: 4;
}}
.trade-timeline-marker span {{
  position: absolute;
  top: auto;
  bottom: -20px;
  transform: translateX(-50%);
  color: inherit;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}}
.trade-deadline-warning {{
  position: absolute;
  top: 0;
  bottom: 0;
  border-radius: 0;
  clip-path: polygon(0.3rem 0, calc(100% - 0.3rem) 0, 100% 0.3rem, 100% calc(100% - 0.3rem), calc(100% - 0.3rem) 100%, 0.3rem 100%, 0 calc(100% - 0.3rem), 0 0.3rem);
  opacity: .14;
}}
.trade-deadline-marker {{
  position: absolute;
  top: 0;
  bottom: 0;
  width: 4px;
  border-radius: 0;
  z-index: 3;
}}
.trade-deadline-marker span {{
  position: absolute;
  left: 50%;
  top: auto;
  bottom: -20px;
  transform: translateX(-50%);
  max-width: 72px;
  font-size: 11px;
  font-weight: 700;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.trade-mode-label-below {{
  color: inherit;
  font-size: 13px;
  font-weight: 700;
  margin-top: 24px;
  margin-bottom: 6px;
}}
.trade-action-list {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 6px;
  margin-top: 8px;
}}
.trade-action-item {{
  position: relative;
  overflow: hidden;
  padding: 5px 8px 5px 18px;
  background: linear-gradient(145deg, var(--leo-surface-a), var(--leo-surface-b));
  border: 1px solid var(--leo-surface-rim);
  border-radius: 0;
  clip-path: polygon(0.35rem 0, calc(100% - 0.35rem) 0, 100% 0.35rem, 100% calc(100% - 0.35rem), calc(100% - 0.35rem) 100%, 0.35rem 100%, 0 calc(100% - 0.35rem), 0 0.35rem);
  box-shadow: inset 0 1px 0 var(--leo-surface-top);
  color: inherit;
  font-size: 12px;
  line-height: 1.35;
  backdrop-filter: blur(6px);
}}
.trade-action-item::before {{
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 10px;
  background: var(--trade-action-color);
}}
.trade-action-item strong {{
  color: var(--trade-action-color);
  margin-right: 4px;
}}
.timeline-legend {{
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: inherit;
  font-size: 12px;
  margin-top: 8px;
}}
.timeline-legend-item {{
  display: inline-flex;
  align-items: center;
  gap: 5px;
}}
.timeline-legend-item span {{
  width: 18px;
  height: 8px;
  border-radius: 999px;
  display: inline-block;
}}
.timeline-countdown-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
  margin: 12px 0 4px;
}}
.timeline-countdown-sections {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin: 12px 0 4px;
}}
.timeline-countdown-section {{
  margin: 0;
}}
.timeline-countdown-section-title {{
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--leo-kicker);
  margin: 0 0 8px;
}}
.timeline-countdown-card {{
  border: 2px solid var(--leo-surface-rim);
  border-radius: 0;
  clip-path: polygon(0.45rem 0, calc(100% - 0.45rem) 0, 100% 0.45rem,
             100% calc(100% - 0.45rem), calc(100% - 0.45rem) 100%,
             0.45rem 100%, 0 calc(100% - 0.45rem), 0 0.45rem);
  padding: 12px 14px;
  background: linear-gradient(145deg, var(--leo-surface-a), var(--leo-surface-b));
  box-shadow: inset 0 1px 0 var(--leo-surface-top), inset 0 -1px 0 var(--leo-surface-bot), 0 0 10px var(--leo-metal-glow);
  color: var(--leo-ink);
  backdrop-filter: blur(8px);
}}
.timeline-countdown-card.market-card {{
  border-left: 2px solid rgba(18, 57, 91, 0.30);
}}
.timeline-countdown-card.action-card {{
  border-left: 2px solid rgba(31, 106, 83, 0.30);
}}
.timeline-countdown-card.urgent {{
  border-color: rgba(158, 47, 47, 0.70);
  background: linear-gradient(145deg, rgba(158, 47, 47, 0.16), rgba(244, 240, 232, 0.06));
  color: var(--leo-ink);
}}
.timeline-countdown-title {{
  font-size: 12px;
  font-weight: 700;
  opacity: .82;
}}
.timeline-countdown-time {{
  font-size: 18px;
  font-weight: 800;
  margin-top: 2px;
}}
.timeline-countdown-meta {{
  font-size: 12px;
  opacity: .82;
  margin-top: 2px;
}}
@media (max-width: 640px) {{
  .trade-timeline-wrap {{
    padding: 12px 10px 34px;
  }}
  .trade-timeline-head {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 2px;
    font-size: 12px;
  }}
  .trade-timeline-head span:nth-child(2) {{
    order: -1;
    color: inherit;
    font-weight: 700;
  }}
  .trade-timeline-row {{
    margin: 16px 0 18px;
  }}
  .trade-timeline-row.mode-row {{
    margin-bottom: 22px;
  }}
  .trade-timeline-track {{
    height: 38px;
  }}
  .trade-timeline-segment span {{
    left: 6px;
    font-size: 11px;
  }}
  .trade-timeline-marker span {{
    bottom: -22px;
    font-size: 10px;
  }}
  .trade-deadline-marker span {{
    bottom: -22px;
    max-width: 56px;
    font-size: 10px;
  }}
  .trade-mode-label-below {{
    margin-top: 26px;
  }}
  .trade-action-list,
  .timeline-countdown-grid,
  .timeline-countdown-sections {{
    grid-template-columns: 1fr;
  }}
}}
</style>
<div class="trade-timeline-wrap">
  <div class="trade-timeline-head">
    <span>{html.escape(start.strftime("%Y-%m-%d %H:%M"))}</span>
    <span>{html.escape(_tr(language, "合并市场与当前交易模式", "Merged markets and selected mode"))}</span>
    <span>{html.escape(end.strftime("%Y-%m-%d %H:%M"))}</span>
  </div>
  <div class="trade-timeline-row">
    <div class="trade-timeline-label">{html.escape(_tr(language, "市场时间轴", "Market timeline"))}</div>
    <div class="trade-timeline-track">{market_html}</div>
  </div>
  <div class="trade-timeline-row mode-row">
    <div>
      <div class="trade-timeline-track">{warning_html}{deadline_html}{now_marker_html}</div>
      <div class="trade-mode-label-below">{html.escape(_tr(language, "交易模式时间轴", "Mode timeline"))}</div>
      <div class="trade-action-list">{action_list_html}</div>
    </div>
  </div>
  <div class="timeline-legend">{legend_html}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def _timeline_bounds(
    market_windows: list[dict[str, Any]],
    trade_items: list[Any],
    now: datetime,
) -> tuple[datetime, datetime]:
    anchors = [now + timedelta(hours=24)]
    anchors.extend(window["close"] for window in market_windows)
    anchors.extend(item.deadline for item in trade_items)
    end = max(anchors)
    return now, end


def _market_segments(
    market_windows: list[dict[str, Any]],
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    boundaries = {start, end}
    for window in market_windows:
        boundaries.add(max(start, window["open"]))
        boundaries.add(min(end, window["close"]))
    ordered = sorted(boundaries)
    segments: list[dict[str, Any]] = []
    for segment_start, segment_end in zip(ordered, ordered[1:]):
        if segment_start >= segment_end:
            continue
        active = [
            window
            for window in market_windows
            if window["open"] < segment_end and window["close"] > segment_start
        ]
        if active:
            segments.append({"start": segment_start, "end": segment_end, "active": active})
    return segments


def _market_segment_html(segment: dict[str, Any], start: datetime, total_seconds: float) -> str:
    left = _timeline_pct(segment["start"], start, total_seconds)
    width = max(_timeline_pct(segment["end"], start, total_seconds) - left, 0.3)
    active = segment["active"]
    label = " / ".join(window["label"] for window in active)
    if len(active) == 1:
        background = active[0]["color"]
    else:
        stripe_parts = []
        stripe_width = 12
        for index, window in enumerate(active):
            stripe_parts.append(f'{window["color"]} {index * stripe_width}px {(index + 1) * stripe_width}px')
        background = f"repeating-linear-gradient(135deg, {', '.join(stripe_parts)})"
    return (
        f'<div class="trade-timeline-segment" style="left:{left:.4f}%;width:{width:.4f}%;background:{background};" '
        f'title="{html.escape(label)}"><span>{html.escape(label)}</span></div>'
    )


def _now_marker_html(now: datetime, start: datetime, end: datetime, total_seconds: float, language: str) -> str:
    if not start <= now <= end:
        return ""
    left = _timeline_pct(now, start, total_seconds)
    label = _tr(language, "现在", "Now")
    return f'<div class="trade-timeline-marker" style="left:{left:.4f}%;"><span>{html.escape(label)}</span></div>'


def _trade_deadline_html(item: Any, start: datetime, total_seconds: float, language: str) -> str:
    left = _timeline_pct(item.deadline, start, total_seconds)
    color = _trade_marker_color(item)
    label = f"{item.market_label} {item.deadline:%H:%M}"
    title = f"{label} · {_short_trade_action(item, language)}"
    return (
        f'<div class="trade-deadline-marker" style="left:{left:.4f}%;background:{color};" '
        f'title="{html.escape(title)}"><span style="color:{color};">{html.escape(label)}</span></div>'
    )


def _trade_action_item_html(item: Any, language: str) -> str:
    color = _trade_marker_color(item)
    label = f"{item.market_label} {item.deadline:%Y-%m-%d %H:%M}"
    return (
        f'<div class="trade-action-item" style="--trade-action-color:{color};">'
        f"<strong>{html.escape(label)}</strong>"
        f"{html.escape(_short_trade_action(item, language))}"
        "</div>"
    )


def _trade_marker_color(item: Any) -> str:
    action_en = item.action("en").lower()
    if item.strategy_key == NEXT_SESSION_MODE:
        return "#1f6a53"
    if item.market_label == "NZX":
        return "#9e2f2f"
    if item.market_label == "ASX":
        return "#1f6a53"
    if "open" in action_en:
        return "#355d7a"
    if "close" in action_en:
        return "#12395b"
    return "#9e2f2f"


def _short_trade_action(item: Any, language: str) -> str:
    action_en = item.action("en").lower()
    if item.strategy_key == NEXT_SESSION_MODE:
        return _tr(language, "下一交易日：开盘前调仓", "Next session: rebalance before open")
    if item.strategy_key == SAME_CLOSE_MODE:
        return _tr(language, "同日收盘：按收盘信号调仓", "Same close: rebalance at the close")
    if item.market_label == "NZX":
        return _tr(language, "NZX 收盘前：处理本地仓位", "Before NZX close: local sleeve")
    if "open" in action_en:
        return _tr(language, "美股开盘前：挂 3 倍买单", "Before US open: place 3x buy")
    if "close" in action_en:
        return _tr(language, "美股收盘前：卖 3 倍，准备买回 NZ", "Before US close: sell 3x, prep NZ buyback")
    return item.action(language)


def _trade_warning_window_html(item: Any, start: datetime, end: datetime, total_seconds: float) -> str:
    warning_start = max(start, item.deadline - timedelta(hours=3))
    warning_end = min(end, item.deadline)
    if warning_start >= warning_end:
        return ""
    left = _timeline_pct(warning_start, start, total_seconds)
    width = max(_timeline_pct(warning_end, start, total_seconds) - left, 0.3)
    color = _trade_marker_color(item)
    return f'<div class="trade-deadline-warning" style="left:{left:.4f}%;width:{width:.4f}%;background:{color};"></div>'


def _timeline_pct(value: datetime, start: datetime, total_seconds: float) -> float:
    return min(max((value - start).total_seconds() / total_seconds * 100, 0.0), 100.0)


def _timeline_countdowns(
    market_windows: list[dict[str, Any]],
    trade_items: list[Any],
    now: datetime,
    language: str,
) -> None:
    market_cards: list[str] = []
    action_cards: list[str] = []

    market_event_candidates: list[tuple[str, datetime, str, str]] = []
    for window in market_windows:
        if window["open"] <= now <= window["close"]:
            close_dt = window["close"]
            market_event_candidates.append((
                _tr(language, f"当前市场 {window['label']} 收盘", f"Current market {window['label']} close"),
                close_dt,
                close_dt.strftime("%Y-%m-%d %H:%M"),
                "market-card",
            ))
        elif window["open"] > now:
            open_dt = window["open"]
            market_event_candidates.append((
                _tr(language, f"下个市场 {window['label']} 开盘", f"Next market {window['label']} open"),
                open_dt,
                open_dt.strftime("%Y-%m-%d %H:%M"),
                "market-card",
            ))
    if market_event_candidates:
        title, target, meta, kind = min(market_event_candidates, key=lambda x: x[1])
        market_cards.append(_countdown_card_html(title, target, meta, now, language, kind))

    future_trade_items = sorted(
        (item for item in trade_items if item.deadline >= now),
        key=lambda item: item.deadline,
    )
    if future_trade_items:
        item = future_trade_items[0]
        action_cards.append(_countdown_card_html(
            _tr(language, f"当前模式操作时间 · {item.market_label}", f"Current mode action · {item.market_label}"),
            item.deadline,
            f"{item.deadline:%Y-%m-%d %H:%M} · {_short_trade_action(item, language)}",
            now,
            language,
            "action-card",
        ))

    sections: list[str] = []
    if market_cards:
        sections.append(_countdown_section_html(
            _tr(language, "市场时段", "Market window"),
            market_cards,
        ))
    if action_cards:
        sections.append(_countdown_section_html(
            _tr(language, "策略动作", "Strategy action"),
            action_cards,
        ))
    if sections:
        st.markdown(f'<div class="timeline-countdown-sections">{"".join(sections)}</div>', unsafe_allow_html=True)


def _countdown_section_html(title: str, cards: list[str]) -> str:
    cards_html = "\n".join(cards)
    return (
        '<div class="timeline-countdown-section">'
        f'<div class="timeline-countdown-section-title">{html.escape(title)}</div>'
        f'<div class="timeline-countdown-grid">{cards_html}</div>'
        "</div>"
    )


def _countdown_card_html(
    title: str,
    target: datetime,
    meta: str,
    now: datetime,
    language: str,
    kind: str,
) -> str:
    remaining = target - now
    urgent = timedelta(0) <= remaining <= timedelta(hours=3)
    class_name = f"timeline-countdown-card {kind}"
    if urgent:
        class_name += " urgent"
    return (
        f'<div class="{class_name}">'
        f'<div class="timeline-countdown-title">{html.escape(title)}</div>'
        f'<div class="timeline-countdown-time">{html.escape(_format_duration(remaining, language))}</div>'
        f'<div class="timeline-countdown-meta">{html.escape(meta)}</div>'
        "</div>"
    )


def _format_duration(delta: timedelta, language: str = "zh") -> str:
    total_minutes = max(int(delta.total_seconds() // 60), 0)
    hours, minutes = divmod(total_minutes, 60)
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return _tr(language, f"{days}天{hours}小时", f"{days}d {hours}h")
    if hours:
        return _tr(language, f"{hours}小时{minutes}分钟", f"{hours}h {minutes}m")
    return _tr(language, f"{minutes}分钟", f"{minutes}m")


def required_symbols_from_raw(settings: dict[str, Any]) -> list[str]:
    symbols = [settings["signals"]["primary"], settings["signals"]["volatility"]]
    symbols.extend(settings["signals"].get("confirm", []))
    symbols.extend(settings["signals"].get("defensive", []))
    execution = settings["execution"]
    symbols.extend(
        [
            execution["core_asset"],
            execution["asx_core_asset"],
            execution["defensive_asset"],
            execution.get("nz_defensive_asset", "NZC.NZ"),
            execution.get("au_defensive_asset", "BILL.AX"),
            execution["leveraged_asset"],
        ]
    )
    return list(dict.fromkeys(symbols))


@st.cache_data(ttl=86400)
def _cached_prices(
    symbols: tuple[str, ...],
    start: str,
    end: str | None,
    auto_adjust: bool,
) -> dict[str, pd.DataFrame]:
    return download_prices(list(symbols), start=start, end=end, auto_adjust=auto_adjust)


def _price_series(frame: pd.DataFrame, preferred_field: str) -> pd.Series:
    if preferred_field in frame.columns:
        return frame[preferred_field]
    if isinstance(frame.columns, pd.MultiIndex):
        for field in (preferred_field, "Close", "Adj Close"):
            if field in frame.columns.get_level_values(-1):
                return frame.xs(field, axis=1, level=-1).iloc[:, 0]
            if field in frame.columns.get_level_values(0):
                selected = frame[field]
                return selected.iloc[:, 0] if isinstance(selected, pd.DataFrame) else selected
    for field in (preferred_field, "Close", "Adj Close"):
        if field in frame.columns:
            return frame[field]
    raise KeyError(preferred_field)


@st.cache_data(ttl=3600)
def _cached_backtest(
    price: pd.Series,
    vix: pd.Series,
    settings: dict[str, Any],
    *,
    open_price: pd.Series | None,
    leveraged_price: pd.Series | None,
    leveraged_open_price: pd.Series | None,
    result_start: str | None,
):
    return run_backtest(
        price,
        vix,
        settings,
        open_price=open_price,
        leveraged_price=leveraged_price,
        leveraged_open_price=leveraged_open_price,
        result_start=result_start,
    )


def _option_index(options: list[str], value: str) -> int:
    return shared_option_index(options, value)


def _portfolio_adjustment_section(
    settings: dict[str, Any],
    allocation: Any,
    prices: dict[str, pd.DataFrame],
    signal_date: pd.Timestamp,
) -> None:
    language = _ui_language(settings)
    st.subheader(_tr(language, "当前仓位调整建议", "Current Rebalance Advice"))
    base_currency = settings["profile"].get("base_currency", "NZD")
    st.caption(_tr(language, "输入当前持仓数量或金额。若填写数量且能取得价格，系统会估算市值；若填写金额，则优先使用金额。", "Enter current holding quantity or amount. If quantity has a price, market value is estimated; amount takes priority."))

    default_rows = _default_holding_rows(settings, allocation)
    default_rows["currency"] = pd.Categorical(default_rows["currency"], categories=CURRENCIES)
    holdings = st.data_editor(
        default_rows,
        num_rows="dynamic",
        use_container_width=True,
        key="current_holdings_editor",
        column_config={
            "asset": st.column_config.TextColumn(_tr(language, "资产", "Asset")),
            "quantity": st.column_config.NumberColumn(_tr(language, "数量", "Quantity"), min_value=0.0, step=1.0),
            "amount": st.column_config.NumberColumn(_tr(language, "金额", "Amount"), min_value=0.0, step=100.0),
            "currency": st.column_config.SelectboxColumn(
                _tr(language, "货币", "Currency"),
                options=CURRENCIES,
                default=base_currency,
                required=True,
            ),
        },
    )
    holdings_frame = pd.DataFrame(holdings)
    if holdings_frame.empty:
        st.info(_tr(language, "请输入当前持仓。", "Enter current holdings."))
        return

    operation_frame, summary_frame, notes = _build_rebalance_advice(
        holdings_frame,
        allocation,
        settings,
        prices,
        base_currency,
        signal_date,
    )
    if notes:
        st.warning("\n".join(notes))
    st.dataframe(summary_frame, use_container_width=True, hide_index=True)
    st.dataframe(operation_frame, use_container_width=True, hide_index=True)


def _default_holding_rows(settings: dict[str, Any], allocation: Any) -> pd.DataFrame:
    execution = settings["execution"]
    assets = [
        allocation.core_asset,
        allocation.leveraged_asset or execution["leveraged_asset"],
        allocation.defensive_asset,
    ]
    rows = [
        {"asset": asset, "quantity": 0.0, "amount": 0.0, "currency": _asset_currency(asset, settings)}
        for asset in dict.fromkeys(assets)
        if asset
    ]
    return pd.DataFrame(rows)


def _build_rebalance_advice(
    holdings: pd.DataFrame,
    allocation: Any,
    settings: dict[str, Any],
    prices: dict[str, pd.DataFrame],
    base_currency: str,
    signal_date: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    language = _ui_language(settings)
    notes: list[str] = []
    current_values: dict[str, float] = {}
    for _, row in holdings.iterrows():
        asset = str(row.get("asset", "")).strip()
        if not asset:
            continue
        currency = str(row.get("currency", base_currency))
        amount = _safe_float(row.get("amount", 0.0))
        quantity = _safe_float(row.get("quantity", 0.0))
        if amount <= 0 and quantity > 0:
            price = _latest_price(asset, prices)
            if price is None:
                notes.append(_tr(language, f"无法取得 {asset} 价格；请手动填写金额。", f"Could not fetch a price for {asset}; enter the amount manually."))
                continue
            amount = quantity * price
            currency = _asset_currency(asset, settings)
        rate = _fx_rate(currency, base_currency)
        if rate is None:
            notes.append(_tr(language, f"无法取得 {currency}->{base_currency} 汇率；{asset} 暂按 1:1 估算。", f"Could not fetch {currency}->{base_currency} FX rate; estimating {asset} at 1:1."))
            rate = 1.0
        current_values[asset] = current_values.get(asset, 0.0) + amount * rate

    total_value = sum(current_values.values())
    targets = {
        allocation.core_asset: allocation.core_percent,
        allocation.defensive_asset: allocation.defensive_percent,
    }
    if allocation.leveraged_asset and allocation.leveraged_percent > 0:
        targets[allocation.leveraged_asset] = allocation.leveraged_percent
    elif settings["execution"]["leveraged_asset"] not in targets:
        targets[settings["execution"]["leveraged_asset"]] = 0.0
    for asset in current_values:
        targets.setdefault(asset, 0.0)

    target_values = {
        asset: total_value * target_percent / 100.0
        for asset, target_percent in targets.items()
    }
    cap_note = _apply_foreign_asset_cap_to_base_values(target_values, settings, base_currency)
    if cap_note:
        notes.append(cap_note)

    summary_rows = []
    operation_rows = []
    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    execution_market = settings["execution"].get("default_market", "us")
    execution_window = market_window(settings, execution_market).relevant_local_trading_window(datetime.now())
    for asset, target_value in target_values.items():
        current_value = current_values.get(asset, 0.0)
        target_percent = (target_value / total_value * 100.0) if total_value else 0.0
        delta = target_value - current_value
        action = _rebalance_action(asset, delta, language)
        trade_currency = _asset_currency(asset, settings)
        current_nzd = _convert_amount(current_value, base_currency, "NZD", notes, language)
        target_nzd = _convert_amount(target_value, base_currency, "NZD", notes, language)
        delta_nzd = _convert_amount(delta, base_currency, "NZD", notes, language)
        current_trade = _convert_amount(current_value, base_currency, trade_currency, notes, language)
        target_trade = _convert_amount(target_value, base_currency, trade_currency, notes, language)
        delta_trade = _convert_amount(delta, base_currency, trade_currency, notes, language)
        summary_rows.append(
            {
                _tr(language, "资产", "Asset"): asset,
                _tr(language, "操作货币", "Trade currency"): trade_currency,
                f"{_tr(language, '当前市值', 'Current value')}(NZD)": round(current_nzd, 2),
                f"{_tr(language, '当前市值', 'Current value')}({trade_currency})": round(current_trade, 2),
                _tr(language, "目标比例", "Target weight"): f"{target_percent:,.2f}%",
                f"{_tr(language, '目标市值', 'Target value')}(NZD)": round(target_nzd, 2),
                f"{_tr(language, '目标市值', 'Target value')}({trade_currency})": round(target_trade, 2),
                f"{_tr(language, '差额', 'Delta')}(NZD)": round(delta_nzd, 2),
                f"{_tr(language, '差额', 'Delta')}({trade_currency})": round(delta_trade, 2),
                _tr(language, "建议", "Suggestion"): action,
            }
        )
        if abs(delta) > 0.01:
            operation_rows.append(
                {
                    _tr(language, "运行时间", "Generated at"): generated_at,
                    _tr(language, "信号日期", "Signal date"): str(signal_date.date()),
                    _tr(language, "建议执行窗口", "Suggested execution window"): f"{execution_window[0]:%Y-%m-%d %H:%M} -> {execution_window[1]:%Y-%m-%d %H:%M}",
                    _tr(language, "资产", "Asset"): asset,
                    _tr(language, "操作", "Action"): action,
                    _tr(language, "操作货币", "Trade currency"): trade_currency,
                    f"{_tr(language, '金额', 'Amount')}(NZD)": round(abs(delta_nzd), 2),
                    f"{_tr(language, '金额', 'Amount')}({trade_currency})": round(abs(delta_trade), 2),
                }
            )
    if not operation_rows:
        operation_rows.append(
            {
                _tr(language, "运行时间", "Generated at"): generated_at,
                _tr(language, "信号日期", "Signal date"): str(signal_date.date()),
                _tr(language, "建议执行窗口", "Suggested execution window"): f"{execution_window[0]:%Y-%m-%d %H:%M} -> {execution_window[1]:%Y-%m-%d %H:%M}",
                _tr(language, "资产", "Asset"): _tr(language, "全部", "All"),
                _tr(language, "操作", "Action"): _tr(language, "不操作", "Hold"),
                _tr(language, "操作货币", "Trade currency"): base_currency,
                f"{_tr(language, '金额', 'Amount')}(NZD)": 0.0,
                f"{_tr(language, '金额', 'Amount')}({base_currency})": 0.0,
            }
        )
    return pd.DataFrame(operation_rows), pd.DataFrame(summary_rows), notes


def _convert_amount(
    amount: float,
    source_currency: str,
    target_currency: str,
    notes: list[str],
    language: str,
) -> float:
    if source_currency == target_currency:
        return amount
    rate = _fx_rate(source_currency, target_currency)
    if rate is None:
        notes.append(
            _tr(
                language,
                f"无法取得 {source_currency}->{target_currency} 汇率；暂按 1:1 估算。",
                f"Could not fetch {source_currency}->{target_currency} FX rate; estimating at 1:1.",
            )
        )
        rate = 1.0
    return amount * rate


def _apply_foreign_asset_cap_to_base_values(
    target_values: dict[str, float],
    settings: dict[str, Any],
    base_currency: str,
) -> str | None:
    language = _ui_language(settings)
    if base_currency == "NZD":
        return _translate_cap_note(apply_foreign_asset_cap_to_values(target_values, settings), language)

    nzd_values: dict[str, float] = {}
    for asset, value in target_values.items():
        rate = _fx_rate(base_currency, "NZD")
        nzd_values[asset] = value * (rate or 1.0)
    note = apply_foreign_asset_cap_to_values(nzd_values, settings)
    if not note:
        return None
    target_values.clear()
    for asset, value in nzd_values.items():
        rate = _fx_rate("NZD", base_currency)
        target_values[asset] = value * (rate or 1.0)
    return _translate_cap_note(note, language)


def _translate_cap_note(note: str | None, language: str) -> str | None:
    if not note or language == "zh":
        return note
    return (
        "Foreign/FIF target value has been capped at the configured NZD limit. "
        "NZX/ASX assets are excluded from this cap, and the excess has been moved to the local defensive asset."
    )


def _rebalance_action(asset: str, delta: float, language: str) -> str:
    if asset.startswith("未分配"):
        return _tr(language, "人工处理", "Manual")
    if delta > 0:
        return _tr(language, "买入", "Buy")
    if delta < 0:
        return _tr(language, "卖出", "Sell")
    return _tr(language, "不操作", "Hold")


def _zoomable_line_chart(
    frame: pd.DataFrame,
    columns: list[str],
    title: str,
    key: str,
    language: str,
    line_styles: dict[str, str] | None = None,
) -> None:
    shared_render_lightweight_chart(
        frame,
        columns,
        title,
        key=key,
        label_resolver=lambda series: _series_label(series, language),
        line_styles=line_styles,
    )


def _series_label(series: str, language: str) -> str:
    labels = {
        "equity": ("策略净值", "Strategy equity"),
        "buy_hold_equity": ("S&P 500 持有", "S&P 500 buy & hold"),
        "leveraged_buy_hold_equity": ("3 倍 S&P 500 买入持有", "3x S&P 500 buy & hold"),
        "ma120_timing_equity": ("S&P 500 120 日择时", "S&P 500 120-day timing"),
        "leveraged_ma120_timing_equity": ("三倍持有：跌破 120 日均线转现金", "3x Hold: Cash Below 120MA"),
        "target_exposure": ("目标等效仓位", "Target equivalent exposure"),
        "actual_equivalent_exposure": ("实际等效仓位", "Actual equivalent exposure"),
        "overnight_equivalent_exposure": ("隔夜等效仓位", "Overnight equivalent exposure"),
        "intraday_equivalent_exposure": ("日内等效仓位", "Intraday equivalent exposure"),
        "post_close_equivalent_exposure": ("收盘后等效仓位", "Post-close equivalent exposure"),
        "pending_next_open_equivalent_exposure": ("下次开盘等效仓位", "Next-open equivalent exposure"),
        "current_config": ("当前配置", "Current config"),
        "default_config": ("默认配置", "Default config"),
        "best_individual": ("最佳单参数", "Best individual"),
        "best_unified": ("最佳统一参数", "Best unified"),
        "health_price": ("价格", "Price"),
        "health_ma120": ("120 日均线", "120-day MA"),
        "health_ma200": ("200 日均线", "200-day MA"),
    }
    zh, en = labels.get(series, (series, series))
    return _tr(language, zh, en)


def _latest_price(asset: str, prices: dict[str, pd.DataFrame]) -> float | None:
    frame = prices.get(asset)
    if frame is None or frame.empty:
        return None
    close = _close_series(frame)
    if close is None or close.dropna().empty:
        return None
    return float(close.dropna().iloc[-1])


def _asset_currency(asset: str, settings: dict[str, Any]) -> str:
    normalized = asset.strip().upper()
    if asset.lower() == "cash":
        return settings["profile"].get("base_currency", "NZD")
    if normalized.endswith((".NZ", ".NZX")):
        return "NZD"
    if normalized.endswith((".AX", ".ASX")):
        return "AUD"
    return "USD"


def _counts_toward_foreign_cap(asset: str) -> bool:
    normalized = asset.strip().upper()
    if not normalized or normalized.startswith("未分配"):
        return False
    if normalized == "CASH":
        return False
    return counts_toward_foreign_cap(asset)


@st.cache_data(ttl=3600)
def _fx_rate(currency: str, base_currency: str) -> float | None:
    if currency == base_currency:
        return 1.0
    try:
        import yfinance as yf

        symbol = f"{currency}{base_currency}=X"
        data = yf.download(symbol, period="5d", auto_adjust=True, progress=False)
        if data.empty:
            return None
        close = _close_series(data)
        if close is None:
            return None
        close = close.dropna()
        if close.empty:
            return None
        return float(close.iloc[-1])
    except Exception:
        return None


def _close_series(frame: pd.DataFrame) -> pd.Series | None:
    if isinstance(frame.columns, pd.MultiIndex):
        if "Close" not in frame.columns.get_level_values(0):
            return None
        close = frame["Close"]
        if isinstance(close, pd.DataFrame):
            if close.empty:
                return None
            return close.iloc[:, 0]
        return close
    if "Close" not in frame.columns:
        return None
    return frame["Close"]


def _safe_float(value: Any) -> float:
    try:
        if pd.isna(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _pdf_download_button(
    language: str,
    label: str,
    data: bytes,
    filename: str,
    *,
    key: str,
) -> None:
    st.download_button(
        label,
        data=data,
        file_name=filename,
        mime="application/pdf",
        use_container_width=True,
        key=key,
        help=_tr(language, "导出当前页面摘要、策略信息和关键指标。", "Export the current page summary, strategy information, and key metrics."),
    )


def _disabled_pdf_button(language: str, label: str, *, key: str) -> None:
    st.download_button(
        label,
        data=b"",
        file_name="report.pdf",
        mime="application/pdf",
        use_container_width=True,
        key=key,
        disabled=True,
        help=_tr(language, "请先更新或运行当前页面，再生成 PDF。", "Update or run the current page before generating a PDF."),
    )


def _build_pdf_report(
    title: str,
    settings: dict[str, Any],
    language: str,
    *,
    sections: list[tuple[str, list[tuple[str, str]]]],
    charts: list[tuple[str, pd.DataFrame, list[str]]] | None = None,
    notes: list[str] | None = None,
) -> bytes:
    buffer = BytesIO()
    font_name = _pdf_font_name()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=18,
        leading=24,
        spaceAfter=8,
    )
    heading_style = ParagraphStyle(
        "ReportHeading",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=12,
        leading=16,
        spaceBefore=8,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=9,
        leading=13,
    )
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    story: list[Any] = [
        Paragraph(_pdf_escape(title), title_style),
        Paragraph(
            _pdf_escape(
                f"{_tr(language, '生成日期', 'Generated')}: {date.today().isoformat()}    "
                f"{_tr(language, '配置', 'Profile')}: {_profile_name(settings)}"
            ),
            body_style,
        ),
        Spacer(1, 6),
    ]
    strategy_section_title = _tr(language, "策略信息", "Strategy Information")
    for index, (section_title, rows) in enumerate(sections):
        if index > 0 and section_title == strategy_section_title:
            story.append(PageBreak())
        story.append(Paragraph(_pdf_escape(section_title), heading_style))
        story.append(_pdf_table(rows, font_name, body_style))
        story.append(Spacer(1, 4))
    if charts:
        story.append(PageBreak())
        story.append(Paragraph(_pdf_escape(_tr(language, "曲线和折线", "Curves and Lines")), heading_style))
        for chart_title, frame, columns in charts:
            drawing = _pdf_line_chart(frame, columns, chart_title, language)
            if drawing is None:
                continue
            story.append(Paragraph(_pdf_escape(chart_title), body_style))
            story.append(drawing)
            story.append(Spacer(1, 8))
    if notes:
        story.append(Paragraph(_pdf_escape(_tr(language, "说明", "Notes")), heading_style))
        for note in notes:
            story.append(Paragraph(_pdf_escape(str(note)), body_style))
    doc.build(story)
    return buffer.getvalue()


def _pdf_table(rows: list[tuple[str, str]], font_name: str, body_style: ParagraphStyle) -> Table:
    table_data = [
        [Paragraph(_pdf_escape(str(label)), body_style), Paragraph(_pdf_escape(str(value)), body_style)]
        for label, value in rows
    ]
    table = Table(table_data, colWidths=[62 * mm, 105 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LEADING", (0, 0), (-1, -1), 12),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F5F5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _pdf_line_chart(
    frame: pd.DataFrame,
    columns: list[str],
    title: str,
    language: str,
) -> Drawing | None:
    if frame.empty:
        return None
    available = [column for column in columns if column in frame.columns]
    if not available:
        return None
    data = frame[available].dropna(how="all")
    if data.empty:
        return None

    width = 170 * mm
    height = 72 * mm
    left = 16 * mm
    right = 8 * mm
    top = 8 * mm
    bottom = 15 * mm
    plot_width = width - left - right
    plot_height = height - top - bottom
    drawing = Drawing(width, height)
    axis_color = colors.HexColor("#666666")
    drawing.add(Line(left, top + plot_height, left + plot_width, top + plot_height, strokeColor=axis_color, strokeWidth=0.5))
    drawing.add(Line(left, top, left, top + plot_height, strokeColor=axis_color, strokeWidth=0.5))

    values = data[available].astype(float)
    y_min = float(values.min().min())
    y_max = float(values.max().max())
    if y_min == y_max:
        y_min -= 1.0
        y_max += 1.0
    padding = (y_max - y_min) * 0.05
    y_min -= padding
    y_max += padding
    denominator = y_max - y_min
    x_count = max(len(values.index) - 1, 1)
    palette = [
        colors.HexColor("#1f77b4"),
        colors.HexColor("#d62728"),
        colors.HexColor("#2ca02c"),
        colors.HexColor("#9467bd"),
        colors.HexColor("#ff7f0e"),
        colors.HexColor("#17becf"),
        colors.HexColor("#8c564b"),
        colors.HexColor("#7f7f7f"),
    ]
    font_name = _pdf_font_name()

    def point(row_index: int, value: float) -> tuple[float, float]:
        x = left + plot_width * (row_index / x_count)
        y = top + plot_height - ((value - y_min) / denominator) * plot_height
        return x, y

    for series_index, column in enumerate(available):
        series = values[column].dropna()
        if series.empty:
            continue
        last_x = last_y = None
        color = palette[series_index % len(palette)]
        for row_index, value in enumerate(values[column].tolist()):
            if pd.isna(value):
                last_x = last_y = None
                continue
            x, y = point(row_index, float(value))
            if last_x is not None and last_y is not None:
                drawing.add(Line(last_x, last_y, x, y, strokeColor=color, strokeWidth=1.2))
            last_x, last_y = x, y
        legend_x = left + (series_index % 2) * 74 * mm
        legend_y = height - 4 * mm - (series_index // 2) * 5 * mm
        drawing.add(Line(legend_x, legend_y, legend_x + 8 * mm, legend_y, strokeColor=color, strokeWidth=1.5))
        drawing.add(String(legend_x + 10 * mm, legend_y - 2, _series_label(column, language), fontName=font_name, fontSize=6.5, fillColor=colors.black))

    drawing.add(String(left, 3 * mm, str(data.index.min())[:10], fontName=font_name, fontSize=6, fillColor=axis_color))
    drawing.add(String(left + plot_width - 22 * mm, 3 * mm, str(data.index.max())[:10], fontName=font_name, fontSize=6, fillColor=axis_color))
    drawing.add(String(1 * mm, top, f"{y_min:,.0f}", fontName=font_name, fontSize=6, fillColor=axis_color))
    drawing.add(String(1 * mm, top + plot_height - 3, f"{y_max:,.0f}", fontName=font_name, fontSize=6, fillColor=axis_color))
    return drawing


def _pdf_font_name() -> str:
    font_name = "ReportCJK"
    if font_name in pdfmetrics.getRegisteredFontNames():
        return font_name
    for path in (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ):
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont(font_name, path))
                return font_name
            except Exception:
                continue
    return "Helvetica"


def _pdf_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def _strategy_summary_rows(settings: dict[str, Any], language: str) -> list[tuple[str, str]]:
    trend = settings["trend"]
    position = settings["position"]
    execution = settings["execution"]
    rules = settings["vix"]["rules"]
    return [
        (_tr(language, "配置名称", "Profile"), _profile_name(settings)),
        (_tr(language, "核心标的", "Primary symbol"), settings["signals"]["primary"]),
        (_tr(language, "执行市场", "Execution market"), execution.get("default_market", "us")),
        (_tr(language, "核心资产", "Core asset"), execution.get("core_asset", "")),
        (_tr(language, "ASX 核心资产", "ASX core asset"), execution.get("asx_core_asset", "")),
        (_tr(language, "杠杆资产", "Leveraged asset"), execution.get("leveraged_asset", "")),
        (_tr(language, "防御资产", "Defensive asset"), execution.get("defensive_asset", "")),
        (_tr(language, "仓位下限 / 上限", "Exposure floor / cap"), f"{position.get('min_exposure', 0)}% / {position.get('max_exposure', 0)}%"),
        (_tr(language, "趋势均线", "Trend MAs"), f"{trend.get('short_window')} / {trend.get('medium_window')} / {trend.get('long_window')}"),
        (_tr(language, "确认天数", "Confirmation days"), str(trend.get("confirmation_days", 1))),
        (_tr(language, "允许杠杆", "Allow leverage"), str(execution.get("allow_leverage", False))),
        (_tr(language, "VIX 分档乘数", "VIX tier multipliers"), ", ".join(f"{rule.get('label')}: {rule.get('multiplier')}" for rule in rules)),
        (_tr(language, "阴跌识别", "Slow-decline detection"), str(position.get("trend_quality_ma_cross_slow_decline_enabled", False))),
        (_tr(language, "阴跌可降至 0", "Slow-decline zero floor"), str(position.get("trend_quality_slow_decline_zero_floor_enabled", False))),
    ]


def _trade_summary_rows(trades: pd.DataFrame, language: str) -> list[tuple[str, str]]:
    if trades.empty:
        return []
    rows: list[tuple[str, str]] = []
    for _, trade in trades.tail(10).iterrows():
        label = str(trade.get("date", ""))
        value = (
            f"{_tr(language, '目标', 'Target')} {float(trade.get('target_exposure', 0)):,.0f}% | "
            f"{_tr(language, '核心', 'Core')} {float(trade.get('core_percent', 0)):,.1f}% | "
            f"{_tr(language, '杠杆', 'Leverage')} {float(trade.get('leveraged_percent', 0)):,.1f}% | "
            f"{_tr(language, '防御', 'Defensive')} {float(trade.get('local_defensive_percent', 0)):,.1f}%"
        )
        rows.append((label, value))
    return rows


def _pdf_filename(
    event: str,
    settings: dict[str, Any],
    *,
    range_text: str | None = None,
    cagr: float | None = None,
) -> str:
    parts = [date.today().isoformat(), event, _profile_name(settings)]
    if range_text:
        parts.append(range_text)
    if cagr is not None:
        parts.append(f"cagr-{float(cagr):.2f}pct")
    return f"{'_'.join(_filename_slug(part) for part in parts if part)}.pdf"


def _profile_name(settings: dict[str, Any]) -> str:
    return str(settings.get("profile", {}).get("name") or "default")


def _filename_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "-", str(value).strip())
    return slug.strip("-") or "report"


def _fingerprint(settings: dict[str, Any], extras: dict[str, str]) -> str:
    return shared_fingerprint(settings, extras)


def _is_stale(session_key: str, settings: dict[str, Any], extras: dict[str, str]) -> bool:
    return shared_is_stale(session_key, settings, extras)


def _state_label(label: str, language: str) -> str:
    labels = {
        "risk_off": ("风险关闭", "Risk off"),
        "accelerating_bull": ("加速牛市", "Accelerating bull"),
        "confirmed_bull": ("确认牛市", "Confirmed bull"),
        "allowed": ("允许持仓", "Allowed"),
        "risk_watch": ("风险观察", "Risk watch"),
        "low": ("低波动", "Low"),
        "normal": ("正常波动", "Normal"),
        "danger": ("高风险", "Danger"),
        "crisis": ("危机", "Crisis"),
    }
    zh, en = labels.get(label, (label, label))
    return _tr(language, zh, en)


def _vix_multiplier_note(label: str, language: str = "zh") -> str:
    notes = {
        "low": (
            "低波动环境的奖励系数。调高会在平稳牛市中更积极加仓，调低会更保守。",
            "Reward multiplier for low-volatility conditions. Higher values add exposure more aggressively.",
        ),
        "normal": (
            "普通波动环境的基准系数。通常保持 1.0，表示不额外奖励也不惩罚。",
            "Baseline multiplier for normal volatility. Usually kept at 1.0.",
        ),
        "danger": (
            "高波动环境的风险折扣。调低会更快降仓，调高会容忍更多震荡。",
            "Risk discount for high volatility. Lower values reduce exposure faster.",
        ),
        "crisis": (
            "极端恐慌环境的保护系数。调低会更接近撤退，调高会保留更多市场暴露。",
            "Protection multiplier for crisis conditions. Lower values move closer to exiting.",
        ),
    }
    zh, en = notes.get(label, ("仓位修正系数。大于 1 会放大仓位，小于 1 会降低仓位。", "Exposure adjustment multiplier. Above 1 increases exposure; below 1 reduces it."))
    return _tr(language, zh, en)


if __name__ == "__main__":
    main()
