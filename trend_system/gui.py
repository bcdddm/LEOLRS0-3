from __future__ import annotations

from io import BytesIO
from copy import deepcopy
from datetime import date, datetime, timedelta
import hashlib
import html
from pathlib import Path
import re
from typing import Any

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
from trend_system.config import load_settings, required_symbols
from trend_system.data import download_prices
from trend_system.exposure_rules import (
    apply_foreign_asset_cap_to_values,
    counts_toward_foreign_cap,
)
from trend_system.portfolio import build_allocation
from trend_system.signals import history_start_date, latest_signal
from trend_system.trade_timeline import trade_timeline_items
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
    selected = st.session_state.get("ui_language") or settings.get("ui", {}).get("language", "zh")
    return "en" if selected == "en" else "zh"


def _tr(language: str, zh: str, en: str) -> str:
    return en if language == "en" else zh


def _apply_session_preferences(settings: dict[str, Any]) -> None:
    ui = settings.setdefault("ui", {})
    profile = settings.setdefault("profile", {})
    if "settings_ui_language" in st.session_state:
        st.session_state["ui_language"] = st.session_state["settings_ui_language"]
    if "settings_home_timezone" in st.session_state:
        st.session_state["home_timezone"] = st.session_state["settings_home_timezone"]
    if "settings_base_currency" in st.session_state:
        st.session_state["base_currency"] = st.session_state["settings_base_currency"]
    if "ui_language" in st.session_state:
        ui["language"] = st.session_state["ui_language"]
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
.block-container {
  overflow-x: hidden !important;
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

    st.title("LEOLRS0-3")
    st.caption(
        _tr(
            language,
            "新西兰时区默认 · 日线级别 · 风险控制优先",
            "New Zealand time zone defaults · Daily signals · Risk control first",
        )
    )

    page_options = {
        _tr(language, "今日信号", "Daily Signal"): "daily",
        _tr(language, "市场健康度", "Market Health"): "market_health",
        _tr(language, "回测", "Backtest"): "backtest",
        _tr(language, "设置总览", "Settings Overview"): "settings",
    }
    page = st.radio(
        _tr(language, "页面", "Page"),
        list(page_options.keys()),
        horizontal=True,
        label_visibility="collapsed",
    )
    if page_options[page] == "daily":
        _daily_tab(working_settings)
    elif page_options[page] == "market_health":
        _market_health_tab(working_settings)
    elif page_options[page] == "backtest":
        _backtest_tab(working_settings)
    else:
        _settings_tab(working_settings, config_path)


def _settings_sidebar(settings: dict[str, Any], config_path: str) -> dict[str, Any]:
    key_prefix = _widget_key_prefix(config_path)
    with st.sidebar.form("settings_form"):
        language = _ui_language(settings)
        st.header(_tr(language, "策略参数", "Strategy Parameters"))

        execution = settings["execution"]
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
            help=_tr(
                language,
                "只有 VIX 低于这个数值时，系统才允许使用杠杆 ETF。",
                "Leveraged ETFs are allowed only when VIX is below this value.",
            ),
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
            help=_tr(
                language,
                "VIX 达到或高于这个数值时，系统会清掉杠杆暴露。",
                "When VIX reaches or exceeds this value, leveraged exposure is cleared.",
            ),
            key=f"{key_prefix}_execution_clear_leverage_when_vix_at_or_above",
        )
        st.caption(
            _tr(
                language,
                "这两个门槛只控制是否允许杠杆 ETF；基础仓位仍由趋势信号和 VIX 分档系数决定。",
                "These thresholds only control leveraged ETF permission; base exposure still comes from trend signals and VIX tiers.",
            )
        )
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
        st.subheader(_tr(language, "趋势信号", "Trend Signal"))
        trend["short_window"] = st.number_input(_tr(language, "短期均线", "Short moving average"), 5, 100, int(trend["short_window"]))
        st.caption(_tr(language, "反映短期动能。数值越小越敏感，越容易提前加仓或减仓。", "Tracks short-term momentum. Smaller values react faster."))
        trend["medium_window"] = st.number_input(_tr(language, "中期均线", "Medium moving average"), 10, 150, int(trend["medium_window"]))
        st.caption(_tr(language, "反映中期趋势。数值越大越稳，但信号会更慢。", "Tracks medium-term trend. Larger values are steadier but slower."))
        trend["long_window"] = st.number_input(_tr(language, "长期均线", "Long moving average"), 50, 300, int(trend["long_window"]))
        st.caption(_tr(language, "判断牛熊环境的主过滤器。越长越保守，越短越容易频繁切换。", "Main bull/bear environment filter. Longer is more conservative."))
        trend["confirmation_days"] = st.number_input(_tr(language, "连续确认天数", "Confirmation days"), 1, 10, int(trend["confirmation_days"]))
        st.caption(_tr(language, "要求信号连续成立多少天才确认。调高可减少假突破，但会牺牲反应速度。", "Requires a signal to hold for this many days. Higher values reduce false breaks but react slower."))
        st.subheader(_tr(language, "基础仓位边界", "Base Exposure Bounds"))
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

        # ── 简单模块 ─────────────────────────────────────────────────────────
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

        # ── 高级模块 (折叠) ──────────────────────────────────────────────────
        st.divider()
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
    cols = st.columns([1, 1, 1, 1, 1])
    start = cols[0].date_input(_tr(language, "数据起始日期", "Data start date"), value=date.today(), key="daily_start")
    run = _aligned_button(cols[1], _tr(language, "更新今日信号", "Update daily signal"), type="primary", use_container_width=True)
    timeline_mode_labels = _daily_timeline_mode_labels(language)
    _nz_label = _tr(language, "NZ 盘末 / 美股开盘", "NZ close / US open")
    if "daily_timeline_mode" not in st.session_state:
        st.session_state["daily_timeline_mode"] = _nz_label
    selected_timeline_mode_label = cols[2].selectbox(
        _tr(language, "交易时间轴模式", "Timeline mode"),
        list(timeline_mode_labels.keys()),
        key="daily_timeline_mode",
    )
    timeline_mode = timeline_mode_labels[selected_timeline_mode_label]
    settings.setdefault("backtest", {})["execution_timing"] = timeline_mode

    if not run and "daily_result" not in st.session_state:
        _disabled_pdf_button(language, _tr(language, "打印/下载今日信号 PDF", "Print/Download Daily Signal PDF"), key="daily_pdf_disabled")
        st.info(_tr(language, "今日信号尚未加载。", "Daily signal has not been loaded yet."))
        _market_windows(settings, timeline_mode)
        return

    if run:
        with st.spinner(_tr(language, "正在下载 Yahoo Finance 数据...", "Downloading Yahoo Finance data...")):
            data_start = history_start_date(start, settings)
            prices = _cached_prices(tuple(required_symbols_from_raw(settings)), str(data_start), None, True)
            primary = settings["signals"]["primary"]
            vix_symbol = settings["signals"]["volatility"]
            price_field = settings["signals"].get("price_field", "Close")
            try:
                signal = latest_signal(prices[primary][price_field], prices[vix_symbol][price_field], settings)
            except RuntimeError as exc:
                st.error(
                    f"{_tr(language, '信号计算失败，数据不足，请尝试将数据起始日期调早。', 'Signal calculation failed — not enough data. Try moving the data start date further back.')}"
                    f"\n\n`{exc}`"
                )
                st.session_state.pop("daily_result", None)
                return
            allocation = build_allocation(signal.target_exposure, signal.vix, settings)
            st.session_state["daily_result"] = (signal, allocation)
            st.session_state["daily_prices"] = prices
            st.session_state["daily_fingerprint"] = _fingerprint(settings, {"start": str(start)})

    if _is_stale("daily_fingerprint", settings, {"start": str(start)}):
        st.warning(_tr(language, "数据已更改，请重新回测并刷新数据。", "Settings changed. Please refresh the data."))

    signal, allocation = st.session_state["daily_result"]
    ma_short_label, ma_medium_label, ma_long_label = _trend_ma_labels(settings)
    ma_summary_label = f"{ma_short_label} / {ma_medium_label} / {ma_long_label}"
    daily_rows = [
        (_tr(language, "信号日期", "Signal date"), str(signal.date.date())),
        (_tr(language, "核心价格", "Core price"), f"{signal.price:.2f}"),
        (ma_summary_label, f"{signal.ma_short:.2f} / {signal.ma_medium:.2f} / {signal.ma_long:.2f}"),
        (_tr(language, "趋势", "Trend"), f"{_state_label(signal.trend_label, language)} ({signal.trend_exposure:.0f}%)"),
        ("VIX", f"{signal.vix:.2f} ({_state_label(signal.vix_label, language)})"),
        (_tr(language, "VIX 系数", "VIX multiplier"), f"x{signal.vix_multiplier:.2f}"),
        (_tr(language, "目标等效仓位", "Target equivalent exposure"), f"{signal.target_exposure:.0f}%"),
        (allocation.core_asset, f"{allocation.core_percent:.2f}%"),
        (allocation.leveraged_asset or _tr(language, "无杠杆", "No leverage"), f"{allocation.leveraged_percent:.2f}%"),
        (allocation.defensive_asset, f"{allocation.defensive_percent:.2f}%"),
    ]
    _pdf_download_button(
        language,
        _tr(language, "打印/下载今日信号 PDF", "Print/Download Daily Signal PDF"),
        _build_pdf_report(
            _tr(language, "今日信号", "Daily Signal"),
            settings,
            language,
            sections=[
                (_tr(language, "市场状态", "Market State"), daily_rows),
                (_tr(language, "策略信息", "Strategy Information"), _strategy_summary_rows(settings, language)),
            ],
            notes=allocation.notes,
        ),
        _pdf_filename("daily-signal", settings),
        key="daily_pdf_download",
    )
    st.subheader(_tr(language, "市场状态", "Market State"))
    metric_cols = st.columns(5)
    metric_cols[0].metric(_tr(language, "SPY 收盘价", "SPY close"), f"{signal.price:.2f}")
    metric_cols[1].metric(_tr(language, "趋势", "Trend"), _state_label(signal.trend_label, language), f"{signal.trend_exposure:.0f}%")
    metric_cols[2].metric("VIX", f"{signal.vix:.2f}", _state_label(signal.vix_label, language))
    metric_cols[3].metric(_tr(language, "VIX 系数", "VIX multiplier"), f"x{signal.vix_multiplier:.2f}")
    metric_cols[4].metric(_tr(language, "目标等效仓位", "Target equivalent exposure"), f"{signal.target_exposure:.0f}%")
    if (
        settings.get("position", {}).get("trend_quality_ma_cross_slow_decline_enabled", False)
        and signal.trend_quality_slow_decline
    ):
        st.warning(
            _tr(
                language,
                f"趋势质量警告：120 日均线（{signal.trend_quality_ma_120:.2f}）低于 200 日均线（{signal.trend_quality_ma_200:.2f}），系统判定当前处于（阴跌）状态。",
                f"Trend quality warning: the 120-day MA ({signal.trend_quality_ma_120:.2f}) is below the 200-day MA ({signal.trend_quality_ma_200:.2f}), so the system treats the market as being in slow-decline state.",
            )
        )

    st.subheader(_tr(language, "执行仓位", "Execution Allocation"))
    alloc_cols = st.columns(4)
    alloc_cols[0].metric(allocation.core_asset, f"{allocation.core_percent:.2f}%")
    alloc_cols[1].metric(allocation.leveraged_asset or _tr(language, "无杠杆", "No leverage"), f"{allocation.leveraged_percent:.2f}%")
    alloc_cols[2].metric(allocation.defensive_asset, f"{allocation.defensive_percent:.2f}%")
    alloc_cols[3].metric(_tr(language, "等效仓位", "Equivalent exposure"), f"{allocation.equivalent_exposure:.2f}%")
    if allocation.notes:
        st.warning("\n".join(allocation.notes))

    ma_frame = pd.DataFrame(
        {
            _tr(language, "数值", "Value"): {
                ma_short_label: signal.ma_short,
                ma_medium_label: signal.ma_medium,
                ma_long_label: signal.ma_long,
            }
        }
    )
    st.bar_chart(ma_frame)
    _portfolio_adjustment_section(settings, allocation, st.session_state.get("daily_prices", {}), signal.date)
    _market_windows(settings, timeline_mode)


def _market_health_tab(settings: dict[str, Any]) -> None:
    language = _ui_language(settings)
    st.subheader(_tr(language, "市场健康度", "Market Health"))
    st.caption(
        _tr(
            language,
            "这个页面把高杠杆是否可用拆成独立的市场健康度判断：只有趋势结构修复后，才允许系统重新进入进攻模式。",
            "This page separates leveraged exposure permission into a market-health check: the system only returns to offensive mode after the trend structure repairs.",
        )
    )
    cols = st.columns([1, 1, 1])
    start = cols[0].date_input(
        _tr(language, "健康度数据起始日期", "Health data start date"),
        value=date.today(),
        key="market_health_start",
    )
    run = _aligned_button(cols[1], _tr(language, "更新市场健康度", "Update market health"), type="primary", use_container_width=True)
    primary = settings["signals"]["primary"]
    price_field = settings["signals"].get("price_field", "Close")
    if not run and "market_health_price" not in st.session_state:
        _disabled_pdf_button(language, _tr(language, "打印/下载市场健康度 PDF", "Print/Download Market Health PDF"), key="market_health_pdf_disabled")
        st.info(_tr(language, "市场健康度尚未加载。", "Market health has not been loaded yet."))
        _market_health_strategy_notes(language)
        return
    if run:
        with st.spinner(_tr(language, "正在下载价格并计算市场健康度...", "Downloading prices and calculating market health...")):
            data_start = history_start_date(start, settings, include_market_health=True)
            prices = _cached_prices((primary,), str(data_start), None, True)
            price = _price_series(prices[primary], price_field).dropna()
            st.session_state["market_health_price"] = price
            st.session_state["market_health_symbol"] = primary
            st.session_state["market_health_display_start"] = start

    price = st.session_state["market_health_price"]
    ma120 = price.rolling(120, min_periods=1).mean()
    ma200 = price.rolling(200, min_periods=1).mean()
    latest_price = float(price.iloc[-1])
    latest_ma120 = float(ma120.iloc[-1])
    latest_ma200 = float(ma200.iloc[-1])
    slow_decline = latest_ma120 < latest_ma200
    healthy = latest_ma120 > latest_ma200
    stage = (
        _tr(language, "预警期：（阴跌）尚未结束", "Warning: slow-decline state is not over")
        if slow_decline
        else _tr(language, "恢复期：结构已修复", "Recovery: structure has repaired")
        if healthy
        else _tr(language, "中性：120/200 均线接近", "Neutral: 120/200 MAs are close")
    )

    health_rows = [
        (_tr(language, "标的", "Symbol"), primary),
        (_tr(language, "最新日期", "Latest date"), str(price.index[-1].date())),
        (_tr(language, "最新价格", "Latest price"), f"{latest_price:.2f}"),
        ("MA120", f"{latest_ma120:.2f}"),
        ("MA200", f"{latest_ma200:.2f}"),
        (_tr(language, "健康阶段", "Health stage"), stage),
        (_tr(language, "是否阴跌", "Slow decline"), _tr(language, "是", "Yes") if slow_decline else _tr(language, "否", "No")),
    ]
    _pdf_download_button(
        language,
        _tr(language, "打印/下载市场健康度 PDF", "Print/Download Market Health PDF"),
        _build_pdf_report(
            _tr(language, "市场健康度", "Market Health"),
            settings,
            language,
            sections=[
                (_tr(language, "健康度摘要", "Health Summary"), health_rows),
                (_tr(language, "策略信息", "Strategy Information"), _strategy_summary_rows(settings, language)),
            ],
            notes=_market_health_note_lines(language),
        ),
        _pdf_filename("market-health", settings),
        key="market_health_pdf_download",
    )
    metric_cols = st.columns(4)
    metric_cols[0].metric(primary, f"{latest_price:.2f}")
    metric_cols[1].metric("MA120", f"{latest_ma120:.2f}")
    metric_cols[2].metric("MA200", f"{latest_ma200:.2f}")
    metric_cols[3].metric(_tr(language, "健康阶段", "Health stage"), stage)
    if slow_decline:
        st.warning(
            _tr(
                language,
                "市场健康度警告：120 日均线低于 200 日均线，视为（阴跌）状态。策略最高只允许 100% 等效仓位，不使用 3 倍杠杆。",
                "Market health warning: the 120-day MA is below the 200-day MA, treated as slow-decline state. The strategy allows at most 100% equivalent exposure and does not use 3x leverage.",
            )
        )
    else:
        st.success(
            _tr(
                language,
                "市场健康度未处于（阴跌）状态；高仓位仍需继续通过趋势、VIX 和回撤模块确认。",
                "Market health is not in slow-decline state; high exposure still needs confirmation from trend, VIX, and drawdown modules.",
            )
        )

    display_start = pd.Timestamp(st.session_state.get("market_health_display_start", start))
    display_price = price.loc[price.index >= display_start]
    display_ma120 = ma120.loc[ma120.index >= display_start]
    display_ma200 = ma200.loc[ma200.index >= display_start]
    health_frame = pd.DataFrame(
        {
            "price": display_price,
            "ma120": display_ma120,
            "ma200": display_ma200,
        }
    ).tail(260)
    health_frame.index.name = "date"
    _zoomable_line_chart(
        health_frame.rename(columns={"price": "health_price", "ma120": "health_ma120", "ma200": "health_ma200"}),
        ["health_price", "health_ma120", "health_ma200"],
        _tr(language, "市场健康度曲线", "Market health chart"),
        key="market_health_chart",
        language=language,
    )
    _market_health_strategy_notes(language)


def _market_health_strategy_notes(language: str) -> None:
    st.markdown(f"**{_tr(language, '操作纪律', 'Operating Rules')}**")
    st.markdown("\n".join(_market_health_note_lines(language)))


def _market_health_note_lines(language: str) -> list[str]:
    if language == "en":
        return [
            "1. Normal market: trend and VIX modules may allow high exposure or leverage.",
            "2. Warning phase: price or short MAs may look fine, but if 120MA < 200MA, slow-decline state is not over; cap at 100% and avoid 3x leverage.",
            "3. Recovery phase: only unlock after 120MA > 200MA, then let trend, VIX, and drawdown modules restore high exposure gradually.",
            "4. False-trigger guard: no high leverage while the market has not made new highs for a long time or while 120/200 has not repaired.",
        ]
    return [
        "1. 正常市场：允许按趋势和 VIX 模块加到高仓位或杠杆。",
        "2. 预警期：价格或短均线看起来还不错，但 120MA < 200MA，视为（阴跌）尚未结束；最高只允许 100%，不使用 3 倍杠杆。",
        "3. 恢复期：只有当 120MA > 200MA 后，才解除（阴跌）锁定，再允许系统根据趋势、VIX、回撤逐步恢复高仓位。",
        "4. 防误触：长期不创新高或 120/200 未修复时，都不碰高杠杆。",
    ]


def _aligned_button(container: Any, label: str, **kwargs: Any) -> bool:
    container.markdown('<div style="height: 1.75rem;"></div>', unsafe_allow_html=True)
    return container.button(label, **kwargs)


def _backtest_tab(settings: dict[str, Any]) -> None:
    language = _ui_language(settings)
    st.subheader(_tr(language, "历史回测", "Historical Backtest"))
    st.caption(_tr(language, "仓位曲线显示的是实际目标等效仓位。最大等效仓位只是上限；若趋势仓位 × VIX 系数达不到上限，曲线不会碰到 300%。", "The exposure curve shows actual target equivalent exposure. The maximum exposure is only a cap."))
    preset_labels = {
        _tr(language, "自定义", "Custom"): "自定义",
        _tr(language, "2000-01-01 到 2010-01-01", "2000-01-01 to 2010-01-01"): "2000-01-01 到 2010-01-01",
        _tr(language, "2010-01-01 到现在", "2010-01-01 to today"): "2010-01-01 到现在",
        _tr(language, "2021-01-01 到 2023-12-31", "2021-01-01 to 2023-12-31"): "2021-01-01 到 2023-12-31",
        _tr(language, "2000-01-01 到现在", "2000-01-01 to today"): "2000-01-01 到现在",
    }
    preset_label = st.selectbox(_tr(language, "回测区间预设", "Backtest date preset"), list(preset_labels.keys()))
    preset = preset_labels[preset_label]
    default_start, default_end = _backtest_date_defaults(preset, settings)

    cols = st.columns([1, 1, 1, 1, 1])
    start = cols[0].date_input(
        _tr(language, "回测起始日期", "Backtest start date"),
        value=default_start,
        min_value=BACKTEST_MIN_DATE,
        max_value=BACKTEST_MAX_DATE,
        key=f"backtest_start_{preset}",
    )
    end = cols[1].date_input(
        _tr(language, "回测结束日期", "Backtest end date"),
        value=default_end,
        min_value=BACKTEST_MIN_DATE,
        max_value=BACKTEST_MAX_DATE,
        key=f"backtest_end_{preset}",
    )
    initial = cols[2].number_input(_tr(language, "初始资金", "Initial capital"), 1000.0, 10_000_000.0, float(settings["backtest"]["initial_capital"]), 1000.0)
    settings["backtest"]["initial_capital"] = initial
    weekly_contribution = cols[3].number_input(
        _tr(language, "每周追加资金", "Weekly contribution"),
        0.0,
        1_000_000.0,
        float(settings["backtest"].get("weekly_contribution", 0.0)),
        100.0,
        help=_tr(
            language,
            "每个新交易周开始时追加到策略和所有参考曲线。第一条回测记录只使用初始资金。",
            "Added to the strategy and all benchmark curves at the start of each new trading week. The first backtest row uses only initial capital.",
        ),
    )
    settings["backtest"]["weekly_contribution"] = weekly_contribution
    run = _aligned_button(cols[4], _tr(language, "运行回测", "Run backtest"), type="primary", use_container_width=True)
    chart_settings = st.columns([1, 1, 1, 2])
    show_leveraged_buy_hold = chart_settings[0].toggle(
        _tr(language, "显示 3 倍买入持有虚线", "Show dashed 3x buy & hold"),
        value=bool(settings["backtest"].get("show_leveraged_buy_hold", True)),
    )
    show_ma120_timing = chart_settings[1].toggle(
        _tr(language, "显示 120 日择时点线", "Show dotted 120-day timing"),
        value=bool(settings["backtest"].get("show_ma120_timing", True)),
    )
    show_leveraged_ma120_timing = chart_settings[2].toggle(
        _tr(language, "显示三倍持有：跌破 120 日均线转现金", "Show 3x Hold: Cash Below 120MA"),
        value=bool(settings["backtest"].get("show_leveraged_ma120_timing", True)),
    )
    use_actual_leveraged_returns = chart_settings[3].toggle(
        _tr(language, "使用真实杠杆 ETF 收益", "Use actual leveraged ETF returns"),
        value=bool(settings["backtest"].get("use_actual_leveraged_asset_returns", False)),
        help=_tr(
            language,
            "开启后，策略杠杆部分和 3 倍持有曲线会使用配置里的杠杆 ETF 真实价格，例如 SPXL；关闭时使用 S&P 500 日收益 × 杠杆倍数的理论口径。",
            "When enabled, the strategy leveraged sleeve and 3x hold line use the configured leveraged ETF's actual price, for example SPXL. When off, they use the synthetic S&P 500 daily return x leverage multiple.",
        ),
    )
    settings["backtest"]["show_leveraged_buy_hold"] = show_leveraged_buy_hold
    settings["backtest"]["show_ma120_timing"] = show_ma120_timing
    settings["backtest"]["show_leveraged_ma120_timing"] = show_leveraged_ma120_timing
    settings["backtest"]["use_actual_leveraged_asset_returns"] = use_actual_leveraged_returns
    chart_settings[3].caption(
        _tr(
            language,
            "前三个开关只影响净值图显示；真实杠杆 ETF 收益会改变回测结果。",
            "The first three toggles only affect the equity chart display; actual leveraged ETF returns change the backtest result.",
        )
    )
    execution_timing_labels = _execution_timing_labels(language)
    current_execution_timing = settings["backtest"].get(
        "execution_timing",
        "next_session" if settings["backtest"].get("signal_effective_next_day", True) else "same_close",
    )
    selected_execution_timing_label = st.selectbox(
        _tr(language, "回测执行时点", "Backtest execution timing"),
        list(execution_timing_labels.keys()),
        index=_option_index(
            list(execution_timing_labels.keys()),
            next(
                (
                    label
                    for label, value in execution_timing_labels.items()
                    if value == current_execution_timing
                ),
                list(execution_timing_labels.keys())[0],
            ),
        ),
        help=_tr(
            language,
            "选择信号生成后用哪一个交易时点进入新仓位。",
            "Choose when a new position starts after a signal is generated.",
        ),
    )
    execution_timing = execution_timing_labels[selected_execution_timing_label]
    settings["backtest"]["execution_timing"] = execution_timing
    settings["backtest"]["signal_effective_next_day"] = execution_timing != "same_close"
    if execution_timing == "next_session":
        st.info(
            _tr(
                language,
                "回测备忘：当日收益使用前一交易日收盘后已经持有的仓位计算；当日收盘数据只生成新的调仓信号，新仓位从下一交易日开始生效。因此，即使当天暴涨才触发加仓，策略也不会吃到当天涨幅，只会在当天收盘后记录调仓。",
                "Backtest note: each day's return is calculated using the position already held after the previous close. The current close only generates a new rebalance signal, and the new position starts from the next trading day. So if a sharp rally triggers an add-exposure signal, the strategy does not capture that same-day rally; it records the rebalance after the close.",
            )
        )
    elif execution_timing == "same_close":
        st.warning(
            _tr(
                language,
                "当前为激进口径：当天收盘信号会在当天收益前生效，可能包含前视偏差，只适合与下一交易日生效口径做对照。",
                "Aggressive mode is active: the same-day close signal applies before that day's return. This can include look-ahead bias and should only be used for comparison.",
            )
        )

    if end < start:
        st.error(_tr(language, "回测结束日期不能早于开始日期。", "Backtest end date cannot be earlier than the start date."))
        return

    if not run and "backtest_result" not in st.session_state:
        _disabled_pdf_button(language, _tr(language, "打印/下载历史回测 PDF", "Print/Download Backtest PDF"), key="backtest_pdf_disabled")
        st.info(_tr(language, "回测尚未运行。", "Backtest has not been run yet."))
        return

    fingerprint_extras = {
        "start": str(start),
        "end": str(end),
        "initial_capital": str(initial),
        "weekly_contribution": str(weekly_contribution),
        "execution_timing": execution_timing,
        "use_actual_leveraged_returns": str(use_actual_leveraged_returns),
    }
    if run:
        with st.status(_tr(language, "准备回测...", "Preparing backtest..."), expanded=True) as status:
            primary = settings["signals"]["primary"]
            vix_symbol = settings["signals"]["volatility"]
            leveraged_symbol = settings["execution"]["leveraged_asset"]
            price_field = settings["signals"].get("price_field", "Close")
            symbols = [primary, vix_symbol]
            if use_actual_leveraged_returns:
                symbols.append(leveraged_symbol)
            status.update(label=_tr(language, "下载或读取缓存中的历史价格...", "Downloading or reading cached price history..."))
            data_start = history_start_date(start, settings)
            prices = _cached_prices(tuple(dict.fromkeys(symbols)), str(data_start), _inclusive_end(end), True)
            status.update(label=_tr(language, "整理价格序列...", "Preparing price series..."))
            open_price = prices[primary].get("Open")
            leveraged_prices = prices.get(leveraged_symbol) if use_actual_leveraged_returns else None
            leveraged_price = (
                leveraged_prices[price_field]
                if leveraged_prices is not None and price_field in leveraged_prices
                else None
            )
            leveraged_open_price = leveraged_prices.get("Open") if leveraged_prices is not None else None
            status.update(label=_tr(language, "运行回测模型...", "Running backtest model..."))
            model_settings = _model_settings(settings)
            result = _cached_backtest(
                prices[primary][price_field],
                prices[vix_symbol][price_field],
                model_settings,
                open_price=open_price,
                leveraged_price=leveraged_price,
                leveraged_open_price=leveraged_open_price,
                result_start=str(start),
            )
            status.update(label=_tr(language, "生成图表和指标...", "Rendering charts and metrics..."), state="complete")
            st.session_state["backtest_result"] = result
            st.session_state["backtest_fingerprint"] = _fingerprint(
                settings,
                fingerprint_extras,
            )

    result = st.session_state["backtest_result"]
    if _is_stale(
        "backtest_fingerprint",
        settings,
        fingerprint_extras,
    ):
        st.warning(_tr(language, "数据已更改，请重新回测并刷新数据。", "Settings changed. Please rerun the backtest."))

    parameter_report = _parameter_debug_section(settings, start, end, language)

    metrics = result.metrics
    backtest_rows = [
        (_tr(language, "回测区间", "Backtest range"), f"{start} ~ {end}"),
        (_tr(language, "初始资金", "Initial capital"), f"{initial:,.2f}"),
        (_tr(language, "每周追加资金", "Weekly contribution"), f"{weekly_contribution:,.2f}"),
        (_tr(language, "执行时点", "Execution timing"), execution_timing),
        (_tr(language, "策略总收益", "Strategy total return"), f"{metrics.get('total_return_pct', 0):.2f}%"),
        ("CAGR", f"{metrics.get('cagr_pct', 0):.2f}%"),
        (_tr(language, "最大回撤", "Max drawdown"), f"{metrics.get('max_drawdown_pct', 0):.2f}%"),
        (_tr(language, "年化波动", "Annual volatility"), f"{metrics.get('annual_volatility_pct', 0):.2f}%"),
        ("Sharpe", f"{metrics.get('sharpe_no_rf', 0):.2f}"),
        (_tr(language, "基准总收益", "Benchmark total return"), f"{metrics.get('buy_hold_total_return_pct', 0):.2f}%"),
        (_tr(language, "基准 CAGR", "Benchmark CAGR"), f"{metrics.get('buy_hold_cagr_pct', 0):.2f}%"),
        (_tr(language, "调仓次数", "Rebalances"), str(len(result.trades))),
    ]
    latest_curve = result.equity_curve.iloc[-1]
    curve_rows = [
        (_tr(language, "策略净值", "Strategy equity"), f"{latest_curve.get('equity', 0):,.2f}"),
        (_tr(language, "S&P 500 持有", "S&P 500 buy & hold"), f"{latest_curve.get('buy_hold_equity', 0):,.2f}"),
        (_tr(language, "3 倍 S&P 500 买入持有", "3x S&P 500 buy & hold"), f"{latest_curve.get('leveraged_buy_hold_equity', 0):,.2f}"),
        (_tr(language, "S&P 500 120 日择时", "S&P 500 120-day timing"), f"{latest_curve.get('ma120_timing_equity', 0):,.2f}"),
        (_tr(language, "三倍持有：跌破 120 日均线转现金", "3x Hold: Cash Below 120MA"), f"{latest_curve.get('leveraged_ma120_timing_equity', 0):,.2f}"),
        (_tr(language, "目标等效仓位", "Target equivalent exposure"), f"{latest_curve.get('target_exposure', 0):.2f}%"),
    ]
    curve_rows.append(
        (_tr(language, "实际等效仓位", "Actual equivalent exposure"), f"{latest_curve.get('actual_equivalent_exposure', 0):.2f}%")
    )
    pdf_sections = [
        (_tr(language, "回测表现", "Backtest Performance"), backtest_rows),
        (_tr(language, "净值和仓位曲线摘要", "Equity and Exposure Summary"), curve_rows),
        (_tr(language, "策略信息", "Strategy Information"), _strategy_summary_rows(settings, language)),
    ]
    trade_rows = _trade_summary_rows(result.trades, language)
    if trade_rows:
        pdf_sections.append((_tr(language, "最近调仓记录", "Latest Rebalances"), trade_rows))
    pdf_charts = [
        (
            _tr(language, "净值曲线", "Equity curve"),
            result.equity_curve,
            equity_columns_for_pdf(show_leveraged_buy_hold, show_ma120_timing, show_leveraged_ma120_timing),
        ),
        (
            _tr(language, "仓位曲线", "Exposure curve"),
            result.equity_curve,
            _exposure_columns_for_timing(execution_timing),
        ),
    ]
    if parameter_report:
        pdf_sections.extend(parameter_report["sections"])
        pdf_charts.extend(parameter_report["charts"])
    _pdf_download_button(
        language,
        _tr(language, "打印/下载历史回测 PDF", "Print/Download Backtest PDF"),
        _build_pdf_report(
            _tr(language, "历史回测", "Historical Backtest"),
            settings,
            language,
            sections=pdf_sections,
            charts=pdf_charts,
        ),
        _pdf_filename(
            "backtest",
            settings,
            range_text=f"{start}_to_{end}",
            cagr=metrics.get("cagr_pct", 0.0),
        ),
        key="backtest_pdf_download",
    )
    st.markdown(f"**{_tr(language, '策略表现', 'Strategy Performance')}**")
    metric_cols = st.columns(5)
    metric_cols[0].metric(_tr(language, "策略总收益", "Strategy total return"), f"{metrics.get('total_return_pct', 0):.2f}%")
    metric_cols[1].metric("策略 CAGR", f"{metrics.get('cagr_pct', 0):.2f}%")
    metric_cols[2].metric(_tr(language, "策略最大回撤", "Strategy max drawdown"), f"{metrics.get('max_drawdown_pct', 0):.2f}%")
    metric_cols[3].metric(_tr(language, "策略年化波动", "Strategy annual volatility"), f"{metrics.get('annual_volatility_pct', 0):.2f}%")
    metric_cols[4].metric("策略 Sharpe", f"{metrics.get('sharpe_no_rf', 0):.2f}")

    benchmark_symbol = settings["signals"]["primary"]
    st.markdown(f"**{_tr(language, '买入并持有基准', 'Buy-and-hold benchmark')}: {benchmark_symbol}**")
    benchmark_cols = st.columns(5)
    benchmark_cols[0].metric(_tr(language, "基准总收益", "Benchmark total return"), f"{metrics.get('buy_hold_total_return_pct', 0):.2f}%")
    benchmark_cols[1].metric("基准 CAGR", f"{metrics.get('buy_hold_cagr_pct', 0):.2f}%")
    benchmark_cols[2].metric(_tr(language, "基准最大回撤", "Benchmark max drawdown"), f"{metrics.get('buy_hold_max_drawdown_pct', 0):.2f}%")
    benchmark_cols[3].metric(_tr(language, "基准年化波动", "Benchmark annual volatility"), f"{metrics.get('buy_hold_annual_volatility_pct', 0):.2f}%")
    benchmark_cols[4].metric("基准 Sharpe", f"{metrics.get('buy_hold_sharpe_no_rf', 0):.2f}")
    st.caption(_tr(language, "CAGR = 年化复合增长率，表示资金按复利计算后平均每年增长多少；它不是简单平均年收益。", "CAGR is compound annual growth rate. It is not a simple average annual return."))

    if st.button(_tr(language, "回正净值图", "Reset equity chart")):
        st.session_state["equity_chart_reset"] = st.session_state.get("equity_chart_reset", 0) + 1
    equity_columns = ["equity", "buy_hold_equity"]
    equity_line_styles = {"equity": "solid", "buy_hold_equity": "solid"}
    if show_leveraged_buy_hold:
        equity_columns.append("leveraged_buy_hold_equity")
        equity_line_styles["leveraged_buy_hold_equity"] = "dashed"
    if show_ma120_timing:
        equity_columns.append("ma120_timing_equity")
        equity_line_styles["ma120_timing_equity"] = "dotted"
    if show_leveraged_ma120_timing:
        equity_columns.append("leveraged_ma120_timing_equity")
        equity_line_styles["leveraged_ma120_timing_equity"] = "dotted"
    _zoomable_line_chart(
        result.equity_curve,
        equity_columns,
        _tr(language, "净值曲线", "Equity curve"),
        key=f"equity_chart_{st.session_state.get('equity_chart_reset', 0)}",
        language=language,
        line_styles=equity_line_styles,
    )
    if st.button(_tr(language, "回正仓位图", "Reset exposure chart")):
        st.session_state["exposure_chart_reset"] = st.session_state.get("exposure_chart_reset", 0) + 1
    _zoomable_line_chart(
        result.equity_curve,
        _exposure_columns_for_timing(execution_timing),
        _tr(language, "仓位曲线", "Exposure curve"),
        key=f"exposure_chart_{st.session_state.get('exposure_chart_reset', 0)}",
        language=language,
    )

    with st.expander(_tr(language, "调仓记录", "Rebalance Log")):
        trade_view = st.radio(
            _tr(language, "显示范围", "Rows"),
            [
                _tr(language, "最近 50 笔", "Latest 50"),
                _tr(language, "全部", "All"),
            ],
            horizontal=True,
        )
        trades_to_show = result.trades.tail(50) if trade_view.startswith(_tr(language, "最近", "Latest")) else result.trades
        st.dataframe(trades_to_show, use_container_width=True, height=320)
        st.download_button(
            _tr(language, "下载调仓记录 CSV", "Download rebalance log CSV"),
            data=result.trades.to_csv(index=False).encode("utf-8"),
            file_name="trades.csv",
            mime="text/csv",
        )


def _settings_tab(settings: dict[str, Any], config_path: str) -> None:
    language = _ui_language(settings)
    st.subheader(_tr(language, "当前设置", "Current Settings"))
    st.caption(f"{_tr(language, '来源', 'Source')}: {Path(config_path).resolve()}")

    st.markdown(f"**{_tr(language, '个人偏好', 'Preferences')}**")
    pref_cols = st.columns(3)
    ui = settings.setdefault("ui", {})
    profile = settings.setdefault("profile", {})
    selected_language = pref_cols[0].selectbox(
        _tr(language, "界面语言", "Interface language"),
        ["zh", "en"],
        index=_option_index(["zh", "en"], ui.get("language", "zh")),
        format_func=lambda value: "中文" if value == "zh" else "English",
        key="settings_ui_language",
    )
    selected_timezone = pref_cols[1].selectbox(
        _tr(language, "居住地区", "Home region"),
        [
            "Pacific/Auckland",
            "Australia/Sydney",
            "Asia/Shanghai",
            "America/New_York",
            "UTC",
        ],
        index=_option_index(
            [
                "Pacific/Auckland",
                "Australia/Sydney",
                "Asia/Shanghai",
                "America/New_York",
                "UTC",
            ],
            profile.get("home_timezone", "Pacific/Auckland"),
        ),
        key="settings_home_timezone",
    )
    selected_currency = pref_cols[2].selectbox(
        _tr(language, "基础货币", "Base currency"),
        ["NZD", "AUD", "USD", "CNY"],
        index=_option_index(["NZD", "AUD", "USD", "CNY"], profile.get("base_currency", "NZD")),
        key="settings_base_currency",
    )
    ui["language"] = selected_language
    profile["home_timezone"] = selected_timezone
    profile["base_currency"] = selected_currency
    st.session_state["ui_language"] = selected_language
    st.session_state["home_timezone"] = selected_timezone
    st.session_state["base_currency"] = selected_currency
    st.caption(
        _tr(
            language,
            "这些偏好会立即影响当前会话；点击保存当前设置后会写入配置文件。",
            "These preferences affect the current session immediately; save current settings to write them to the config file.",
        )
    )

    save_cols = st.columns([1, 1, 2])
    if _aligned_button(save_cols[0], _tr(language, "保存当前设置", "Save current settings"), type="primary", use_container_width=True):
        try:
            _save_config(Path(config_path), settings)
        except Exception as exc:
            st.error(f"{_tr(language, '本地写入失败', 'Local write failed')}: {exc}")
        else:
            toml_str = toml.dumps(settings)
            rel = str(Path(config_path).relative_to(APP_ROOT))
            ok, msg = _save_config_github(rel, toml_str)
            if ok:
                st.success(f"{_tr(language, '设置已保存。', 'Settings saved.')} {msg}")
            else:
                st.warning(
                    f"{_tr(language, '设置已写入本地，但', 'Settings written locally, but')} {msg}"
                    f"（{_tr(language, '重部署后配置将丢失，请手动 git push', "config will be lost on redeploy — please git push manually")}）"
                )
    new_name = save_cols[1].text_input(_tr(language, "新配置名称", "New profile name"), placeholder=_tr(language, "例如：保守版", "Example: Conservative"))
    if _aligned_button(save_cols[2], _tr(language, "另存为配置文件包", "Save as profile"), use_container_width=True):
        if not new_name.strip():
            st.error(_tr(language, "请先输入新配置名称。", "Enter a new profile name first."))
        else:
            target = _profile_path_for_name(new_name)
            settings.setdefault("profile", {})["name"] = new_name.strip()
            try:
                _save_config(target, settings)
            except Exception as exc:
                st.error(f"{_tr(language, '本地写入失败', 'Local write failed')}: {exc}")
            else:
                toml_str = toml.dumps(settings)
                rel = str(target.relative_to(APP_ROOT))
                ok, msg = _save_config_github(rel, toml_str)
                if ok:
                    st.success(f"{_tr(language, '已另存为', 'Saved as')}: {target.name}。{msg}")
                else:
                    st.warning(
                        f"{_tr(language, '已另存为', 'Saved as')} {target.name}（{_tr(language, '本地', 'local')}），"
                        f"{_tr(language, '但', 'but')} {msg}"
                        f"（{_tr(language, '刷新后配置将消失，请手动 git push', 'config will disappear on refresh — please git push manually')}）"
                    )
    # --- Delete profile section ---
    deletable = {
        name: path
        for name, path in _config_options().items()
        if path != Path(DEFAULT_CONFIG) and name not in ("默认配置", "自定义路径")
        and path.resolve() != Path(config_path).resolve()
    }
    if deletable:
        st.markdown(f"**{_tr(language, '删除配置文件包', 'Delete Profile')}**")
        del_cols = st.columns([3, 1])
        del_target_name = del_cols[0].selectbox(
            _tr(language, "选择要删除的配置", "Select profile to delete"),
            list(deletable.keys()),
            key="delete_profile_select",
            label_visibility="collapsed",
        )
        if del_cols[1].button(_tr(language, "删除", "Delete"), use_container_width=True):
            st.session_state["pending_delete"] = del_target_name
        if st.session_state.get("pending_delete") == del_target_name:
            st.warning(
                f"⚠️ {_tr(language, '确认删除配置文件包', 'Confirm delete profile')}"
                f" **{del_target_name}**？{_tr(language, '此操作不可撤销。', 'This cannot be undone.')}"
            )
            confirm_cols = st.columns(2)
            if confirm_cols[0].button(_tr(language, "确认删除", "Confirm delete"), type="primary", key="confirm_delete_yes"):
                del_path = deletable[del_target_name]
                try:
                    del_path.unlink(missing_ok=True)
                except Exception as exc:
                    st.error(f"{_tr(language, '本地删除失败', 'Local delete failed')}: {exc}")
                else:
                    rel = str(del_path.relative_to(APP_ROOT))
                    ok, msg = _delete_config_github(rel)
                    st.session_state.pop("pending_delete", None)
                    if ok:
                        st.success(f"{_tr(language, '已删除', 'Deleted')}: {del_target_name}。{msg}")
                    else:
                        st.warning(
                            f"{_tr(language, '本地已删除，但', 'Deleted locally, but')} {msg}"
                            f"（{_tr(language, '请手动 git push 同步到 GitHub', 'please git push to sync to GitHub')}）"
                        )
                    st.rerun()
            if confirm_cols[1].button(_tr(language, "取消", "Cancel"), key="confirm_delete_no"):
                st.session_state.pop("pending_delete", None)
                st.rerun()

    st.json(settings, expanded=False)
    st.info(_tr(language, "保存前，当前修改只影响本次界面运行。", "Until saved, changes only affect the current app session."))
    st.markdown(f"**{_tr(language, 'GitHub 推送设置', 'GitHub Push Settings')}**")
    wf_config, wf_nz_time, wf_us_time = _read_workflow_push_config()
    push_config_options = {name: path for name, path in _config_options().items() if name != "自定义路径"}
    push_config_names = list(push_config_options.keys())
    wf_config_name = next(
        (name for name, path in push_config_options.items() if str(path.relative_to(APP_ROOT)) == wf_config),
        push_config_names[0],
    )
    push_cols = st.columns([2, 1, 1])
    push_selected_name = push_cols[0].selectbox(
        _tr(language, "推送配置", "Push config"),
        push_config_names,
        index=_option_index(push_config_names, wf_config_name),
        key="push_config_select",
    )
    push_nz_time = push_cols[1].text_input(
        _tr(language, "NZ 推送时间", "NZ push time"),
        value=wf_nz_time,
        placeholder="15:45",
        key="push_nz_time",
    )
    push_us_time = push_cols[2].text_input(
        _tr(language, "US 推送时间", "US push time"),
        value=wf_us_time,
        placeholder="15:00",
        key="push_us_time",
    )
    st.caption(_tr(language, "时间格式 HH:MM（本地时间）。NZ 时间对应 Pacific/Auckland，US 时间对应 America/New_York。", "Format HH:MM (local time). NZ uses Pacific/Auckland, US uses America/New_York."))
    push_action_cols = st.columns([1, 1, 2])
    if push_action_cols[0].button(_tr(language, "保存推送设置", "Save push settings"), type="primary", use_container_width=True):
        selected_path = push_config_options[push_selected_name]
        rel = str(selected_path.relative_to(APP_ROOT)) if push_selected_name != "默认配置" else _DEFAULT_PUSH_CONFIG
        ok, msg = _update_workflow_github(rel, push_nz_time.strip(), push_us_time.strip())
        if ok:
            st.success(f"{_tr(language, '推送设置已保存。', 'Push settings saved.')} {msg}")
        else:
            st.error(f"{_tr(language, '保存失败', 'Save failed')}: {msg}")
    if push_action_cols[1].button(_tr(language, "恢复默认配置", "Restore defaults"), use_container_width=True):
        ok, msg = _update_workflow_github(_DEFAULT_PUSH_CONFIG, _DEFAULT_NZ_TIME, _DEFAULT_US_TIME)
        if ok:
            st.success(f"{_tr(language, '已恢复为默认配置。', 'Restored to default config.')} {msg}")
        else:
            st.error(f"{_tr(language, '恢复失败', 'Restore failed')}: {msg}")
    st.markdown(f"**{_tr(language, '系统版本', 'System Version')}**")
    st.metric(_tr(language, "当前版本", "Current version"), f"v{__version__}")
    _render_release_notes(language)


def _render_release_notes(language: str) -> None:
    st.markdown(f"**{_tr(language, '更新与修复日志', 'Update and Fix Log')}**")
    changelog = _release_notes_text(language)
    escaped = html.escape(changelog)
    st.markdown(
        f"""
<div style="height: 320px; overflow-y: auto; border: 1px solid #d9dde3; border-radius: 6px; padding: 12px; background: transparent; white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace; font-size: 13px; line-height: 1.45;">
{escaped}
</div>
""",
        unsafe_allow_html=True,
    )
    st.caption(f"{_tr(language, '日志文件', 'Log file')}: {_release_notes_path(language).resolve()}")


def _release_notes_text(language: str = "zh") -> str:
    path = _release_notes_path(language)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "CHANGELOG.md not found."


def _release_notes_path(language: str = "zh") -> Path:
    return CHANGELOG_EN_PATH if language == "en" and CHANGELOG_EN_PATH.exists() else CHANGELOG_PATH


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
        st.markdown(f"**{_tr(language, '全区间参数调整建议', 'Full-Range Parameter Recommendations')}**")
        st.dataframe(_localized_recommendations(recommendations, language), use_container_width=True, hide_index=True)
        st.markdown(f"**{_tr(language, '最适合的参数范围', 'Preferred Parameter Ranges')}**")
        st.dataframe(_localized_parameter_frame(ranges, language), use_container_width=True, hide_index=True)
        st.markdown(f"**{_tr(language, '逐个测试最佳结果', 'Best Individual Tests')}**")
        st.dataframe(_localized_parameter_frame(individual.head(25), language), use_container_width=True, hide_index=True)
        st.markdown(f"**{_tr(language, '统一测试结果', 'Unified Test Results')}**")
        st.dataframe(_localized_parameter_frame(unified, language), use_container_width=True, hide_index=True)
        st.markdown(f"**{_tr(language, '全区间对比净值曲线', 'Full-Range Comparison Equity Curves')}**")
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
        st.markdown(f"**{_tr(language, '目标日期参数建议表', 'Target-Date Parameter Recommendations')}**")
        st.caption(
            _tr(
                language,
                f"目标日期：{stored['target_date']}；时间窗口：{stored['window_start']} ~ {stored['window_end']}；排序目标：{stored['sort_label']}",
                f"Target date: {stored['target_date']}; window: {stored['window_start']} to {stored['window_end']}; objective: {stored['sort_label']}",
            )
        )
        st.dataframe(_localized_recommendations(target_recommendations, language), use_container_width=True, hide_index=True)
        st.markdown(f"**{_tr(language, '目标日期窗口最适合的参数范围', 'Target Window Preferred Parameter Ranges')}**")
        st.dataframe(_localized_parameter_frame(target_ranges, language), use_container_width=True, hide_index=True)
        st.markdown(f"**{_tr(language, '目标日期窗口对比净值曲线', 'Target Window Comparison Equity Curves')}**")
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
        _tr(language, "下一交易日", "Next session"): "next_session",
        _tr(language, "NZ 盘末 / 美股开盘", "NZ close / US open"): "nz_close_us_open",
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
    """Push a config file to GitHub via REST API. Returns (success, message)."""
    import base64
    import json
    import urllib.error
    import urllib.request

    try:
        token = st.secrets.get("GITHUB_TOKEN", "")
        repo = st.secrets.get("GITHUB_REPO", "")
        branch = st.secrets.get("GITHUB_BRANCH", "main")
        if not token or not repo:
            return False, "未配置 GITHUB_TOKEN / GITHUB_REPO secrets"
        api_url = f"https://api.github.com/repos/{repo}/contents/{relative_path}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        }
        # GET current file SHA (required for updates)
        req = urllib.request.Request(api_url, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                current = json.loads(resp.read())
            sha = current.get("sha", "")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                sha = ""
            else:
                raise
        # PUT new content
        body: dict[str, Any] = {
            "message": f"chore: update {relative_path} via Streamlit UI",
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if sha:
            body["sha"] = sha
        put_req = urllib.request.Request(
            api_url, data=json.dumps(body).encode(), headers=headers, method="PUT"
        )
        with urllib.request.urlopen(put_req):
            pass
        return True, "已推送到 GitHub"
    except Exception as exc:
        return False, f"GitHub 推送失败: {exc}"


def _delete_config_github(relative_path: str) -> tuple[bool, str]:
    """Delete a config file from GitHub via REST API. Returns (success, message)."""
    import json
    import urllib.error
    import urllib.request

    try:
        token = st.secrets.get("GITHUB_TOKEN", "")
        repo = st.secrets.get("GITHUB_REPO", "")
        branch = st.secrets.get("GITHUB_BRANCH", "main")
        if not token or not repo:
            return False, "未配置 GITHUB_TOKEN / GITHUB_REPO secrets"
        api_url = f"https://api.github.com/repos/{repo}/contents/{relative_path}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        }
        # GET current file SHA (required for deletion)
        req = urllib.request.Request(api_url, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                current = json.loads(resp.read())
            sha = current.get("sha", "")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return True, "GitHub 上不存在该文件（已跳过）"
            raise
        body: dict[str, Any] = {
            "message": f"chore: delete {relative_path} via Streamlit UI",
            "sha": sha,
            "branch": branch,
        }
        del_req = urllib.request.Request(
            api_url, data=json.dumps(body).encode(), headers=headers, method="DELETE"
        )
        with urllib.request.urlopen(del_req):
            pass
        return True, "已从 GitHub 删除"
    except Exception as exc:
        return False, f"GitHub 删除失败: {exc}"


_WORKFLOW_PATH = ".github/workflows/daily-signal.yml"
_DEFAULT_PUSH_CONFIG = "config/settings.toml"
_DEFAULT_NZ_TIME = "15:45"
_DEFAULT_US_TIME = "15:00"


def _read_workflow_push_config() -> tuple[str, str, str]:
    """Read current push config/times from the GitHub Actions workflow via API.
    Returns (config_rel_path, nz_time, us_time). Falls back to defaults on error."""
    import base64
    import json
    import re
    import urllib.request

    try:
        token = st.secrets.get("GITHUB_TOKEN", "")
        repo = st.secrets.get("GITHUB_REPO", "")
        branch = st.secrets.get("GITHUB_BRANCH", "main")
        if not token or not repo:
            return _DEFAULT_PUSH_CONFIG, _DEFAULT_NZ_TIME, _DEFAULT_US_TIME
        api_url = f"https://api.github.com/repos/{repo}/contents/{_WORKFLOW_PATH}?ref={branch}"
        req = urllib.request.Request(api_url, headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        content = base64.b64decode(data["content"]).decode()
        nz = re.search(r'"\\$nz_time"\s*==\s*"(\d{2}:\d{2})"', content)
        us = re.search(r'"\\$ny_time"\s*==\s*"(\d{2}:\d{2})"', content)
        cfg = re.search(r'--config\s+(config/\S+\.toml)', content)
        return (
            cfg.group(1) if cfg else _DEFAULT_PUSH_CONFIG,
            nz.group(1) if nz else _DEFAULT_NZ_TIME,
            us.group(1) if us else _DEFAULT_US_TIME,
        )
    except Exception:
        return _DEFAULT_PUSH_CONFIG, _DEFAULT_NZ_TIME, _DEFAULT_US_TIME


def _update_workflow_github(config_rel: str, nz_time: str, us_time: str) -> tuple[bool, str]:
    """Update push config/times in the GitHub Actions workflow via REST API."""
    import base64
    import json
    import re
    import urllib.error
    import urllib.request

    try:
        token = st.secrets.get("GITHUB_TOKEN", "")
        repo = st.secrets.get("GITHUB_REPO", "")
        branch = st.secrets.get("GITHUB_BRANCH", "main")
        if not token or not repo:
            return False, "未配置 GITHUB_TOKEN / GITHUB_REPO secrets"
        api_url = f"https://api.github.com/repos/{repo}/contents/{_WORKFLOW_PATH}"
        headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json", "Content-Type": "application/json"}
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        content = base64.b64decode(data["content"]).decode()
        sha = data["sha"]
        content = re.sub(r'"(\$nz_time)"\s*==\s*"\d{2}:\d{2}"', f'"$nz_time" == "{nz_time}"', content)
        content = re.sub(r'"(\$ny_time)"\s*==\s*"\d{2}:\d{2}"', f'"$ny_time" == "{us_time}"', content)
        content = re.sub(r'--config\s+config/\S+\.toml', f'--config {config_rel}', content)
        body: dict[str, Any] = {
            "message": f"chore: update push config to {config_rel} ({nz_time} NZ / {us_time} US) via Streamlit UI",
            "content": base64.b64encode(content.encode()).decode(),
            "sha": sha,
            "branch": branch,
        }
        put_req = urllib.request.Request(api_url, data=json.dumps(body).encode(), headers=headers, method="PUT")
        with urllib.request.urlopen(put_req):
            pass
        return True, "Workflow 已更新并推送到 GitHub"
    except Exception as exc:
        return False, f"Workflow 更新失败: {exc}"


def _market_windows(settings: dict[str, Any], timeline_mode: str | None = None) -> None:
    language = _ui_language(settings)
    st.subheader(_tr(language, "新西兰本地交易窗口", "Local Trading Windows"))
    now = pd.Timestamp.now(tz=settings["profile"]["home_timezone"]).to_pydatetime()
    us_open, us_close = _relevant_local_window(settings, "us", now)
    asx_open, asx_close = _relevant_local_window(settings, "asx", now)
    nzx_open, nzx_close = _relevant_local_window(settings, "nzx", now)
    market_windows = [
        {"key": "nzx", "label": "NZ", "open": nzx_open, "close": nzx_close, "color": "#991b1b"},
        {"key": "asx", "label": "AU", "open": asx_open, "close": asx_close, "color": "#14532d"},
        {"key": "us", "label": "US", "open": us_open, "close": us_close, "color": "#2563eb"},
    ]
    selected_timeline_mode = timeline_mode or settings.get("backtest", {}).get("execution_timing", "next_session")
    if selected_timeline_mode not in {"next_session", "nz_close_us_open"}:
        selected_timeline_mode = "next_session"
    trade_items = [
        item
        for item in trade_timeline_items(settings, now)
        if item.strategy_key == selected_timeline_mode
    ]
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
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 14px 14px 10px;
  margin: 10px 0 12px;
  background: transparent;
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
  border-radius: 6px;
  background: rgba(128, 128, 128, 0.2);
  overflow: visible;
}}
.trade-timeline-segment {{
  position: absolute;
  top: 0;
  bottom: 0;
  border-radius: 5px;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.42);
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
  border-radius: 5px;
  opacity: .2;
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
  background: rgba(128, 128, 128, 0.2);
  border-radius: 6px;
  color: inherit;
  font-size: 12px;
  line-height: 1.35;
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
  gap: 10px;
  margin: 10px 0 2px;
}}
.timeline-countdown-card {{
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px 12px;
  background: transparent;
  color: inherit;
}}
.timeline-countdown-card.urgent {{
  border-color: #dc2626;
  background: #dc2626;
  color: #ffffff;
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
    padding: 12px 10px 10px;
  }}
  .trade-timeline-head {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 2px;
    font-size: 12px;
  }}
  .trade-timeline-head span:nth-child(2) {{
    order: -1;
    color: #111827;
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
    return now, now + timedelta(hours=24)


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
    if item.strategy_key == "next_session":
        return "#059669"
    if item.market_label == "NZX":
        return "#991b1b"
    if "open" in action_en:
        return "#93c5fd"
    if "close" in action_en:
        return "#2563eb"
    return "#dc2626"


def _short_trade_action(item: Any, language: str) -> str:
    action_en = item.action("en").lower()
    if item.strategy_key == "next_session":
        return _tr(language, "下一交易日：开盘前调仓", "Next session: rebalance before open")
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
    countdowns: list[tuple[str, datetime, str]] = []

    market_event_candidates: list[tuple[str, datetime, str]] = []
    for window in market_windows:
        if window["open"] <= now <= window["close"]:
            close_dt = window["close"]
            market_event_candidates.append((
                _tr(language, f"当前市场 {window['label']} 收盘", f"Current market {window['label']} close"),
                close_dt,
                close_dt.strftime("%Y-%m-%d %H:%M"),
            ))
        elif window["open"] > now:
            open_dt = window["open"]
            market_event_candidates.append((
                _tr(language, f"下个市场 {window['label']} 开盘", f"Next market {window['label']} open"),
                open_dt,
                open_dt.strftime("%Y-%m-%d %H:%M"),
            ))
    if market_event_candidates:
        countdowns.append(min(market_event_candidates, key=lambda x: x[1]))

    future_trade_items = sorted(
        (item for item in trade_items if item.deadline >= now),
        key=lambda item: item.deadline,
    )
    if future_trade_items:
        item = future_trade_items[0]
        countdowns.append((
            _tr(language, f"当前模式操作时间 · {item.market_label}", f"Current mode action · {item.market_label}"),
            item.deadline,
            f"{item.deadline:%Y-%m-%d %H:%M} · {_short_trade_action(item, language)}",
        ))

    cards = "\n".join(
        _countdown_card_html(title, target, meta, now, language)
        for title, target, meta in countdowns
    )
    if cards:
        st.markdown(f'<div class="timeline-countdown-grid">{cards}</div>', unsafe_allow_html=True)


def _countdown_card_html(title: str, target: datetime, meta: str, now: datetime, language: str) -> str:
    remaining = target - now
    urgent = timedelta(0) <= remaining <= timedelta(hours=3)
    class_name = "timeline-countdown-card urgent" if urgent else "timeline-countdown-card"
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
    return options.index(value) if value in options else 0


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
                _tr(language, "目标比例", "Target weight"): f"{target_percent:.2f}%",
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
    chart_data = (
        frame.reset_index()[["date", *columns]]
        .melt(id_vars="date", var_name="series", value_name="value")
        .dropna()
    )
    chart_data["line_style"] = chart_data["series"].map(line_styles or {}).fillna("solid")
    chart_data["series_label"] = chart_data["series"].apply(lambda series: _series_label(series, language))
    chart = (
        alt.Chart(chart_data)
        .mark_line(strokeCap="round")
        .encode(
            x=alt.X("date:T", title=_tr(language, "日期", "Date")),
            y=alt.Y("value:Q", title=title),
            color=alt.Color("series_label:N", title=_tr(language, "曲线", "Series")),
            strokeDash=alt.StrokeDash(
                "line_style:N",
                scale=alt.Scale(
                    domain=["solid", "dashed", "dotted"],
                    range=[[], [8, 5], [1, 5]],
                ),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("date:T", title=_tr(language, "日期", "Date")),
                alt.Tooltip("series_label:N", title=_tr(language, "曲线", "Series")),
                alt.Tooltip("value:Q", title=_tr(language, "数值", "Value"), format=",.2f"),
            ],
        )
        .properties(height=360)
        .interactive()
    )
    st.altair_chart(chart, use_container_width=True, key=key)


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
            f"{_tr(language, '目标', 'Target')} {float(trade.get('target_exposure', 0)):.0f}% | "
            f"{_tr(language, '核心', 'Core')} {float(trade.get('core_percent', 0)):.1f}% | "
            f"{_tr(language, '杠杆', 'Leverage')} {float(trade.get('leveraged_percent', 0)):.1f}% | "
            f"{_tr(language, '防御', 'Defensive')} {float(trade.get('local_defensive_percent', 0)):.1f}%"
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
    payload = toml.dumps({"settings": _model_settings(settings), "extras": extras})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_stale(session_key: str, settings: dict[str, Any], extras: dict[str, str]) -> bool:
    saved = st.session_state.get(session_key)
    return bool(saved and saved != _fingerprint(settings, extras))


def _model_settings(settings: dict[str, Any]) -> dict[str, Any]:
    model_settings = deepcopy(settings)
    model_settings.get("backtest", {}).pop("show_leveraged_buy_hold", None)
    model_settings.get("backtest", {}).pop("show_ma120_timing", None)
    model_settings.get("backtest", {}).pop("show_leveraged_ma120_timing", None)
    return model_settings


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
