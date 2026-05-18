from __future__ import annotations

from io import BytesIO
from copy import deepcopy
from datetime import date, datetime, timedelta
import hashlib
import html
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st
import toml
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Line, String
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from trend_system.backtest import build_parameter_sweep_candidate, run_backtest, run_parameter_sweep
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
from trend_system.models import BacktestRequest, DailySignalRequest, HealthcheckRequest
from trend_system.interfaces.streamlit.app_shell import render_app_shell
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
    fingerprint as shared_fingerprint,
    is_stale as shared_is_stale,
    model_settings as shared_model_settings,
    option_index as shared_option_index,
    release_notes_path as shared_release_notes_path,
    release_notes_text as shared_release_notes_text,
    render_lightweight_chart as shared_render_lightweight_chart,
    render_release_notes as shared_render_release_notes,
    tr as shared_tr,
    ui_language as shared_ui_language,
)
from trend_system.interfaces.streamlit.shared.world_map import build_world_map_markup, build_world_map_text
from trend_system.portfolio import build_allocation
from trend_system.services.backtest_service import run_backtest_use_case
from trend_system.services.daily_signal_service import run_daily_signal
from trend_system.services.healthcheck_service import run_healthcheck
from trend_system.signals import history_start_date
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


def _ui_theme(settings: dict[str, Any]) -> str:
    selected = st.session_state.get("ui_theme") or settings.get("ui", {}).get("theme", "dark")
    return selected if selected in {"dark", "light"} else "dark"


def _tr(language: str, zh: str, en: str) -> str:
    return shared_tr(language, zh, en)


def _as_settings(settings: dict[str, Any]) -> Settings:
    return Settings(raw=settings, path=DEFAULT_CONFIG)


def _apply_session_preferences(settings: dict[str, Any]) -> None:
    ui = settings.setdefault("ui", {})
    profile = settings.setdefault("profile", {})
    if "settings_ui_language" in st.session_state:
        st.session_state["ui_language"] = st.session_state["settings_ui_language"]
    if "header_ui_language" in st.session_state:
        st.session_state["ui_language"] = "en" if st.session_state["header_ui_language"] == "EN" else "zh"
    if "settings_ui_theme" in st.session_state:
        st.session_state["ui_theme"] = st.session_state["settings_ui_theme"]
    if "header_ui_theme" in st.session_state:
        st.session_state["ui_theme"] = st.session_state["header_ui_theme"]
    if "settings_home_timezone" in st.session_state:
        st.session_state["home_timezone"] = st.session_state["settings_home_timezone"]
    if "settings_base_currency" in st.session_state:
        st.session_state["base_currency"] = st.session_state["settings_base_currency"]
    if "ui_language" in st.session_state:
        ui["language"] = st.session_state["ui_language"]
    if "ui_theme" in st.session_state:
        ui["theme"] = st.session_state["ui_theme"]
    if "home_timezone" in st.session_state:
        profile["home_timezone"] = st.session_state["home_timezone"]
    if "base_currency" in st.session_state:
        profile["base_currency"] = st.session_state["base_currency"]


def main() -> None:
    st.set_page_config(
        page_title="LEOLRS0-3",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        """
<style>
/* ── Design tokens ─────────────────────────────────────── */
:root {
  --leo-ink:          #111214;
  --leo-ink-sub:      rgba(17, 18, 20, 0.78);
  --leo-kicker:       rgba(18, 57, 91, 0.85);
  --text-color:       #111214;
  --text-muted:       rgba(17, 18, 20, 0.78);
  --panel-warm:       rgba(174, 143, 84, 0.25);
  --panel-fill-a:     rgba(244, 240, 232, 0.25);
  --panel-fill-b:     rgba(255, 255, 255, 0.10);
  --leo-surface-a:    rgba(244, 240, 232, 0.25);
  --leo-surface-b:    rgba(255, 255, 255, 0.10);
  --leo-surface-chip: rgba(255, 255, 255, 0.14);
  --leo-surface-rim:  rgba(174, 143, 84, 0.22);
  --leo-surface-top:  rgba(255, 255, 255, 0.17);
  --leo-surface-bot:  rgba(174, 143, 84, 0.06);
  --leo-metal-glow:   rgba(174, 143, 84, 0.12);
  --leo-light-x:      50%;
  --leo-light-y:      -8%;
  --leo-light-drift:  0px;
  --leo-scroll-energy: 0;
  --leo-prussian-mineral: rgba(18, 57, 91, 0.88);
  --leo-prussian-haze: rgba(74, 110, 150, 0.18);
  --leo-racing-green: rgba(31, 106, 83, 0.88);
  --leo-racing-green-haze: rgba(31, 106, 83, 0.18);
  --leo-palace-red: rgba(158, 47, 47, 0.88);
  --leo-palace-red-haze: rgba(158, 47, 47, 0.16);
  /* Pearl switch shell — 25% opacity */
  --leo-sw-bg:        rgba(244, 240, 232, 0.25);
  --leo-sw-rim:       rgba(174, 143, 84, 0.24);
  --leo-sw-inner:     rgba(255, 255, 255, 0.31);
  --leo-sw-shadow:    rgba(26, 29, 31, 0.10);
  --leo-sw-text:      rgba(17, 18, 20, 0.72);
  --leo-sw-text-on:   #111214;
  /* Active beads */
  --leo-bead-en:      rgba(31, 106, 83, 0.92);
  --leo-bead-en-txt:  #F4F0E8;
  --leo-bead-zh:      rgba(31, 106, 83, 0.92);
  --leo-bead-zh-txt:  #F4F0E8;
}
/* ── Light mode — explicit black text ──────────────────── */
html[data-theme="light"],
body[data-theme="light"],
[data-theme="light"] {
  --leo-ink:      #0A0C0D;
  --leo-ink-sub:  rgba(10, 12, 13, 0.82);
  --leo-kicker:   rgb(18, 57, 91);
  --text-color:   #0A0C0D;
  --text-muted:   rgba(10, 12, 13, 0.82);
  --panel-warm:   rgba(174, 143, 84, 0.25);
  --panel-fill-a: rgba(244, 240, 232, 0.25);
  --panel-fill-b: rgba(255, 255, 255, 0.10);
  --leo-surface-a:    rgba(244, 240, 232, 0.25);
  --leo-surface-b:    rgba(255, 255, 255, 0.10);
  --leo-surface-chip: rgba(255, 255, 255, 0.14);
  --leo-surface-rim:  rgba(174, 143, 84, 0.22);
  --leo-surface-top:  rgba(255, 255, 255, 0.17);
  --leo-surface-bot:  rgba(174, 143, 84, 0.06);
  --leo-metal-glow:   rgba(174, 143, 84, 0.12);
  --leo-sw-text:      rgba(17, 18, 20, 0.72);
  --leo-sw-text-on:   #111214;
}
html[data-theme="dark"],
body[data-theme="dark"],
[data-theme="dark"] {
  --leo-ink:        rgba(244, 240, 232, 0.92);
  --leo-ink-sub:    rgba(244, 240, 232, 0.60);
  --leo-kicker:     rgba(244, 240, 232, 0.86);
  --text-color:     rgba(244, 240, 232, 0.92);
  --text-muted:     rgba(244, 240, 232, 0.60);
  --panel-warm:     rgba(174, 143, 84, 0.10);
  --panel-fill-a:   rgba(26, 29, 31, 0.74);
  --panel-fill-b:   rgba(0, 0, 0, 0.22);
  --leo-surface-a:  rgba(26, 29, 31, 0.25);
  --leo-surface-b:  rgba(244, 240, 232, 0.06);
  --leo-surface-chip: rgba(244, 240, 232, 0.08);
  --leo-surface-rim: rgba(174, 143, 84, 0.18);
  --leo-surface-top: rgba(255, 255, 255, 0.05);
  --leo-surface-bot: rgba(174, 143, 84, 0.05);
  --leo-metal-glow: rgba(174, 143, 84, 0.10);
  --leo-sw-bg:      rgba(26, 29, 31, 0.25);
  --leo-sw-rim:     rgba(174, 143, 84, 0.22);
  --leo-sw-inner:   rgba(255, 255, 255, 0.06);
  --leo-sw-shadow:  rgba(0, 0, 0, 0.40);
  --leo-sw-text:    rgba(244, 240, 232, 0.65);
  --leo-sw-text-on: rgba(244, 240, 232, 0.95);
}
/* ── Shell layout ──────────────────────────────────────── */
html,
body,
#root,
.stApp,
[data-testid="stAppViewContainer"] {
  height: 100% !important;
  min-height: 100vh !important;
}
body,
#root,
.stApp {
  overflow: visible !important;
  color: var(--text-color) !important;
}
[data-testid="stAppViewContainer"] {
  position: relative !important;
  inset: auto !important;
  overflow: visible !important;
  color: var(--text-color) !important;
}
[data-testid="stMain"],
[data-testid="stMainBlockContainer"] {
  min-height: 100vh !important;
  color: var(--text-color) !important;
}
.block-container {
  overflow-x: hidden !important;
}
.stApp {
  position: relative;
}
.shell-title-band {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  margin-bottom: 0.2rem;
}
.shell-kicker {
  font-size: 0.62rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--leo-kicker);
}
.shell-title {
  font-size: clamp(1.3rem, 2.6vw, 1.8rem);
  line-height: 1;
  font-weight: 700;
  color: var(--text-color);
}
.shell-subtitle {
  font-size: 0.78rem;
  color: var(--text-muted);
}
/* Align segmented controls with title band vertically */
[data-testid="stHorizontalBlock"]:has(.shell-title-band) {
  align-items: center !important;
}
[data-testid="stHorizontalBlock"]:has(.shell-title-band) [data-testid="stSegmentedControl"] {
  margin: 0 !important;
}
/* ── Pearl language switch ─────────────────────────────── */
div[data-testid="stSegmentedControl"] > div {
  background:      var(--leo-sw-bg)    !important;
  border:          1px solid var(--leo-sw-rim) !important;
  border-radius:   999px               !important;
  padding:         3px                 !important;
  box-shadow:
    inset 0 1px 0 var(--leo-sw-inner),
    0 1px 4px var(--leo-sw-shadow)     !important;
  backdrop-filter: blur(6px)           !important;
  gap:             2px                 !important;
}
div[data-testid="stSegmentedControl"] button {
  border-radius:   999px       !important;
  border:          none        !important;
  background:      transparent !important;
  color:           var(--leo-sw-text) !important;
  font-size:       0.70rem     !important;
  font-weight:     500         !important;
  letter-spacing:  0.07em      !important;
  padding:         3px 11px    !important;
  transition:
    background 160ms cubic-bezier(0.25, 0.46, 0.45, 0.94),
    color      120ms ease,
    box-shadow 160ms ease      !important;
}
div[data-testid="stSegmentedControl"] button:nth-child(1)[aria-pressed="true"],
div[data-testid="stSegmentedControl"] button:nth-child(1)[aria-selected="true"] {
  background: var(--leo-bead-en)     !important;
  color:      var(--leo-bead-en-txt) !important;
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.10),
    0 1px 3px rgba(31,106,83,0.24)   !important;
}
div[data-testid="stSegmentedControl"] button:nth-child(2)[aria-pressed="true"],
div[data-testid="stSegmentedControl"] button:nth-child(2)[aria-selected="true"] {
  background: var(--leo-bead-zh)     !important;
  color:      var(--leo-bead-zh-txt) !important;
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.08),
    0 1px 3px rgba(31,106,83,0.24)   !important;
}
div[data-testid="stSegmentedControl"] button:not([aria-pressed="true"]):not([aria-selected="true"]):hover {
  color:      var(--leo-sw-text-on)  !important;
  background: rgba(174,143,84,0.05)  !important;
}
div[data-testid="stSegmentedControl"] button:focus-visible {
  outline:        1.5px solid rgba(174,143,84,0.60) !important;
  outline-offset: 1px !important;
}
.strategy-console-intro {
  margin: 0.35rem 0 0.85rem;
  padding: 0.8rem 0.85rem 0.75rem;
  background: linear-gradient(145deg, var(--panel-fill-a), var(--panel-fill-b));
  border: 2px solid var(--leo-surface-rim);
  clip-path: polygon(0.75rem 0, calc(100% - 0.75rem) 0, 100% 0.75rem, 100% calc(100% - 0.75rem), calc(100% - 0.75rem) 100%, 0.75rem 100%, 0 calc(100% - 0.75rem), 0 0.75rem);
  box-shadow: inset 0 1px 0 var(--leo-surface-top), inset 0 -1px 0 var(--leo-surface-bot), 0 0 14px var(--leo-metal-glow);
  backdrop-filter: blur(8px);
}
.strategy-console-title {
  font-size: 0.84rem;
  font-weight: 700;
  margin-bottom: 0.3rem;
  color: var(--text-color);
}
.strategy-console-note {
  font-size: 0.73rem;
  color: var(--text-muted);
  margin-bottom: 0.5rem;
}
.strategy-console-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
.strategy-console-chip {
  display: inline-flex;
  align-items: center;
  min-height: 1.6rem;
  padding: 0.22rem 0.62rem;
  border-radius: 0;
  border: 1px solid var(--leo-surface-rim);
  background: var(--leo-surface-chip);
  box-shadow: inset 0 1px 0 var(--leo-surface-top);
  font-size: 0.72rem;
  color: var(--text-color);
  backdrop-filter: blur(6px);
}
/* ── Hard edge reset: all rectangular, no rounded / chamfered corners ── */
div[data-testid="stSegmentedControl"] > div,
div[data-testid="stSegmentedControl"] button,
.strategy-console-intro,
.strategy-console-chip,
.sidebar-section-plate,
.sidebar-control-cluster,
.sidebar-control-cluster .cluster-chip,
[data-testid="stMetric"],
[data-testid="stExpander"],
[data-testid="stVegaLiteChart"],
[data-testid="element-container"] > iframe,
[data-testid="stSidebar"] [data-baseweb="input"],
[data-testid="stSidebar"] [data-baseweb="base-input"],
[data-testid="stSidebar"] [data-baseweb="radio"] label,
[data-testid="stSidebar"] [role="switch"],
[data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button,
[data-testid="stSidebar"] [data-baseweb="slider"] > div:first-child > div,
[data-testid="stSidebar"] [data-baseweb="slider"] > div:first-child > div > div,
[data-testid="stSidebar"] [role="slider"],
.trade-timeline-wrap,
.trade-timeline-track,
.trade-timeline-segment,
.trade-action-item,
.timeline-countdown-card,
.timeline-legend-item span {
  border-radius: 0 !important;
  clip-path: none !important;
}
.sidebar-section-plate {
  margin: 0.55rem 0 0.5rem;
  padding: 0.55rem 0.7rem 0.5rem;
  background: linear-gradient(145deg, rgba(18,57,91,0.10), var(--panel-fill-b));
  border: 2px solid var(--leo-surface-rim);
  clip-path: polygon(0.6rem 0, calc(100% - 0.6rem) 0, 100% 0.6rem, 100% calc(100% - 0.6rem), calc(100% - 0.6rem) 100%, 0.6rem 100%, 0 calc(100% - 0.6rem), 0 0.6rem);
  box-shadow: inset 0 1px 0 var(--leo-surface-top), inset 0 -1px 0 var(--leo-surface-bot), 0 0 12px var(--leo-metal-glow);
  backdrop-filter: blur(8px);
}
.sidebar-section-overline {
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--leo-kicker);
  margin-bottom: 0.18rem;
}
.sidebar-section-title {
  font-size: 0.86rem;
  font-weight: 700;
  color: var(--text-color);
}
.sidebar-section-summary {
  font-size: 0.72rem;
  color: var(--text-muted);
  margin-top: 0.18rem;
}
.sidebar-control-cluster {
  margin: 0.42rem 0 0.62rem;
  padding: 0.68rem 0.72rem 0.6rem;
  background:
    radial-gradient(circle at top right, var(--leo-prussian-haze), transparent 42%),
    linear-gradient(145deg, var(--panel-fill-a), var(--panel-fill-b));
  border: 2px solid var(--leo-surface-rim);
  clip-path: polygon(0.72rem 0, calc(100% - 0.72rem) 0, 100% 0.72rem, 100% calc(100% - 0.72rem), calc(100% - 0.72rem) 100%, 0.72rem 100%, 0 calc(100% - 0.72rem), 0 0.72rem);
  box-shadow: inset 0 1px 0 var(--leo-surface-top), inset 0 -1px 0 var(--leo-surface-bot), 0 0 14px var(--leo-metal-glow);
  backdrop-filter: blur(8px);
}
.strategy-console-intro,
.sidebar-section-plate,
.sidebar-control-cluster,
[data-testid="stMetric"],
[data-testid="stExpander"],
[data-testid="stVegaLiteChart"],
[data-testid="element-container"] > iframe,
.trade-timeline-wrap,
.timeline-countdown-card {
  transition: box-shadow 180ms ease, border-color 180ms ease, transform 180ms ease;
}
.strategy-console-intro:hover,
.strategy-console-intro:focus-within,
.sidebar-section-plate:hover,
.sidebar-section-plate:focus-within,
.sidebar-control-cluster:hover,
.sidebar-control-cluster:focus-within,
[data-testid="stMetric"]:hover,
[data-testid="stExpander"]:hover,
[data-testid="stExpander"]:focus-within,
.trade-timeline-wrap:hover,
.trade-timeline-wrap:focus-within,
.timeline-countdown-card:hover {
  box-shadow:
    inset 0 1px 0 var(--leo-surface-top),
    inset 0 -1px 0 var(--leo-surface-bot),
    0 0 20px rgba(174, 143, 84, 0.20),
    0 0 38px rgba(255, 255, 255, 0.05) !important;
  border-color: rgba(174, 143, 84, 0.34) !important;
}
.sidebar-control-cluster.cluster-green {
  background:
    radial-gradient(circle at top right, var(--leo-racing-green-haze), transparent 42%),
    linear-gradient(145deg, var(--panel-fill-a), var(--panel-fill-b));
}
.sidebar-control-cluster.cluster-red {
  background:
    radial-gradient(circle at top right, var(--leo-palace-red-haze), transparent 42%),
    linear-gradient(145deg, var(--panel-fill-a), var(--panel-fill-b));
}
.sidebar-control-cluster .cluster-overline {
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--leo-kicker);
}
.sidebar-control-cluster .cluster-title {
  margin-top: 0.16rem;
  font-size: 0.94rem;
  font-weight: 700;
  color: var(--text-color);
}
.sidebar-control-cluster .cluster-summary {
  margin-top: 0.16rem;
  font-size: 0.72rem;
  line-height: 1.45;
  color: var(--text-muted);
}
.sidebar-control-cluster .cluster-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.34rem;
  margin-top: 0.45rem;
}
.sidebar-control-cluster .cluster-chip {
  display: inline-flex;
  align-items: center;
  min-height: 1.45rem;
  padding: 0.18rem 0.5rem;
  border-radius: 999px;
  border: 1px solid rgba(174, 143, 84, 0.16);
  background: rgba(255,255,255,0.07);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.08);
  font-size: 0.68rem;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}
/* ── Sidebar control language — Jack R inspired ───────── */
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] {
  margin-bottom: 0.26rem !important;
}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
  font-size: 0.63rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.11em !important;
  text-transform: uppercase !important;
  color: var(--leo-racing-green) !important;
}
[data-testid="stSidebar"] [data-baseweb="input"],
[data-testid="stSidebar"] [data-baseweb="base-input"] {
  background: linear-gradient(145deg, var(--panel-fill-a), var(--panel-fill-b)) !important;
  border: 1px solid var(--leo-surface-rim) !important;
  border-radius: 0 !important;
  box-shadow: inset 0 1px 0 var(--leo-surface-top), inset 0 -1px 0 var(--leo-surface-bot) !important;
  backdrop-filter: blur(8px) !important;
}
[data-testid="stSidebar"] [data-baseweb="input"] input,
[data-testid="stSidebar"] [data-baseweb="base-input"] input {
  color: var(--text-color) !important;
  font-size: 0.92rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.01em !important;
}
[data-testid="stSidebar"] [data-baseweb="input"] input::placeholder,
[data-testid="stSidebar"] [data-baseweb="base-input"] input::placeholder {
  color: var(--text-muted) !important;
}
[data-testid="stSidebar"] [data-baseweb="input"]:focus-within,
[data-testid="stSidebar"] [data-baseweb="base-input"]:focus-within {
  border-color: rgba(31, 106, 83, 0.34) !important;
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.10),
    0 0 0 1px rgba(31, 106, 83, 0.14) !important;
}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
  font-size: 0.70rem !important;
  line-height: 1.45 !important;
  color: var(--text-muted) !important;
}
[data-testid="stSidebar"] [data-baseweb="radio"] {
  gap: 0.45rem !important;
}
[data-testid="stSidebar"] [data-baseweb="radio"] label {
  min-height: 2rem !important;
  padding: 0.18rem 0.32rem !important;
  border: 1px solid transparent !important;
  border-radius: 999px !important;
  background: linear-gradient(145deg, rgba(255,255,255,0.10), rgba(31,106,83,0.05)) !important;
}
[data-testid="stSidebar"] [data-baseweb="radio"] input:checked + div,
[data-testid="stSidebar"] [data-baseweb="radio"] input:checked ~ div {
  border-color: rgba(31, 106, 83, 0.24) !important;
}
[data-testid="stSidebar"] [data-baseweb="radio"] label p {
  font-size: 0.72rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.08em !important;
}
[data-testid="stSidebar"] [role="switch"] {
  background: linear-gradient(90deg, rgba(31,106,83,0.16), rgba(31,106,83,0.08)) !important;
  border: 1px solid var(--leo-surface-rim) !important;
  border-radius: 999px !important;
  box-shadow: inset 0 1px 0 var(--leo-surface-top) !important;
}
[data-testid="stSidebar"] [role="switch"][aria-checked="true"] {
  background: linear-gradient(90deg, rgba(31,106,83,0.28), rgba(31,106,83,0.20)) !important;
  border-color: rgba(31, 106, 83, 0.26) !important;
  box-shadow: inset 0 1px 0 var(--leo-surface-top), 0 0 14px rgba(31,106,83,0.18) !important;
}
[data-testid="stSidebar"] [role="switch"] > div {
  background: linear-gradient(145deg, rgba(244,240,232,0.86), rgba(217,208,188,0.74)) !important;
  box-shadow: 0 1px 3px rgba(17,18,20,0.18), inset 0 1px 0 rgba(255,255,255,0.34) !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {
  min-height: 2.2rem !important;
  display: flex !important;
  align-items: center !important;
  padding-inline: 0.2rem !important;
}
[data-testid="stSidebar"] [data-testid="stExpanderDetails"] {
  padding-top: 0.35rem !important;
}
[data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button {
  min-height: 2.55rem !important;
  background:
    radial-gradient(circle at 24% 28%, rgba(255,255,255,0.14) 0, transparent 28%),
    linear-gradient(145deg, rgba(158,47,47,0.92), rgba(128,38,38,0.96)) !important;
  border: 1px solid rgba(174, 143, 84, 0.22) !important;
  border-radius: 0 !important;
  clip-path: polygon(0.7rem 0, calc(100% - 0.7rem) 0, 100% 0.7rem,
             100% calc(100% - 0.7rem), calc(100% - 0.7rem) 100%,
             0.7rem 100%, 0 calc(100% - 0.7rem), 0 0.7rem) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.10), 0 2px 8px rgba(158,47,47,0.16) !important;
  color: rgba(244,240,232,0.96) !important;
  font-size: 0.76rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.12em !important;
  text-transform: uppercase !important;
}
[data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button:hover {
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.10), 0 4px 10px rgba(158,47,47,0.22) !important;
  border-color: rgba(174, 143, 84, 0.30) !important;
}
[data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button:focus-visible {
  outline: 1.5px solid rgba(158,47,47,0.36) !important;
  outline-offset: 2px !important;
}
[data-theme="dark"] [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
[data-theme="dark"] [data-testid="stSidebar"] [data-baseweb="radio"] label p,
[data-theme="dark"] [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
[data-theme="dark"] [data-testid="stSidebar"] [data-baseweb="slider"] [data-testid="stThumbValue"] {
  color: rgba(244, 240, 232, 0.92) !important;
}
/* ── Section header ────────────────────────────────────── */
.leo-section-head {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  margin: 1.1rem 0 0.65rem;
  padding-bottom: 0.35rem;
  border-bottom: 1px solid rgba(174, 143, 84, 0.40);
}
.leo-section-overline {
  font-size: 0.66rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--leo-kicker);
  white-space: nowrap;
}
.leo-section-rule {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, rgba(174,143,84,0.38) 0%, transparent 100%);
}
.leo-section-head--backtest .leo-section-overline {
  font-size: 0.84rem;
  letter-spacing: 0.14em;
}
/* ── Section dot markers ───────────────────────────────── */
.leo-section-dot {
  display:     inline-block;
  width:       0.36rem;
  height:      0.36rem;
  background:  rgba(174, 143, 84, 0.80);
  flex-shrink: 0;
}
.leo-section-head--prussian .leo-section-dot      { background:   rgba(18, 57, 91, 0.85); }
.leo-section-head--prussian .leo-section-overline { color:        rgba(18, 57, 91, 0.80); }
.leo-section-head--prussian                       { border-bottom-color: rgba(18, 57, 91, 0.38); }
.leo-section-head--green .leo-section-dot         { background:   rgba(22, 74, 60, 0.85); }
.leo-section-head--green .leo-section-overline    { color:        rgba(22, 74, 60, 0.80); }
.leo-section-head--green                          { border-bottom-color: rgba(22, 74, 60, 0.18); }
.leo-section-head--red .leo-section-dot           { background:   rgba(158, 47, 47, 0.85); }
.leo-section-head--red .leo-section-overline      { color:        rgba(158, 47, 47, 0.80); }
.leo-section-head--red                            { border-bottom-color: rgba(158, 47, 47, 0.18); }
/* ── st.subheader override ─────────────────────────────── */
[data-testid="stHeading"] h3 {
  font-size: 0.66rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.16em !important;
  text-transform: uppercase !important;
  color: var(--leo-kicker) !important;
  border-bottom: 1px solid rgba(174, 143, 84, 0.22);
  padding-bottom: 0.35rem;
  margin-bottom: 0.65rem;
}
[data-theme="dark"] [data-testid="stHeading"] h3 {
  color: rgba(244, 240, 232, 0.94) !important;
}
/* ── Main interaction surfaces — user-driven inputs ───── */
[data-testid="stMain"] [data-testid="stWidgetLabel"] p,
[data-testid="stMain"] [data-testid="stWidgetLabel"] span {
  color: rgba(74, 190, 138, 0.95) !important;
  letter-spacing: 0.08em !important;
  white-space: nowrap !important;
  font-size: 0.76rem !important;
}
[data-testid="stMain"] p,
[data-testid="stMain"] label,
[data-testid="stMain"] span,
[data-testid="stMain"] div,
[data-testid="stMain"] li {
  color: inherit;
}
[data-testid="stMain"] [data-testid="stMarkdownContainer"],
[data-testid="stMain"] [data-testid="stMarkdownContainer"] *,
[data-testid="stMain"] [data-testid="stText"],
[data-testid="stMain"] [data-testid="stText"] *,
[data-testid="stMain"] [data-testid="stCaptionContainer"],
[data-testid="stMain"] [data-testid="stCaptionContainer"] * {
  color: var(--text-color) !important;
}
[data-testid="stMain"] [data-testid="stCaptionContainer"] p,
[data-testid="stMain"] [data-testid="stCaptionContainer"] span,
[data-testid="stMain"] .shell-subtitle,
[data-testid="stMain"] .strategy-console-note,
[data-testid="stMain"] .sidebar-section-summary,
[data-testid="stMain"] .cluster-summary,
[data-testid="stMain"] .timeline-countdown-meta,
[data-testid="stMain"] .leo-backtest-status-card__detail {
  color: var(--text-muted) !important;
}
[data-testid="stMain"] [data-baseweb="input"],
[data-testid="stMain"] [data-baseweb="base-input"],
[data-testid="stMain"] [data-baseweb="select"] > div,
[data-testid="stMain"] [data-testid="stDateInputField"],
[data-testid="stMain"] .stDateInput > div > div,
[data-testid="stMain"] .stNumberInput > div > div {
  background:
    radial-gradient(circle at top right, rgba(31,106,83,0.10), transparent 42%),
    linear-gradient(145deg, var(--panel-fill-a), var(--panel-warm)) !important;
  border: 1px solid rgba(31,106,83,0.26) !important;
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.10),
    0 0 0 1px rgba(174,143,84,0.12),
    0 0 12px rgba(31,106,83,0.08) !important;
  border-radius: 0 !important;
}
[data-testid="stMain"] [data-baseweb="input"] input,
[data-testid="stMain"] [data-baseweb="base-input"] input,
[data-testid="stMain"] [data-testid="stDateInputField"] input,
[data-testid="stMain"] .stDateInput input,
[data-testid="stMain"] .stNumberInput input,
[data-testid="stMain"] [data-baseweb="select"] input,
[data-testid="stMain"] [data-baseweb="select"] span {
  color: var(--text-color) !important;
  background: transparent !important;
}
[data-testid="stMain"] [data-baseweb="input"]:focus-within,
[data-testid="stMain"] [data-baseweb="base-input"]:focus-within,
[data-testid="stMain"] [data-baseweb="select"] > div:focus-within,
[data-testid="stMain"] [data-testid="stDateInputField"]:focus-within,
[data-testid="stMain"] .stDateInput > div > div:focus-within,
[data-testid="stMain"] .stNumberInput > div > div:focus-within {
  border-color: rgba(63, 138, 112, 0.50) !important;
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.10),
    0 0 0 1px rgba(174,143,84,0.18),
    0 0 16px rgba(31,106,83,0.12) !important;
}
[data-testid="stMain"] [role="switch"] {
  background: linear-gradient(90deg, rgba(23,87,68,0.22), rgba(63,138,112,0.14)) !important;
  border: 1px solid rgba(31,106,83,0.34) !important;
  border-radius: 999px !important;
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.08),
    0 0 0 1px rgba(174,143,84,0.10),
    0 0 12px rgba(31,106,83,0.10) !important;
}
[data-testid="stMain"] [role="switch"][aria-checked="true"] {
  background: linear-gradient(90deg, rgba(23,87,68,0.34), rgba(63,138,112,0.28)) !important;
  border-color: rgba(31,106,83,0.44) !important;
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.08),
    0 0 0 1px rgba(174,143,84,0.12),
    0 0 18px rgba(31,106,83,0.18) !important;
}
[data-testid="stMain"] [role="switch"] > div {
  background:
    radial-gradient(circle at 32% 28%, rgba(255,255,255,0.22) 0, rgba(255,255,255,0.10) 24%, transparent 46%),
    linear-gradient(145deg, rgba(31,106,83,0.92), rgba(63,138,112,0.90) 70%, rgba(174,143,84,0.34) 100%) !important;
  border: 1px solid rgba(174,143,84,0.26) !important;
  box-shadow:
    0 1px 3px rgba(17,18,20,0.18),
    inset 0 1px 0 rgba(255,255,255,0.20) !important;
}
[data-testid="stMain"] button[kind="primary"],
[data-testid="stMain"] [data-testid="baseButton-primary"] {
  background:
    radial-gradient(circle at 24% 28%, rgba(255,255,255,0.10) 0, transparent 28%),
    linear-gradient(145deg, rgba(122,31,28,0.98), rgba(92,22,21,0.99)) !important;
  border: 1px solid rgba(174,143,84,0.24) !important;
  color: rgba(244,240,232,0.96) !important;
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.06),
    0 0 0 1px rgba(174,143,84,0.10),
    0 0 16px rgba(122,31,28,0.16) !important;
}
[data-testid="stMain"] [data-testid="stDownloadButton"] button {
  background:
    radial-gradient(circle at top right, rgba(74,110,150,0.10), transparent 40%),
    linear-gradient(145deg, rgba(18,57,91,0.94), rgba(28,67,102,0.96)) !important;
  border: 1px solid rgba(74,110,150,0.30) !important;
  color: rgba(244,240,232,0.96) !important;
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.06),
    0 0 0 1px rgba(174,143,84,0.10),
    0 0 16px rgba(18,57,91,0.16) !important;
  min-height: 3rem !important;
}
[data-testid="stMain"] .stButton > button:not([kind="primary"]) {
  background:
    radial-gradient(circle at top right, rgba(31,106,83,0.16), transparent 40%),
    linear-gradient(145deg, rgba(31,106,83,0.22), rgba(31,106,83,0.10)) !important;
  border: 1px solid rgba(31,106,83,0.30) !important;
  color: rgba(244,240,232,0.96) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.08), 0 0 16px rgba(31,106,83,0.12) !important;
}
/* ── Backtest status + comparison cards ────────────────── */
.leo-backtest-status-card {
  min-height: 6.1rem;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0.8rem 0.85rem;
  border: 2px solid rgba(74,110,150,0.28);
  background:
    radial-gradient(circle at top right, rgba(74,110,150,0.10), transparent 42%),
    linear-gradient(145deg, rgba(18,57,91,0.25), var(--panel-warm));
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.08), 0 0 16px rgba(18,57,91,0.12);
}
.leo-backtest-status-card__title {
  font-size: 0.82rem;
  font-weight: 700;
  color: rgba(156,200,255,0.96);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.leo-backtest-status-card__detail {
  margin-top: 0.28rem;
  font-size: 0.73rem;
  line-height: 1.45;
  color: var(--text-muted);
}
.leo-backtest-metric {
  min-height: 8.95rem;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 0.8rem 0.85rem;
  border: 2px solid var(--leo-surface-rim);
  background: linear-gradient(145deg, var(--panel-fill-a), var(--panel-warm));
  box-shadow: inset 0 1px 0 var(--leo-surface-top), inset 0 -1px 0 var(--leo-surface-bot), 0 0 12px var(--leo-metal-glow);
}
.leo-backtest-metric--positive {
  border-color: rgba(31,106,83,0.36);
  background:
    radial-gradient(circle at top right, rgba(31,106,83,0.10), transparent 44%),
    linear-gradient(145deg, var(--panel-fill-a), var(--panel-warm));
  box-shadow: inset 0 1px 0 var(--leo-surface-top), inset 0 -1px 0 var(--leo-surface-bot), 0 0 18px rgba(31,106,83,0.18);
}
.leo-backtest-metric--negative {
  border-color: rgba(158,47,47,0.34);
  background:
    radial-gradient(circle at top right, rgba(158,47,47,0.10), transparent 44%),
    linear-gradient(145deg, var(--panel-fill-a), var(--panel-warm));
  box-shadow: inset 0 1px 0 var(--leo-surface-top), inset 0 -1px 0 var(--leo-surface-bot), 0 0 18px rgba(158,47,47,0.14);
}
.leo-backtest-metric__label {
  min-height: 3.2rem;
  display: block;
  font-size: 0.68rem;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--text-muted);
}
.leo-backtest-metric__label::before {
  content: '▪';
  font-size: 0.52rem;
  color: rgba(174,143,84,0.80);
  margin-right: 0.28rem;
  vertical-align: middle;
}
.leo-backtest-metric__value {
  margin-top: auto;
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--text-color);
}
/* ── Metric card — pearl plate ─────────────────────────── */
[data-testid="stMetric"] {
  min-height: 8.4rem;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  background:  linear-gradient(
                 145deg,
                 var(--panel-fill-a) 0%,
                 var(--panel-fill-b) 55%,
                 rgba(174, 143, 84,  0.025) 100%
               );
  border:      2px solid var(--leo-surface-rim);
  clip-path:   polygon(0.45rem 0, calc(100% - 0.45rem) 0, 100% 0.45rem,
               100% calc(100% - 0.45rem), calc(100% - 0.45rem) 100%,
               0.45rem 100%, 0 calc(100% - 0.45rem), 0 0.45rem);
  padding:     0.7rem 0.85rem 0.65rem;
  box-shadow:  inset 0 1px 0 var(--leo-surface-top),
               inset 1px 0 0 rgba(255,255,255,0.09),
               inset 0 -1px 0 var(--leo-surface-bot),
               0 1px 3px rgba(26,29,31,0.07),
               0 0 14px var(--leo-metal-glow);
  backdrop-filter: blur(8px);
}
/* ── Metric text — light mode (default) ────────────────── */
[data-testid="stMetricLabel"] > div {
  font-size:      0.64rem !important;
  letter-spacing: 0.10em !important;
  text-transform: uppercase !important;
  color:          var(--text-muted) !important;
}
[data-testid="stMetricLabel"] * {
  color: inherit !important;
}
[data-testid="stMetricLabel"] > div::before {
  content:        '▪';
  font-size:      0.52rem;
  color:          rgba(174, 143, 84, 0.80);
  margin-right:   0.28rem;
  vertical-align: middle;
}
[data-testid="stMetricValue"] > div {
  font-size:            1.45rem !important;
  font-weight:          700 !important;
  color:                var(--text-color) !important;
  font-variant-numeric: tabular-nums;
  min-height:           2.3rem !important;
}
[data-testid="stMetricValue"] *,
[data-testid="stMetricDelta"] *,
[data-testid="stMetric"] label,
[data-testid="stMetric"] p,
[data-testid="stMetric"] span,
[data-testid="stMetric"] div {
  color: inherit !important;
}
/* ── Metric card + text — dark mode ────────────────────── */
[data-theme="dark"] [data-testid="stMetric"] {
  background:  linear-gradient(
                 145deg,
                 var(--panel-fill-a) 0%,
                 var(--panel-fill-b) 100%
               );
  border-color: var(--leo-surface-rim);
  box-shadow:  inset 0 1px 0 var(--leo-surface-top),
               inset 0 -1px 0 var(--leo-surface-bot),
               0 1px 3px rgba(0,0,0,0.28);
}
[data-testid="stMetricDelta"],
[data-testid="stMetricDelta"] * {
  color: var(--text-muted) !important;
}
/* ── Daily state metric with right badge ───────────────── */
.leo-sidebadge-metric {
  min-height: 8.4rem;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 0.7rem 0.85rem 0.65rem;
  background: linear-gradient(
    145deg,
    var(--panel-fill-a) 0%,
    var(--panel-fill-b) 55%,
    rgba(174, 143, 84, 0.025) 100%
  );
  border: 2px solid var(--leo-surface-rim);
  box-shadow:
    inset 0 1px 0 var(--leo-surface-top),
    inset 1px 0 0 rgba(255,255,255,0.09),
    inset 0 -1px 0 var(--leo-surface-bot),
    0 1px 3px rgba(26,29,31,0.07),
    0 0 14px var(--leo-metal-glow);
  backdrop-filter: blur(8px);
}
.leo-sidebadge-metric__label {
  font-size: 0.64rem;
  letter-spacing: 0.10em;
  text-transform: uppercase;
  color: var(--text-muted);
}
.leo-sidebadge-metric__label::before {
  content: '▪';
  font-size: 0.52rem;
  color: rgba(174, 143, 84, 0.80);
  margin-right: 0.28rem;
  vertical-align: middle;
}
.leo-sidebadge-metric__row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.8rem;
  margin-top: 0.55rem;
  min-height: 3.15rem;
}
.leo-sidebadge-metric__value {
  flex: 1;
  min-width: 0;
  font-size: 1.28rem;
  font-weight: 700;
  color: var(--text-color);
  line-height: 1.05;
}
.leo-sidebadge-metric__badge {
  flex-shrink: 0;
  padding: 0.28rem 0.62rem;
  border: 1px solid rgba(31, 106, 83, 0.22);
  background: rgba(31, 106, 83, 0.18);
  color: rgba(134, 233, 161, 0.95);
  font-size: 0.76rem;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
}
.leo-sidebadge-metric--red .leo-sidebadge-metric__badge {
  border-color: rgba(158, 47, 47, 0.24);
  background: rgba(158, 47, 47, 0.18);
  color: rgba(255, 215, 215, 0.96);
}
/* ── Expander ──────────────────────────────────────────── */
[data-testid="stExpander"] {
  border:        2px solid var(--leo-surface-rim) !important;
  border-radius: 0 !important;
  clip-path:     polygon(0.45rem 0, calc(100% - 0.45rem) 0, 100% 0.45rem,
                 100% calc(100% - 0.45rem), calc(100% - 0.45rem) 100%,
                 0.45rem 100%, 0 calc(100% - 0.45rem), 0 0.45rem);
  background:    linear-gradient(145deg, var(--panel-fill-a), var(--panel-fill-b));
  box-shadow:    inset 0 1px 0 var(--leo-surface-top), inset 0 -1px 0 var(--leo-surface-bot), 0 0 12px var(--leo-metal-glow);
  backdrop-filter: blur(8px);
}
[data-testid="stExpander"] summary {
  font-size:      0.72rem !important;
  font-weight:    600 !important;
  letter-spacing: 0.08em !important;
  color:          var(--text-muted) !important;
}
/* ── Chart container ───────────────────────────────────── */
[data-testid="stVegaLiteChart"],
[data-testid="element-container"] > iframe {
  border:        2px solid var(--leo-surface-rim) !important;
  border-radius: 0 !important;
  clip-path:     polygon(0.45rem 0, calc(100% - 0.45rem) 0, 100% 0.45rem,
                 100% calc(100% - 0.45rem), calc(100% - 0.45rem) 100%,
                 0.45rem 100%, 0 calc(100% - 0.45rem), 0 0.45rem);
  background:    linear-gradient(145deg, var(--panel-fill-a), var(--panel-fill-b));
  box-shadow:    inset 0 1px 0 var(--leo-surface-top), 0 0 12px var(--leo-metal-glow);
  backdrop-filter: blur(8px);
}
/* ── Responsive metric grid ────────────────────────────── */
/* Desktop (> 1024px): up to 6 per row — Python layout controls column count */
/* Tablet (≤ 1024px): wrap to 4 per row */
@media (max-width: 1024px) {
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    min-width: 23% !important;
    flex: 1 1 23% !important;
  }
}
/* Mobile (≤ 480px): 2 per row, full-bleed padding */
@media (max-width: 640px) {
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    min-width: 48% !important;
    flex: 1 1 48% !important;
  }
  [data-testid="stMetric"] {
    padding: 0.45rem 0.5rem 0.4rem;
  }
  [data-testid="stMetricLabel"] > div {
    font-size: 0.65rem !important;
  }
  [data-testid="stMetricValue"] > div {
    font-size: 1.05rem !important;
  }
}
@media (max-width: 360px) {
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    min-width: 100% !important;
    flex: 1 1 100% !important;
  }
}
/* ── Premium slider ────────────────────────────────────── */
[data-baseweb="slider"] {
  padding: 0.72rem 0 0.58rem !important;
}
[data-testid="stSidebar"] [data-baseweb="slider"] > div:first-child > div {
  height: 6px !important;
  background: linear-gradient(90deg, rgba(31,106,83,0.14), rgba(31,106,83,0.06)) !important;
  border: 1px solid rgba(174, 143, 84, 0.14) !important;
  border-radius: 999px !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.10) !important;
}
[data-testid="stSidebar"] [data-baseweb="slider"] > div:first-child > div > div {
  background: linear-gradient(90deg, rgba(31,106,83,0.76), var(--leo-racing-green)) !important;
  border-radius: 999px !important;
  box-shadow: 0 0 0 1px rgba(255,255,255,0.05), 0 1px 4px rgba(31,106,83,0.18) !important;
}
[data-baseweb="slider"] [data-testid="stThumbValue"] {
  font-size:   0.64rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.06em !important;
  color:       var(--leo-racing-green) !important;
  text-transform: uppercase !important;
}
[data-testid="stSidebar"] [role="slider"] {
  width:   16px !important;
  height:  16px !important;
  background:
    radial-gradient(circle at 32% 28%, rgba(255,255,255,0.28) 0, rgba(255,255,255,0.10) 24%, transparent 45%),
    linear-gradient(145deg, rgba(31,106,83,0.94) 0%, rgba(46,132,105,0.88) 58%, rgba(174,143,84,0.44) 100%) !important;
  border:     1px solid rgba(174, 143, 84, 0.42) !important;
  border-radius: 0 !important;
  clip-path: polygon(
    2px 0, calc(100% - 2px) 0, 100% 2px, 100% calc(100% - 2px),
    calc(100% - 2px) 100%, 2px 100%, 0 calc(100% - 2px), 0 2px
  ) !important;
  box-shadow:
    0 2px 5px rgba(26,29,31,0.24),
    inset 0 1px 0 rgba(255,255,255,0.18) !important;
  transition: box-shadow 130ms ease, border-color 130ms ease !important;
  cursor: grab !important;
  touch-action: none !important;
}
[data-testid="stSidebar"] [role="slider"]:hover,
[data-testid="stSidebar"] [role="slider"]:focus {
  box-shadow:
    0 3px 8px rgba(31,106,83,0.20),
    inset 0 1px 0 rgba(255,255,255,0.18) !important;
  outline: none !important;
  border-color: rgba(31, 106, 83, 0.42) !important;
}
[data-testid="stSidebar"] [role="slider"]:active {
  cursor: grabbing !important;
  box-shadow:
    0 0 18px rgba(31,106,83,0.24),
    0 0 28px rgba(255,255,255,0.06),
    inset 0 1px 0 rgba(255,255,255,0.18) !important;
}
[data-theme="dark"] [data-testid="stSidebar"] [role="slider"] {
  background: linear-gradient(145deg, rgba(244,240,232,0.18) 0%, rgba(26,29,31,0.55) 100%) !important;
  border-color: rgba(174, 143, 84, 0.40) !important;
  box-shadow:
    0 1px 3px rgba(0,0,0,0.50),
    inset 0 1px 0 rgba(255,255,255,0.06) !important;
}
/* ── Final hard edge reset: keep all non-pill surfaces rectangular ───── */
div[data-testid="stSegmentedControl"] > div,
div[data-testid="stSegmentedControl"] button,
.strategy-console-intro,
.strategy-console-chip,
.sidebar-section-plate,
.sidebar-control-cluster,
.sidebar-control-cluster .cluster-chip,
[data-testid="stMetric"],
[data-testid="stExpander"],
[data-testid="stVegaLiteChart"],
[data-testid="element-container"] > iframe,
[data-testid="stSidebar"] [data-baseweb="input"],
[data-testid="stSidebar"] [data-baseweb="base-input"],
[data-testid="stSidebar"] [data-baseweb="radio"] label,
[data-testid="stSidebar"] [role="switch"],
[data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button,
[data-testid="stSidebar"] [data-baseweb="slider"] > div:first-child > div,
[data-testid="stSidebar"] [data-baseweb="slider"] > div:first-child > div > div,
[data-testid="stSidebar"] [role="slider"],
.trade-timeline-wrap,
.trade-timeline-track,
.trade-timeline-segment,
.trade-deadline-warning,
.trade-action-item,
.timeline-countdown-card,
.timeline-legend-item span {
  border-radius: 0 !important;
  clip-path: none !important;
}
</style>
""",
        unsafe_allow_html=True,
    )

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
    _apply_session_preferences(working_settings)
    working_settings = _settings_sidebar(working_settings, config_path)
    language = _ui_language(working_settings)
    resolved_theme = _ui_theme(working_settings)
    _render_theme_override(resolved_theme)
    try:
        alt.themes.enable("dark" if resolved_theme == "dark" else "default")
    except Exception:
        pass
    language = _render_shell_header(working_settings, language)
    # _inject_world_map_bg(working_settings)  # disabled: background world map turned off

    render_app_shell(
        settings=working_settings,
        language=language,
        config_path=config_path,
        daily_renderer=_daily_tab,
        market_health_renderer=_market_health_tab,
        backtest_renderer=_backtest_tab,
        settings_renderer=_settings_tab,
    )


def _render_theme_override(theme: str) -> None:
    if theme == "dark":
        text_color = "rgba(244, 240, 232, 0.92)"
        text_muted = "rgba(244, 240, 232, 0.60)"
        kicker = "rgba(244, 240, 232, 0.86)"
        panel_warm = "rgba(174, 143, 84, 0.10)"
        panel_fill_a = "rgba(26, 29, 31, 0.74)"
        panel_fill_b = "rgba(0, 0, 0, 0.22)"
        surface_a = "rgba(26, 29, 31, 0.25)"
        surface_b = "rgba(244, 240, 232, 0.06)"
        surface_chip = "rgba(244, 240, 232, 0.08)"
        surface_rim = "rgba(174, 143, 84, 0.18)"
        surface_top = "rgba(255, 255, 255, 0.05)"
        surface_bot = "rgba(174, 143, 84, 0.05)"
        metal_glow = "rgba(174, 143, 84, 0.10)"
    else:
        text_color = "#0A0C0D"
        text_muted = "rgba(10, 12, 13, 0.82)"
        kicker = "rgb(18, 57, 91)"
        panel_warm = "rgba(174, 143, 84, 0.25)"
        panel_fill_a = "rgba(244, 240, 232, 0.25)"
        panel_fill_b = "rgba(255, 255, 255, 0.10)"
        surface_a = "rgba(244, 240, 232, 0.25)"
        surface_b = "rgba(255, 255, 255, 0.10)"
        surface_chip = "rgba(255, 255, 255, 0.14)"
        surface_rim = "rgba(174, 143, 84, 0.22)"
        surface_top = "rgba(255, 255, 255, 0.17)"
        surface_bot = "rgba(174, 143, 84, 0.06)"
        metal_glow = "rgba(174, 143, 84, 0.12)"

    st.markdown(
        f"""
<style>
:root,
html,
body,
.stApp,
[data-testid="stAppViewContainer"] {{
  --leo-ink: {text_color};
  --leo-ink-sub: {text_muted};
  --leo-kicker: {kicker};
  --text-color: {text_color};
  --text-muted: {text_muted};
  --panel-warm: {panel_warm};
  --panel-fill-a: {panel_fill_a};
  --panel-fill-b: {panel_fill_b};
  --leo-surface-a: {surface_a};
  --leo-surface-b: {surface_b};
  --leo-surface-chip: {surface_chip};
  --leo-surface-rim: {surface_rim};
  --leo-surface-top: {surface_top};
  --leo-surface-bot: {surface_bot};
  --leo-metal-glow: {metal_glow};
}}
body,
[data-testid="stSidebar"] {{
  background-color: {"#1A1D1F" if theme == "dark" else "#F5F1EB"} !important;
  color: {text_color} !important;
}}
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stMainBlockContainer"] {{
  background-color: transparent !important;
  color: {text_color} !important;
}}
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stMainBlockContainer"] {{
  position: relative !important;
  z-index: 1 !important;
}}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
[data-testid="stSidebar"] [data-baseweb="radio"] label p,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
[data-testid="stSidebar"] [data-baseweb="slider"] [data-testid="stThumbValue"] {{
  color: {"rgba(244, 240, 232, 0.92)" if theme == "dark" else "var(--leo-racing-green)"} !important;
}}
[data-testid="stHeading"] h3 {{
  color: var(--leo-kicker) !important;
}}
[data-testid="stMetric"] {{
  background: linear-gradient(145deg, var(--panel-fill-a) 0%, var(--panel-fill-b) 55%, rgba(174, 143, 84, 0.025) 100%) !important;
}}
[data-testid="stSidebar"] [role="slider"] {{
  background: {"linear-gradient(145deg, rgba(244,240,232,0.18) 0%, rgba(26,29,31,0.55) 100%)" if theme == "dark" else "linear-gradient(145deg, rgba(244,240,232,0.86), rgba(217,208,188,0.74))"} !important;
  border-color: {"rgba(174, 143, 84, 0.40)" if theme == "dark" else "rgba(174, 143, 84, 0.24)"} !important;
}}
[data-testid="stHorizontalBlock"]:has([class*="st-key-app_shell_nav"]) [data-testid="stButton"] > button {{
  background: {"rgba(255, 255, 255, 0.05)" if theme == "dark" else "rgba(244, 240, 232, 0.10)"} !important;
  color: var(--text-color) !important;
  border-color: {"rgba(174, 143, 84, 0.22)" if theme == "dark" else "rgba(174, 143, 84, 0.30)"} !important;
}}
[data-testid="stHorizontalBlock"]:has([class*="st-key-app_shell_nav"]) [data-testid="stButton"] > button:hover {{
  background: {"rgba(18, 57, 91, 0.18)" if theme == "dark" else "rgba(18, 57, 91, 0.07)"} !important;
  color: var(--text-color) !important;
}}
[data-testid="stHorizontalBlock"]:has([class*="st-key-app_shell_nav"]) [data-testid="stButton"] > button[kind="primary"] {{
  background: {"linear-gradient(135deg, rgba(18, 57, 91, 0.28), rgba(18, 57, 91, 0.44))" if theme == "dark" else "linear-gradient(135deg, rgba(18, 57, 91, 0.14), rgba(18, 57, 91, 0.26))"} !important;
  color: var(--text-color) !important;
}}
</style>
""",
        unsafe_allow_html=True,
    )
    _inject_theme_attribute(theme)


def _inject_theme_attribute(theme: str) -> None:
    """Set data-theme on <html> and <body> so [data-theme="dark"] CSS selectors match.

    Without this, the hundreds of [data-theme="dark"] rules in the stylesheet
    never activate, and chart/metric text falls back to Streamlit defaults
    (often black, invisible in dark mode).
    """
    safe_theme = "dark" if theme == "dark" else "light"
    text_color = "rgba(244, 240, 232, 0.92)" if safe_theme == "dark" else "#111214"
    st.markdown(
        f"""
<script>
(function() {{
  const theme = "{safe_theme}";
  try {{
    document.documentElement.setAttribute("data-theme", theme);
    document.body.setAttribute("data-theme", theme);
    const root = window.parent && window.parent.document;
    if (root) {{
      root.documentElement.setAttribute("data-theme", theme);
      if (root.body) root.body.setAttribute("data-theme", theme);
    }}
  }} catch (e) {{}}
}})();
</script>
<style>
[data-theme="dark"] [data-testid="stVegaLiteChart"] text,
[data-theme="dark"] [data-testid="stVegaLiteChart"] tspan,
[data-theme="dark"] [data-testid="stPlotlyChart"] text,
[data-theme="dark"] [data-testid="stPlotlyChart"] tspan,
[data-theme="dark"] [data-testid="stDataFrame"] *,
[data-theme="dark"] [data-testid="stTable"] *,
[data-theme="dark"] svg text,
[data-theme="dark"] svg tspan,
[data-theme="dark"] .recharts-text,
[data-theme="dark"] .vega-tooltip {{
  fill: {text_color} !important;
  color: {text_color} !important;
}}
</style>
""",
        unsafe_allow_html=True,
    )


def _inject_world_map_bg(settings: dict[str, Any]) -> None:
    theme = _ui_theme(settings)
    if theme == "dark":
        page_bg = "#1A1D1F"
        map_color = "rgba(244, 240, 232, 0.0425)"
    else:
        page_bg = "#F5F1EB"
        map_color = "rgba(17, 18, 20, 0.0275)"

    world_map_html = build_world_map_text(repeats=2)
    st.markdown(
        f"""
<style>
html,
body {{
  background: var(--leo-page-bg, {page_bg}) !important;
}}
.leo-world-map-bg {{
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  user-select: none;
  overflow: hidden;
}}
.leo-world-map-pre {{
  margin: 0;
  padding: 72px 0 0;
  font-family: "Courier New", Courier, monospace;
  font-size: 6.5px;
  line-height: 0.45;
  white-space: pre;
  color: {map_color} !important;
  width: 100%;
}}
[data-testid="stMarkdownContainer"] .leo-world-map-pre {{
  color: {map_color} !important;
}}
@media (max-width: 640px) {{
  .leo-world-map-pre {{
    width: max-content;
    animation: leo-map-scroll 80s linear infinite;
  }}
}}
@keyframes leo-map-scroll {{
  from {{ transform: translateX(0); }}
  to {{ transform: translateX(-50%); }}
}}
@media (prefers-reduced-motion: reduce) {{
  .leo-world-map-pre {{
    animation: none !important;
  }}
}}
</style>
<div class="leo-world-map-bg" aria-hidden="true">
  <div class="leo-world-map-pre">{html.escape(world_map_html)}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_shell_header(settings: dict[str, Any], language: str) -> str:
    theme = _ui_theme(settings)
    title_cols = st.columns([5, 1.0, 1.15])
    title_cols[0].markdown(
        f"""
<div class="shell-title-band">
  <div class="shell-kicker">LEOLRS0-3</div>
  <div class="shell-title">LEOLRS0-3</div>
  <div class="shell-subtitle">{html.escape(_tr(language, "新西兰时区默认 · 日线级别 · 风险控制优先", "New Zealand time zone defaults · Daily signals · Risk control first"))}</div>
</div>
""",
        unsafe_allow_html=True,
    )
    selected_theme_label = title_cols[1].segmented_control(
        _tr(language, "界面主题", "Interface theme"),
        ["Dark", "Light"],
        default="Dark" if theme == "dark" else "Light",
        key="header_ui_theme",
        label_visibility="collapsed",
        width="content",
    )
    selected_theme = "dark" if selected_theme_label == "Dark" else "light"
    current = "EN" if language == "en" else "中文"
    selected = title_cols[2].segmented_control(
        _tr(language, "界面语言", "Interface language"),
        ["EN", "中文"],
        default=current,
        key="header_ui_language",
        label_visibility="collapsed",
        width="content",
    )
    resolved = "en" if selected == "EN" else "zh"
    if resolved != language:
        st.session_state["ui_language"] = resolved
        settings.setdefault("ui", {})["language"] = resolved
        st.rerun()
    if selected_theme != theme:
        st.session_state["ui_theme"] = selected_theme
        settings.setdefault("ui", {})["theme"] = selected_theme
        st.rerun()
    return resolved


def _sidebar_section_plate(language: str, overline: str, title: str, summary: str) -> None:
    st.markdown(
        f"""
<div class="sidebar-section-plate">
  <div class="sidebar-section-overline">{html.escape(overline)}</div>
  <div class="sidebar-section-title">{html.escape(title)}</div>
  <div class="sidebar-section-summary">{html.escape(summary)}</div>
</div>
""",
        unsafe_allow_html=True,
    )


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
    chip_markup = "".join(f'<span class="strategy-console-chip">{html.escape(chip)}</span>' for chip in chips)
    st.markdown(
        f"""
<div class="strategy-console-intro">
  <div class="strategy-console-title">{html.escape(_tr(language, "策略控制台", "Strategy Console"))}</div>
  <div class="strategy-console-note">{html.escape(_tr(language, "先看控制台，再深入每一组参数。这个面板开始按决策意图，而不是按原始配置文件来理解。", "Scan the control deck first, then dive into each parameter group. This panel now starts to read by decision intent, not by raw config order."))}</div>
  <div class="strategy-console-grid">{chip_markup}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def _sidebar_control_cluster(
    language: str,
    overline: str,
    title: str,
    summary: str,
    chips: list[str] | None = None,
    tone: str = "prussian",
) -> None:
    tone_class = {
        "prussian": "",
        "green": " cluster-green",
        "red": " cluster-red",
    }.get(tone, "")
    chip_markup = ""
    if chips:
        chip_markup = '<div class="cluster-chip-row">' + "".join(
            f'<span class="cluster-chip">{html.escape(chip)}</span>' for chip in chips
        ) + "</div>"
    st.markdown(
        f"""
<div class="sidebar-control-cluster{tone_class}">
  <div class="cluster-overline">{html.escape(overline)}</div>
  <div class="cluster-title">{html.escape(title)}</div>
  <div class="cluster-summary">{html.escape(summary)}</div>
  {chip_markup}
</div>
""",
        unsafe_allow_html=True,
    )


def _settings_sidebar(settings: dict[str, Any], config_path: str) -> dict[str, Any]:
    key_prefix = _widget_key_prefix(config_path)
    with st.sidebar.form("settings_form"):
        language = _ui_language(settings)
        st.header(_tr(language, "策略参数", "Strategy Parameters"))
        _render_sidebar_console_intro(settings, language)

        execution = settings["execution"]
        _sidebar_section_plate(
            language,
            _tr(language, "第一组", "Group One"),
            _tr(language, "Session & Market Context", "Session & Market Context"),
            _tr(language, "先定义执行市场、本地与海外资产边界，再让后续信号有明确的执行语境。", "Define market selection and account asset boundaries first so every later signal has a clear execution context."),
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
        st.caption(_tr(language, "打开后，VOO、SPXL 等非 NZX/ASX 标的目标市值合计折算后不超过这个纽币金额。IVV.AX、USF.NZ 不计入此限制。", "When enabled, non-NZX/ASX targets such as VOO and SPXL are capped at this NZD value. IVV.AX and USF.NZ are excluded."))
        st.caption(_tr(language, "备注：这是基于新西兰 FIF 50,000 NZD 门槛的辅助监控。部分 ASX 标的是否豁免需以 IRD 规则和实际标的为准。", "Note: this is a helper for New Zealand's 50,000 NZD FIF threshold. Confirm actual treatment with IRD rules and the fund details."))

        trend = settings["trend"]
        position = settings["position"]

        # ── 复合模块 ─────────────────────────────────────────────────────────
        st.divider()
        _sidebar_section_plate(
            language,
            _tr(language, "第二组", "Group Two"),
            _tr(language, "Signal Construction", "Signal Construction"),
            _tr(language, "先定义趋势感应器与简单门控，再决定后面的主仓位引擎如何解释它们。", "Define the trend sensors and simple gate first, then let the main position engine interpret them."),
        )
        st.subheader(_tr(language, "趋势信号", "Trend Signal"))
        trend["short_window"] = st.number_input(_tr(language, "短期均线", "Short moving average"), 5, 100, int(trend["short_window"]))
        st.caption(_tr(language, "反映短期动能。数值越小越敏感，越容易提前加仓或减仓。", "Tracks short-term momentum. Smaller values react faster."))
        trend["medium_window"] = st.number_input(_tr(language, "中期均线", "Medium moving average"), 10, 150, int(trend["medium_window"]))
        st.caption(_tr(language, "反映中期趋势。数值越大越稳，但信号会更慢。", "Tracks medium-term trend. Larger values are steadier but slower."))
        trend["long_window"] = st.number_input(_tr(language, "长期均线", "Long moving average"), 50, 300, int(trend["long_window"]))
        st.caption(_tr(language, "判断牛熊环境的主过滤器。越长越保守，越短越容易频繁切换。", "Main bull/bear environment filter. Longer is more conservative."))
        trend["confirmation_days"] = st.number_input(_tr(language, "连续确认天数", "Confirmation days"), 1, 10, int(trend["confirmation_days"]))
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
        position["simple_module_off_exposure"] = st.slider(
            _tr(language, "条件不满足时的目标仓位 (%)", "Off-state target exposure (%)"),
            0.0,
            300.0,
            min(float(position.get("simple_module_off_exposure", 0.0)), 300.0),
            5.0,
            help=_tr(
                language,
                "简单模块条件不满足时（价格未超过均线阈值）使用的目标仓位。",
                "Target exposure when simple module conditions are not met (price not above MA threshold).",
            ),
            key=f"{key_prefix}_simple_module_off_exposure",
        )
        if _simple_on and not _composite_on:
            position["simple_module_on_exposure"] = st.slider(
                _tr(language, "条件满足时的目标仓位 (%)", "On-state target exposure (%)"),
                0.0,
                300.0,
                min(float(position.get("simple_module_on_exposure", 300.0)), 300.0),
                5.0,
                help=_tr(language, "仅简单模块模式：触发条件时的目标仓位。默认 300%。", "Simple-only mode: target exposure when conditions are met. Default is 300%."),
                key=f"{key_prefix}_simple_module_on_exposure",
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
        _sidebar_section_plate(
            language,
            _tr(language, "第三组", "Group Three"),
            _tr(language, "Core Position Engine", "Core Position Engine"),
            _tr(language, "这里决定基础仓位边界、复合引擎与 VIX 系数如何形成主要仓位姿态。", "This group shapes the base exposure range, composite engine, and VIX tiers that form the main posture."),
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
        _sidebar_control_cluster(
            language,
            _tr(language, "主控制节点", "Primary Control Cluster"),
            _tr(language, "仓位地板 / 顶盖 / 调仓阈值", "Exposure floor / cap / rebalance threshold"),
            _tr(
                language,
                "这一组是策略控制台裡最重要的三根推杆，决定系统愿意压到多低、拉到多高，以及变化多大才值得执行。",
                "This trio is the key control cluster in the strategy console: how low the system can compress, how high it can extend, and how much change is worth executing.",
            ),
            chips=[_tr(language, "Floor", "Floor"), _tr(language, "Cap", "Cap"), _tr(language, "Trigger", "Trigger")],
        )
        position["min_exposure"] = st.slider(
            _tr(language, "最小等效仓位", "Minimum equivalent exposure"),
            0.0,
            300.0,
            min(float(position.get("min_exposure", 0.0)), 300.0),
            5.0,
            help=_tr(
                language,
                "目标等效仓位不会低于这个下限。设为 0% 表示允许完全空仓或只持有防御资产。",
                "Target equivalent exposure will not fall below this floor. Set 0% to allow fully defensive positioning.",
            ),
        )
        st.caption(
            _tr(
                language,
                "这是仓位下限，不是目标仓位。实际目标 = 趋势仓位 × VIX 系数，再受这个下限保护。",
                "This is a floor, not the target. Target = trend exposure x VIX multiplier, floored here.",
            )
        )
        position["max_exposure"] = st.slider(
            _tr(language, "最大等效仓位", "Maximum equivalent exposure"),
            max(50.0, float(position["min_exposure"])),
            300.0,
            max(float(position["min_exposure"]), min(float(position["max_exposure"]), 300.0)),
            5.0,
            help=_tr(language, "300% 约等于 100% 资金买入 3x ETF。120% 约等于 90% 核心资产 + 10% 3x ETF。", "300% is roughly 100% in a 3x ETF. 120% is roughly 90% core plus 10% in a 3x ETF."),
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
        _sidebar_control_cluster(
            language,
            _tr(language, "波动引擎", "Volatility Engine"),
            _tr(language, "VIX 分档与乘数", "VIX thresholds and multipliers"),
            _tr(
                language,
                "这段决定系统在低波动、正常和危险环境之间如何变速，是主仓位引擎后面的第一层节奏控制。",
                "This block controls how the system changes speed across low, normal, and dangerous volatility regimes. It is the first tempo control after the main exposure engine.",
            ),
            chips=[_tr(language, "Low", "Low"), _tr(language, "Normal", "Normal"), _tr(language, "Danger", "Danger"), _tr(language, "Crisis", "Crisis")],
            tone="green",
        )
        for rule in settings["vix"]["rules"]:
            label = rule["label"]
            rule["multiplier"] = st.number_input(
                _tr(language, f"{label} 系数", f"{label} multiplier"),
                0.0,
                5.0,
                float(rule["multiplier"]),
                0.05,
                key=f"{key_prefix}_vix_multiplier_{label}",
            )
            st.caption(_vix_multiplier_note(label, language))

        st.divider()
        _sidebar_section_plate(
            language,
            _tr(language, "第四组", "Group Four"),
            _tr(language, "Leverage & Safety Gate", "Leverage & Safety Gate"),
            _tr(language, "先定义杠杆放行条件，再进入附加安全阀与异常覆盖。", "Define leverage permission before entering the extra safety gates and exception overrides."),
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
        _sidebar_section_plate(
            language,
            _tr(language, "第五组", "Group Five"),
            _tr(language, "Advanced Caps & Exception Modules", "Advanced Caps & Exception Modules"),
            _tr(language, "把回撤、无新高、周期涨幅、趋势质量与极端风险模块视作附加的安全阀门。", "Treat drawdown, no-new-high, period-rise, trend-quality, and extreme-risk modules as additional safety valves."),
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
            _sidebar_control_cluster(
                language,
                _tr(language, "安全阀 A", "Safety Valve A"),
                _tr(language, "VIX 仓位上限曲线", "VIX exposure cap curve"),
                _tr(
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
            _sidebar_control_cluster(
                language,
                _tr(language, "安全阀 B", "Safety Valve B"),
                _tr(language, "回撤仓位上限曲线", "Drawdown exposure cap curve"),
                _tr(
                    language,
                    "这一段处理的是慢性走弱而不是瞬时恐慌，让系统在连续失血阶段更早降低上限。",
                    "This block is for slow deterioration rather than panic spikes, helping the system lower its cap earlier during extended drawdown phases.",
                ),
                chips=[_tr(language, "Lookback", "Lookback"), _tr(language, "Cap ladder", "Cap ladder")],
                tone="red",
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
            parameter_debug_section=_parameter_debug_section,
            trade_summary_rows=_trade_summary_rows,
            equity_columns_for_pdf=equity_columns_for_pdf,
            exposure_columns_for_timing=_exposure_columns_for_timing,
            zoomable_line_chart=_zoomable_line_chart,
            execution_timing_labels=_execution_timing_labels,
            backtest_date_defaults=_backtest_date_defaults,
            fingerprint=_fingerprint,
            is_stale=_is_stale,
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


def _parameter_debug_section(settings: dict[str, Any], start: date, end: date, language: str) -> dict[str, Any] | None:
    with st.expander(_tr(language, "调试模式：参数扫描", "Debug mode: parameter sweep")):
        st.caption(
            _tr(
                language,
                "在当前回测区间内，把核心模型参数按当前值的 50%、75%、100%、125%、150% 测试，并额外围绕目标日期生成时间窗口优化。结果会同时对比当前配置基准线和默认配置基准线。",
                "Within the current backtest range, test core model parameters at 50%, 75%, 100%, 125%, and 150% of their current values, then run an additional target-date window optimization. Results compare against both the current configuration baseline and the default configuration baseline.",
            )
        )
        controls = st.columns([1, 1, 1, 1])
        target_date = controls[0].date_input(
            _tr(language, "目标日期", "Target date"),
            value=end,
            min_value=start,
            max_value=end,
            key="parameter_sweep_target_date",
        )
        months_before = controls[1].number_input(
            _tr(language, "目标日前月数", "Months before"),
            min_value=0,
            max_value=120,
            value=6,
            step=1,
            key="parameter_sweep_months_before",
        )
        months_after = controls[2].number_input(
            _tr(language, "目标日后月数", "Months after"),
            min_value=0,
            max_value=120,
            value=6,
            step=1,
            key="parameter_sweep_months_after",
        )
        sort_options = {
            _tr(language, "策略总收益", "Strategy total return"): "total_return_pct",
            "CAGR": "cagr_pct",
            "Sharpe": "sharpe_no_rf",
            _tr(language, "最大回撤（越高越好）", "Max drawdown, higher is better"): "max_drawdown_pct",
            _tr(language, "年化波动（越低越好）", "Annual volatility, lower is better"): "annual_volatility_pct",
            _tr(language, "调仓次数（越少越好）", "Rebalances, lower is better"): "trades",
        }
        sort_label = controls[3].selectbox(
            _tr(language, "排序目标", "Ranking objective"),
            list(sort_options.keys()),
            key="parameter_sweep_sort_metric",
        )
        sort_metric = sort_options[sort_label]
        run_sweep = st.button(
            _tr(language, "运行 50% 参数扫描", "Run 50% parameter sweep"),
            use_container_width=True,
        )
        if not run_sweep and "parameter_sweep" not in st.session_state:
            return None
        if not run_sweep and not isinstance(st.session_state.get("parameter_sweep"), dict):
            st.session_state.pop("parameter_sweep", None)
            return None

        if run_sweep:
            with st.spinner(_tr(language, "正在扫描参数组合...", "Scanning parameter variants...")):
                primary = settings["signals"]["primary"]
                vix_symbol = settings["signals"]["volatility"]
                price_field = settings["signals"].get("price_field", "Close")
                default_raw = load_settings(DEFAULT_CONFIG).raw
                data_start = min(history_start_date(start, settings), history_start_date(start, default_raw))
                prices = _cached_prices((primary, vix_symbol), str(data_start), _inclusive_end(end), True)
                price = prices[primary][price_field]
                vix = prices[vix_symbol][price_field]
                open_price = prices[primary].get("Open")
                model_settings = _model_settings(settings)
                default_settings = _model_settings(default_raw)
                individual, unified, ranges, recommendations = _cached_parameter_sweep(
                    price,
                    vix,
                    model_settings,
                    open_price=prices[primary].get("Open"),
                    result_start=str(start),
                    baseline_settings=default_settings,
                    sort_metric=sort_metric,
                )
                individual = _with_parameter_ui_names(individual, model_settings, language)
                unified = _with_parameter_ui_names(unified, model_settings, language)
                ranges = _with_parameter_ui_names(ranges, model_settings, language)
                recommendations = _with_parameter_ui_names(recommendations, model_settings, language)
                window_start = max(start, target_date - timedelta(days=int(months_before) * 30))
                window_end = min(end, target_date + timedelta(days=int(months_after) * 30))
                target_price = price.loc[: pd.Timestamp(window_end)]
                target_vix = vix.loc[: pd.Timestamp(window_end)]
                target_open_price = open_price.loc[: pd.Timestamp(window_end)] if open_price is not None else None
                target_individual, target_unified, target_ranges, target_recommendations = _cached_parameter_sweep(
                    target_price,
                    target_vix,
                    model_settings,
                    open_price=target_open_price,
                    result_start=str(window_start),
                    baseline_settings=default_settings,
                    sort_metric=sort_metric,
                )
                target_individual = _with_parameter_ui_names(target_individual, model_settings, language)
                target_unified = _with_parameter_ui_names(target_unified, model_settings, language)
                target_ranges = _with_parameter_ui_names(target_ranges, model_settings, language)
                target_recommendations = _with_parameter_ui_names(target_recommendations, model_settings, language)
                full_curves = _sweep_comparison_curves(
                    price,
                    vix,
                    model_settings,
                    default_settings,
                    individual,
                    unified,
                    open_price=open_price,
                    result_start=str(start),
                )
                target_curves = _sweep_comparison_curves(
                    target_price,
                    target_vix,
                    model_settings,
                    default_settings,
                    target_individual,
                    target_unified,
                    open_price=target_open_price,
                    result_start=str(window_start),
                )
                st.session_state["parameter_sweep"] = {
                    "full": (individual, unified, ranges, recommendations),
                    "target": (target_individual, target_unified, target_ranges, target_recommendations),
                    "target_date": target_date,
                    "window_start": window_start,
                    "window_end": window_end,
                    "sort_label": sort_label,
                    "sort_metric": sort_metric,
                    "full_curves": full_curves,
                    "target_curves": target_curves,
                    "full_factor_curves": _sweep_factor_curves(individual, sort_metric),
                    "target_factor_curves": _sweep_factor_curves(target_individual, sort_metric),
                }

        stored = st.session_state["parameter_sweep"]
        individual, unified, ranges, recommendations = stored["full"]
        target_individual, target_unified, target_ranges, target_recommendations = stored["target"]
        st.markdown(f'<div class="leo-section-head leo-section-head--prussian"><span class="leo-section-dot"></span><span class="leo-section-overline">{_tr(language, "全区间参数调整建议", "Full-Range Parameter Recommendations")}</span><span class="leo-section-rule"></span></div>', unsafe_allow_html=True)
        st.dataframe(_localized_recommendations(recommendations, language), use_container_width=True, hide_index=True)
        st.markdown(f'<div class="leo-section-head leo-section-head--prussian"><span class="leo-section-dot"></span><span class="leo-section-overline">{_tr(language, "最适合的参数范围", "Preferred Parameter Ranges")}</span><span class="leo-section-rule"></span></div>', unsafe_allow_html=True)
        st.dataframe(_localized_parameter_frame(ranges, language), use_container_width=True, hide_index=True)
        st.markdown(f'<div class="leo-section-head leo-section-head--prussian"><span class="leo-section-dot"></span><span class="leo-section-overline">{_tr(language, "逐个测试最佳结果", "Best Individual Tests")}</span><span class="leo-section-rule"></span></div>', unsafe_allow_html=True)
        st.dataframe(_localized_parameter_frame(individual.head(25), language), use_container_width=True, hide_index=True)
        st.markdown(f'<div class="leo-section-head leo-section-head--prussian"><span class="leo-section-dot"></span><span class="leo-section-overline">{_tr(language, "统一测试结果", "Unified Test Results")}</span><span class="leo-section-rule"></span></div>', unsafe_allow_html=True)
        st.dataframe(_localized_parameter_frame(unified, language), use_container_width=True, hide_index=True)
        st.markdown(f'<div class="leo-section-head leo-section-head--prussian"><span class="leo-section-dot"></span><span class="leo-section-overline">{_tr(language, "全区间对比净值曲线", "Full-Range Comparison Equity Curves")}</span><span class="leo-section-rule"></span></div>', unsafe_allow_html=True)
        _zoomable_line_chart(
            stored["full_curves"],
            list(stored["full_curves"].columns),
            _tr(language, "扫描对比净值", "Sweep comparison equity"),
            key="parameter_sweep_full_curves",
            language=language,
        )
        _sweep_metric_line_chart(
            stored["full_factor_curves"],
            _tr(language, "全区间单参数扫描折线", "Full-range individual sweep lines"),
            stored["sort_metric"],
            language,
            key="parameter_sweep_full_factor_lines",
        )
        st.markdown(f'<div class="leo-section-head leo-section-head--green"><span class="leo-section-dot"></span><span class="leo-section-overline">{_tr(language, "目标日期参数建议表", "Target-Date Parameter Recommendations")}</span><span class="leo-section-rule"></span></div>', unsafe_allow_html=True)
        st.caption(
            _tr(
                language,
                f"目标日期：{stored['target_date']}；时间窗口：{stored['window_start']} ~ {stored['window_end']}；排序目标：{stored['sort_label']}",
                f"Target date: {stored['target_date']}; window: {stored['window_start']} to {stored['window_end']}; objective: {stored['sort_label']}",
            )
        )
        st.dataframe(_localized_recommendations(target_recommendations, language), use_container_width=True, hide_index=True)
        st.markdown(f'<div class="leo-section-head leo-section-head--green"><span class="leo-section-dot"></span><span class="leo-section-overline">{_tr(language, "目标日期窗口最适合的参数范围", "Target Window Preferred Parameter Ranges")}</span><span class="leo-section-rule"></span></div>', unsafe_allow_html=True)
        st.dataframe(_localized_parameter_frame(target_ranges, language), use_container_width=True, hide_index=True)
        st.markdown(f'<div class="leo-section-head leo-section-head--green"><span class="leo-section-dot"></span><span class="leo-section-overline">{_tr(language, "目标日期窗口对比净值曲线", "Target Window Comparison Equity Curves")}</span><span class="leo-section-rule"></span></div>', unsafe_allow_html=True)
        _zoomable_line_chart(
            stored["target_curves"],
            list(stored["target_curves"].columns),
            _tr(language, "目标窗口扫描对比净值", "Target window sweep comparison equity"),
            key="parameter_sweep_target_curves",
            language=language,
        )
        _sweep_metric_line_chart(
            stored["target_factor_curves"],
            _tr(language, "目标窗口单参数扫描折线", "Target-window individual sweep lines"),
            stored["sort_metric"],
            language,
            key="parameter_sweep_target_factor_lines",
        )
        return {
            "sections": _parameter_pdf_sections(stored, language),
            "charts": [
                (_tr(language, "全区间扫描对比净值曲线", "Full-range sweep comparison equity"), stored["full_curves"], list(stored["full_curves"].columns)),
                (_tr(language, "全区间单参数扫描折线", "Full-range individual sweep lines"), stored["full_factor_curves"], list(stored["full_factor_curves"].columns)),
                (_tr(language, "目标窗口扫描对比净值曲线", "Target-window sweep comparison equity"), stored["target_curves"], list(stored["target_curves"].columns)),
                (_tr(language, "目标窗口单参数扫描折线", "Target-window individual sweep lines"), stored["target_factor_curves"], list(stored["target_factor_curves"].columns)),
            ],
        }


def _localized_recommendations(frame: pd.DataFrame, language: str) -> pd.DataFrame:
    if language == "en":
        return frame
    localized = frame.copy()
    direction = {
        "increase": "上调",
        "decrease": "下调",
        "keep": "保持",
    }
    action = {
        "keep current": "保持当前值",
    }
    localized["recommended_direction"] = localized["recommended_direction"].map(direction).fillna(
        localized["recommended_direction"]
    )
    localized["recommended_action"] = localized["recommended_action"].map(action).fillna(
        localized["recommended_action"]
    )
    return localized.rename(
        columns={
            "parameter": "参数",
            "parameter_ui_name": "UI 命名",
            "current_value": "当前值",
            "recommended_value": "建议值",
            "recommended_direction": "建议方向",
            "recommended_action": "建议动作",
            "sort_metric": "排序目标",
            "best_total_return_pct": "最佳总收益(%)",
            "baseline_delta_pct": "相对当前提升(百分点)",
            "default_baseline_delta_pct": "相对默认配置提升(百分点)",
            "preferred_value_min": "适合范围下限",
            "preferred_value_max": "适合范围上限",
        }
    )


def _localized_parameter_frame(frame: pd.DataFrame, language: str) -> pd.DataFrame:
    if language == "en":
        return frame
    return frame.rename(
        columns={
            "mode": "模式",
            "parameter": "参数",
            "parameter_ui_name": "UI 命名",
            "factor": "倍率",
            "original_value": "原始值",
            "tested_value": "测试值",
            "total_return_pct": "总收益(%)",
            "cagr_pct": "CAGR(%)",
            "max_drawdown_pct": "最大回撤(%)",
            "annual_volatility_pct": "年化波动(%)",
            "sharpe_no_rf": "Sharpe",
            "trades": "调仓次数",
            "current_baseline_delta_pct": "相对当前提升(百分点)",
            "default_baseline_delta_pct": "相对默认配置提升(百分点)",
            "note": "备注",
            "best_factor": "最佳倍率",
            "best_value": "最佳值",
            "best_total_return_pct": "最佳总收益(%)",
            "preferred_factor_min": "适合倍率下限",
            "preferred_factor_max": "适合倍率上限",
            "preferred_value_min": "适合值下限",
            "preferred_value_max": "适合值上限",
        }
    )


def _with_parameter_ui_names(frame: pd.DataFrame, settings: dict[str, Any], language: str) -> pd.DataFrame:
    if frame.empty or "parameter" not in frame.columns:
        return frame
    labelled = frame.copy()
    names = labelled["parameter"].apply(lambda parameter: _parameter_ui_name(str(parameter), settings, language))
    if "parameter_ui_name" in labelled.columns:
        labelled["parameter_ui_name"] = names
    else:
        labelled.insert(min(1, len(labelled.columns)), "parameter_ui_name", names)
    return labelled


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


def _sweep_comparison_curves(
    price: pd.Series,
    vix: pd.Series,
    settings: dict[str, Any],
    default_settings: dict[str, Any],
    individual: pd.DataFrame,
    unified: pd.DataFrame,
    *,
    open_price: pd.Series | None,
    result_start: str,
) -> pd.DataFrame:
    curves: dict[str, pd.Series] = {}
    curves["current_config"] = run_backtest(
        price, vix, settings, open_price=open_price, result_start=result_start
    ).equity_curve["equity"]
    curves["default_config"] = run_backtest(
        price, vix, default_settings, open_price=open_price, result_start=result_start
    ).equity_curve["equity"]
    if not individual.empty:
        row = individual.iloc[0]
        candidate = build_parameter_sweep_candidate(
            settings,
            str(row["mode"]),
            str(row["parameter"]),
            float(row["factor"]),
        )
        curves["best_individual"] = run_backtest(
            price, vix, candidate, open_price=open_price, result_start=result_start
        ).equity_curve["equity"]
    if not unified.empty:
        row = unified.iloc[0]
        candidate = build_parameter_sweep_candidate(
            settings,
            str(row["mode"]),
            str(row["parameter"]),
            float(row["factor"]),
        )
        curves["best_unified"] = run_backtest(
            price, vix, candidate, open_price=open_price, result_start=result_start
        ).equity_curve["equity"]
    return pd.DataFrame(curves).dropna(how="all")


def _sweep_factor_curves(frame: pd.DataFrame, metric: str, *, limit: int = 8) -> pd.DataFrame:
    if frame.empty or metric not in frame.columns:
        return pd.DataFrame()
    label_column = "parameter_ui_name" if "parameter_ui_name" in frame.columns else "parameter"
    top_parameters = (
        frame.sort_values(metric, ascending=metric in {"annual_volatility_pct", "trades"})
        ["parameter"]
        .drop_duplicates()
        .head(limit)
        .tolist()
    )
    filtered = frame[frame["parameter"].isin(top_parameters)]
    pivot = filtered.pivot_table(index="factor", columns=label_column, values=metric, aggfunc="first")
    return pivot.sort_index()


def _sweep_metric_line_chart(
    frame: pd.DataFrame,
    title: str,
    metric: str,
    language: str,
    *,
    key: str,
) -> None:
    if frame.empty:
        st.info(_tr(language, "没有足够数据生成扫描折线。", "Not enough data to render sweep lines."))
        return
    chart_data = (
        frame.reset_index()
        .melt(id_vars="factor", var_name="parameter", value_name="value")
        .dropna()
    )
    chart = (
        alt.Chart(chart_data)
        .mark_line(point=True, strokeCap="round")
        .encode(
            x=alt.X("factor:Q", title=_tr(language, "参数倍率", "Parameter factor")),
            y=alt.Y("value:Q", title=metric),
            color=alt.Color("parameter:N", title=_tr(language, "参数", "Parameter")),
            tooltip=[
                alt.Tooltip("factor:Q", title=_tr(language, "参数倍率", "Parameter factor"), format=".2f"),
                alt.Tooltip("parameter:N", title=_tr(language, "参数", "Parameter")),
                alt.Tooltip("value:Q", title=metric, format=",.2f"),
            ],
        )
        .properties(title=title, height=320)
        .interactive()
    )
    st.altair_chart(chart, use_container_width=True, key=key)


def _parameter_pdf_sections(stored: dict[str, Any], language: str) -> list[tuple[str, list[tuple[str, str]]]]:
    _, _, _, recommendations = stored["full"]
    _, _, _, target_recommendations = stored["target"]
    full_rows = [
        (_tr(language, "扫描范围", "Sweep range"), "50% / 75% / 100% / 125% / 150%"),
        (_tr(language, "排序目标", "Ranking objective"), str(stored["sort_label"])),
    ]
    full_rows.extend(_recommendation_rows_for_pdf(recommendations, language))
    target_rows = [
        (_tr(language, "目标日期", "Target date"), str(stored["target_date"])),
        (_tr(language, "时间窗口", "Time window"), f"{stored['window_start']} ~ {stored['window_end']}"),
        (_tr(language, "排序目标", "Ranking objective"), str(stored["sort_label"])),
    ]
    target_rows.extend(_recommendation_rows_for_pdf(target_recommendations, language))
    return [
        (_tr(language, "全区间参数扫描建议", "Full-Range Parameter Sweep Recommendations"), full_rows),
        (_tr(language, "目标日期参数建议表", "Target-Date Parameter Recommendations"), target_rows),
    ]


def _recommendation_rows_for_pdf(frame: pd.DataFrame, language: str, *, limit: int = 8) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for _, row in frame.head(limit).iterrows():
        label = str(row.get("parameter", ""))
        ui_name = str(row.get("parameter_ui_name", label))
        value = (
            f"{_tr(language, 'UI 命名', 'UI name')} {ui_name} | "
            f"{_tr(language, '当前', 'current')} {row.get('current_value')} -> "
            f"{_tr(language, '建议', 'recommended')} {row.get('recommended_value')} | "
            f"{_tr(language, '相对当前', 'vs current')} {row.get('baseline_delta_pct', 0):.2f}pp | "
            f"{_tr(language, '相对默认', 'vs default')} {row.get('default_baseline_delta_pct', 0):.2f}pp"
        )
        rows.append((label, value))
    return rows


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
    active_markets = _active_world_market_regions(market_windows, now)
    world_map_html = build_world_map_markup(active_markets, repeats=1)
    market_status_html = _timeline_market_status_html(active_markets, language)
    market_label_html = _timeline_market_label_html(active_markets)
    st.markdown(
        f"""
<style>
.trade-timeline-wrap {{
  position: relative;
  border: 2px solid var(--leo-surface-rim);
  border-top: 3px solid rgba(174, 143, 84, 0.24);
  border-radius: 0;
  padding: 14px 14px 32px;
  margin: 10px 0 12px;
  background: linear-gradient(145deg, var(--panel-fill-a), var(--panel-fill-b));
  box-shadow: inset 0 1px 0 var(--leo-surface-top), inset 0 -1px 0 var(--leo-surface-bot), 0 0 14px var(--leo-metal-glow);
  backdrop-filter: blur(8px);
  overflow: hidden;
}}
.trade-timeline-map {{
  display: none !important;
}}
.trade-timeline-map::after {{
  content: "";
  position: absolute;
  inset: 0;
  background:
    linear-gradient(90deg, transparent 0%, rgba(244, 240, 232, 0.03) 100%);
  z-index: 1;
  pointer-events: none;
}}
[data-theme="dark"] .trade-timeline-map::after {{
  background:
    linear-gradient(90deg, transparent 0%, rgba(0, 0, 0, 0.06) 100%);
}}
.trade-timeline-map-track {{
  position: relative;
  width: max-content;
  margin-left: auto;
  padding: 8px 0 0;
  animation: none;
}}
.trade-timeline-map-pre {{
  margin: 0;
  font-family: "Courier New", Courier, monospace;
  font-size: 5.5px;
  line-height: 0.62;
  white-space: pre;
  color: rgba(17, 18, 20, 0.10);
}}
[data-theme="dark"] .trade-timeline-map-pre {{
  color: rgba(244, 240, 232, 0.11);
}}
.trade-timeline-map-pre .wm-us.active,
.trade-timeline-map-pre .wm-eu.active,
.trade-timeline-map-pre .wm-asia.active,
.trade-timeline-map-pre .wm-middle_east.active,
.trade-timeline-map-pre .wm-south_america.active,
.trade-timeline-map-pre .wm-asx.active,
.trade-timeline-map-pre .wm-nzx.active {{
  color: rgba(18, 57, 91, 0.78);
  font-weight: 700;
}}
[data-theme="dark"] .trade-timeline-map-pre .wm-us.active,
[data-theme="dark"] .trade-timeline-map-pre .wm-eu.active,
[data-theme="dark"] .trade-timeline-map-pre .wm-asia.active,
[data-theme="dark"] .trade-timeline-map-pre .wm-middle_east.active,
[data-theme="dark"] .trade-timeline-map-pre .wm-south_america.active,
[data-theme="dark"] .trade-timeline-map-pre .wm-asx.active,
[data-theme="dark"] .trade-timeline-map-pre .wm-nzx.active {{
  color: rgba(126, 173, 221, 0.92);
  font-weight: 700;
}}
.trade-map-status {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 8px 0 0;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(244, 240, 232, 0.62) !important;
}}
.trade-map-label {{
  position: absolute;
  z-index: 3;
  transform: translate(-50%, -50%);
  font-family: "Courier New", Courier, monospace;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.04em;
  color: rgba(244, 240, 232, 0.42) !important;
  text-shadow: 0 0 8px rgba(0, 0, 0, 0.34);
  white-space: nowrap;
}}
.trade-map-label.active {{
  color: rgba(126, 173, 221, 0.98) !important;
  text-shadow: 0 0 10px rgba(126, 173, 221, 0.58), 0 0 18px rgba(18, 57, 91, 0.42);
  animation: timeline-market-pulse 4s ease-in-out infinite;
}}
.trade-map-label-us {{ left: 19%; top: 25%; }}
.trade-map-label-south_america {{ left: 31%; top: 63%; }}
.trade-map-label-eu {{ left: 48%; top: 22%; }}
.trade-map-label-middle_east {{ left: 58%; top: 38%; }}
.trade-map-label-asia {{ left: 73%; top: 30%; }}
.trade-map-label-asx {{ left: 83%; top: 75%; }}
.trade-map-label-nzx {{ left: 92%; top: 83%; }}
.trade-map-status span {{
  border: 1px solid rgba(174, 143, 84, 0.18);
  padding: 2px 5px;
  color: rgba(244, 240, 232, 0.62) !important;
  background: rgba(0, 0, 0, 0.16);
}}
[data-testid="stMarkdownContainer"] .trade-map-status span {{
  color: rgba(244, 240, 232, 0.62) !important;
}}
.trade-map-status span.active {{
  color: rgba(126, 173, 221, 0.95) !important;
  border-color: rgba(126, 173, 221, 0.48);
  background: rgba(18, 57, 91, 0.30);
}}
[data-testid="stMarkdownContainer"] .trade-map-status span.active {{
  color: rgba(126, 173, 221, 0.95) !important;
}}
.trade-timeline-content {{
  position: relative;
  z-index: 1;
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
  background: linear-gradient(145deg, var(--panel-fill-a), var(--panel-warm));
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.10), inset 0 -1px 0 rgba(174,143,84,0.05);
  overflow: visible;
}}
.trade-timeline-segment {{
  position: absolute;
  top: 0;
  bottom: 0;
  box-sizing: border-box;
  border: 1px solid rgba(174,143,84,0.24);
  border-radius: 0;
  clip-path: polygon(0.3rem 0, calc(100% - 0.3rem) 0, 100% 0.3rem, 100% calc(100% - 0.3rem), calc(100% - 0.3rem) 100%, 0.3rem 100%, 0 calc(100% - 0.3rem), 0 0.3rem);
  box-shadow:
    inset 0 0 0 1px rgba(255,255,255,.20),
    inset 0 1px 0 rgba(255,255,255,0.14),
    0 0 10px rgba(174,143,84,0.08);
}}
.trade-timeline-segment::after {{
  content: "";
  position: absolute;
  inset: 0;
  background:
    linear-gradient(180deg, rgba(255,255,255,0.16) 0%, rgba(255,255,255,0.04) 44%, transparent 82%),
    radial-gradient(circle at 18% 24%, rgba(255,255,255,0.10) 0%, transparent 34%);
  opacity: 0.34;
  pointer-events: none;
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
  box-shadow: 0 0 8px rgba(255,255,255,0.10);
  z-index: 5;
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
  opacity: .16;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.08);
}}
.trade-deadline-marker {{
  position: absolute;
  top: 0;
  bottom: 0;
  width: 4px;
  box-shadow: 0 0 10px currentColor;
  border-radius: 0;
  z-index: 6;
}}
.trade-deadline-marker span {{
  position: absolute;
  left: 50%;
  top: auto;
  bottom: -20px;
  transform: translateX(-50%);
  max-width: none;
  padding: 1px 4px;
  background: linear-gradient(145deg, var(--panel-fill-a), var(--panel-fill-b));
  border: 1px solid rgba(174,143,84,0.20);
  box-shadow: 0 0 6px rgba(174,143,84,0.08);
  font-size: 11px;
  font-weight: 700;
  line-height: 1.2;
  white-space: nowrap;
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
  gap: 12px;
  margin-top: 8px;
}}
.trade-action-item {{
  position: relative;
  overflow: hidden;
  padding: 5px 8px 5px 18px;
  background: linear-gradient(145deg, var(--panel-fill-a), var(--panel-fill-b));
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
  border: 1px solid rgba(174,143,84,0.20);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.10), 0 0 6px rgba(174,143,84,0.08);
  display: inline-block;
}}
.timeline-countdown-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
  margin: 14px 0 6px;
}}
.timeline-countdown-section {{
  margin: 16px 0 10px;
}}
.timeline-countdown-section + .timeline-countdown-section {{
  margin-top: 22px;
}}
.timeline-countdown-section-title {{
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--leo-kicker);
  margin: 0 0 6px;
}}
.timeline-countdown-card {{
  min-height: 7rem;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  border: 2px solid var(--leo-surface-rim);
  border-radius: 0;
  clip-path: polygon(0.45rem 0, calc(100% - 0.45rem) 0, 100% 0.45rem,
             100% calc(100% - 0.45rem), calc(100% - 0.45rem) 100%,
             0.45rem 100%, 0 calc(100% - 0.45rem), 0 0.45rem);
  padding: 10px 12px;
  background: linear-gradient(145deg, var(--panel-fill-a), var(--panel-fill-b));
  box-shadow: inset 0 1px 0 var(--leo-surface-top), inset 0 -1px 0 var(--leo-surface-bot), 0 0 10px var(--leo-metal-glow);
  color: var(--text-color);
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
  color: var(--text-color);
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
@keyframes timeline-market-pulse {{
  0%, 100% {{ opacity: 0.52; }}
  50% {{ opacity: 1; }}
}}
@media (max-width: 640px) {{
  .trade-timeline-wrap {{
    padding: 12px 10px 34px;
  }}
  .trade-timeline-map {{
    width: 100%;
  }}
  .trade-timeline-map-track {{
    animation: timeline-map-drift 72s linear infinite;
  }}
  .trade-timeline-map-pre {{
    font-size: 4.2px;
    line-height: 0.62;
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
  .timeline-countdown-grid {{
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 6px;
  }}
  .timeline-countdown-card {{
    min-height: 5.35rem;
    padding: 0.5rem 0.55rem;
  }}
  .timeline-countdown-title,
  .timeline-countdown-meta {{
    font-size: 0.68rem;
  }}
  .timeline-countdown-time {{
    font-size: 1.05rem;
  }}
}}
@media (max-width: 360px) {{
  .trade-action-list,
  .timeline-countdown-grid {{
    grid-template-columns: 1fr;
  }}
}}
@keyframes timeline-map-drift {{
  from {{ transform: translateX(0); }}
  to {{ transform: translateX(-50%); }}
}}
@media (prefers-reduced-motion: reduce) {{
  .trade-timeline-map-track,
  .trade-map-label.active {{
    animation: none !important;
  }}
}}
</style>
<div class="trade-timeline-wrap">
  <div class="trade-timeline-map" aria-hidden="true">
    <div class="trade-timeline-map-track">
      <div class="trade-timeline-map-pre">{world_map_html}</div>
      {market_label_html}
    </div>
  </div>
  <div class="trade-timeline-content">
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
    {market_status_html}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def _active_world_market_regions(market_windows: list[dict[str, Any]], now: datetime) -> set[str]:
    active = {
        window["key"]
        for window in market_windows
        if window["open"] <= now <= window["close"]
    }
    regional_sessions = {
        "asia": ("Asia/Tokyo", "09:00", "16:00"),
        "middle_east": ("Asia/Dubai", "10:00", "15:00"),
        "eu": ("Europe/London", "08:00", "16:30"),
        "south_america": ("America/Sao_Paulo", "10:00", "17:00"),
    }
    for region, (tz_name, open_time, close_time) in regional_sessions.items():
        if _is_local_market_session_open(now, tz_name, open_time, close_time):
            active.add(region)
    return active


def _is_local_market_session_open(now: datetime, tz_name: str, open_time: str, close_time: str) -> bool:
    local_now = now.astimezone(ZoneInfo(tz_name))
    if local_now.weekday() >= 5:
        return False
    open_hour, open_minute = map(int, open_time.split(":"))
    close_hour, close_minute = map(int, close_time.split(":"))
    local_open = local_now.replace(hour=open_hour, minute=open_minute, second=0, microsecond=0)
    local_close = local_now.replace(hour=close_hour, minute=close_minute, second=0, microsecond=0)
    return local_open <= local_now <= local_close


def _timeline_market_status_html(active_markets: set[str], language: str) -> str:
    labels = (
        ("us", _tr(language, "美国", "US")),
        ("south_america", _tr(language, "南美", "South America")),
        ("eu", _tr(language, "欧洲", "Europe")),
        ("middle_east", _tr(language, "中东", "Middle East")),
        ("asia", _tr(language, "亚洲", "Asia")),
        ("asx", _tr(language, "澳洲", "Australia")),
        ("nzx", _tr(language, "新西兰", "New Zealand")),
    )
    status = "".join(
        f'<span class="{"active" if key in active_markets else ""}">{html.escape(label)}</span>'
        for key, label in labels
    )
    return f'<div class="trade-map-status">{status}</div>'


def _timeline_market_label_html(active_markets: set[str]) -> str:
    labels = (
        ("us", "US"),
        ("south_america", "SA"),
        ("eu", "EU"),
        ("middle_east", "ME"),
        ("asia", "ASIA"),
        ("asx", "AU"),
        ("nzx", "NZ"),
    )
    return "".join(
        f'<span class="trade-map-label trade-map-label-{key}{" active" if key in active_markets else ""}">++ {html.escape(label)}</span>'
        for key, label in labels
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
        st.markdown("".join(sections), unsafe_allow_html=True)


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


@st.cache_data(ttl=3600)
def _cached_parameter_sweep(
    price: pd.Series,
    vix: pd.Series,
    settings: dict[str, Any],
    *,
    open_price: pd.Series | None,
    result_start: str | None,
    baseline_settings: dict | None = None,
    sort_metric: str = "total_return_pct",
):
    return run_parameter_sweep(
        price,
        vix,
        settings,
        open_price=open_price,
        result_start=result_start,
        baseline_settings=baseline_settings,
        sort_metric=sort_metric,
    )


def _option_index(options: list[str], value: str) -> int:
    return shared_option_index(options, value)


def _inclusive_end(value: date) -> str:
    return str(value + timedelta(days=1))


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
    benchmark_symbol: str | None = None,
) -> None:
    shared_render_lightweight_chart(
        frame,
        columns,
        title,
        key=key,
        label_resolver=lambda series: _series_label(series, language, benchmark_symbol=benchmark_symbol),
        line_styles=line_styles,
        color_overrides=_chart_color_overrides(columns),
    )


def _series_label(series: str, language: str, *, benchmark_symbol: str | None = None) -> str:
    benchmark = benchmark_symbol or "SPY"
    labels = {
        "equity": ("策略净值", "Strategy equity"),
        "buy_hold_equity": (f"{benchmark} 持有", f"{benchmark} buy & hold"),
        "leveraged_buy_hold_equity": (f"3 倍 {benchmark} 买入持有", f"3x {benchmark} buy & hold"),
        "ma120_timing_equity": (f"{benchmark} 120 日择时", f"{benchmark} 120-day timing"),
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


def _chart_color_overrides(columns: list[str]) -> dict[str, str]:
    palette = {
        "equity": "#12395b",
        "buy_hold_equity": "#9e2f2f",
        "leveraged_buy_hold_equity": "#3f8a70",
        "ma120_timing_equity": "#6f43c0",
        "leveraged_ma120_timing_equity": "#c96b2c",
        "target_exposure": "#2f7c63",
        "actual_equivalent_exposure": "#4aa37f",
        "overnight_equivalent_exposure": "#76b89f",
        "intraday_equivalent_exposure": "#2b8d6e",
        "post_close_equivalent_exposure": "#1f6a53",
        "pending_next_open_equivalent_exposure": "#9fd0b3",
    }
    return {column: palette[column] for column in columns if column in palette}


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


def _model_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return shared_model_settings(settings)


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
