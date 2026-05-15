from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable

import pandas as pd
import streamlit as st

from trend_system.interfaces.streamlit.shared.preparing import render_preparing
from trend_system.models import DailySignalRequest
from trend_system.services.daily_signal_service import run_daily_signal


@dataclass(frozen=True)
class DailyPageDeps:
    as_settings: Callable[[dict[str, Any]], Any]
    cached_prices: Callable[[tuple[str, ...], str, str | None, bool], dict[str, pd.DataFrame]]
    tr: Callable[[str, str, str], str]
    aligned_button: Callable[..., bool]
    disabled_pdf_button: Callable[..., None]
    pdf_download_button: Callable[..., None]
    build_pdf_report: Callable[..., bytes]
    strategy_summary_rows: Callable[[dict[str, Any], str], list[tuple[str, str]]]
    pdf_filename: Callable[[str, dict[str, Any]], str]
    state_label: Callable[[str, str], str]
    trend_ma_labels: Callable[[dict[str, Any]], tuple[str, str, str]]
    daily_timeline_mode_labels: Callable[[str], dict[str, str]]
    market_windows: Callable[[dict[str, Any], str | None], None]
    portfolio_adjustment_section: Callable[..., None]
    fingerprint: Callable[[dict[str, Any], dict[str, str]], str]
    is_stale: Callable[[str, dict[str, Any], dict[str, str]], bool]
    required_symbols_from_raw: Callable[[dict[str, Any]], list[str]]


def render_daily_page(
    settings: dict[str, Any],
    language: str,
    *,
    deps: DailyPageDeps,
) -> None:
    tr = deps.tr
    # Zone A — command bar
    ctrl_cols = st.columns([2, 1.2, 2, 0.8])
    start = ctrl_cols[0].date_input(
        tr(language, "数据起始日期", "Data start date"),
        value=date.today() - timedelta(days=420),
        key="daily_start",
    )
    run = deps.aligned_button(ctrl_cols[1], tr(language, "更新今日信号", "Update daily signal"), type="primary", use_container_width=True)
    timeline_mode_labels = deps.daily_timeline_mode_labels(language)
    nz_label = tr(language, "NZ 盘末 / 美股开盘", "NZ close / US open")
    if "daily_timeline_mode" not in st.session_state:
        st.session_state["daily_timeline_mode"] = nz_label
    selected_timeline_mode_label = ctrl_cols[2].selectbox(
        tr(language, "交易时间轴模式", "Timeline mode"),
        list(timeline_mode_labels.keys()),
        key="daily_timeline_mode",
    )
    timeline_mode = timeline_mode_labels[selected_timeline_mode_label]
    settings.setdefault("backtest", {})["execution_timing"] = timeline_mode

    should_prepare = run or "daily_result" not in st.session_state
    if should_prepare:
        preparing = st.empty()
        render_preparing(
            preparing,
            language,
            title=tr(language, "准备中", "Preparing"),
            detail=tr(language, "正在收集市场数据并整理今日信号。", "Collecting market data and preparing today's signal."),
        )
        symbols = tuple(deps.required_symbols_from_raw(settings))
        price_loader = lambda symbol_list, start, end=None, auto_adjust=True: deps.cached_prices(
            tuple(symbol_list),
            str(start),
            end,
            auto_adjust,
        )
        try:
            result = run_daily_signal(
                DailySignalRequest(settings=deps.as_settings(settings), start=start),
                price_loader=price_loader,
            )
        except RuntimeError as exc:
            preparing.empty()
            st.error(
                f"{tr(language, '信号计算失败，数据不足，请尝试将数据起始日期调早。', 'Signal calculation failed — not enough data. Try moving the data start date further back.')}"
                f"\n\n`{exc}`"
            )
            st.session_state.pop("daily_result", None)
            deps.market_windows(settings, timeline_mode)
            return
        prices = deps.cached_prices(symbols, str(start), None, True)
        st.session_state["daily_result"] = (result.signal, result.allocation)
        st.session_state["daily_prices"] = prices
        st.session_state["daily_fingerprint"] = deps.fingerprint(settings, {"start": str(start)})
        preparing.empty()

    if deps.is_stale("daily_fingerprint", settings, {"start": str(start)}):
        st.warning(tr(language, "数据已更改，请重新回测并刷新数据。", "Settings changed. Please refresh the data."))

    signal, allocation = st.session_state["daily_result"]
    ma_short_label, ma_medium_label, ma_long_label = deps.trend_ma_labels(settings)
    ma_summary_label = f"{ma_short_label} / {ma_medium_label} / {ma_long_label}"
    daily_rows = [
        (tr(language, "信号日期", "Signal date"), str(signal.date.date())),
        (tr(language, "核心价格", "Core price"), f"{signal.price:,.2f}"),
        (ma_summary_label, f"{signal.ma_short:,.2f} / {signal.ma_medium:,.2f} / {signal.ma_long:,.2f}"),
        (tr(language, "趋势", "Trend"), f"{deps.state_label(signal.trend_label, language)} ({signal.trend_exposure:,.0f}%)"),
        ("VIX", f"{signal.vix:.2f} ({deps.state_label(signal.vix_label, language)})"),
        (tr(language, "VIX 系数", "VIX multiplier"), f"x{signal.vix_multiplier:.2f}"),
        (tr(language, "目标等效仓位", "Target equivalent exposure"), f"{signal.target_exposure:,.0f}%"),
        (allocation.core_asset, f"{allocation.core_percent:,.2f}%"),
        (allocation.leveraged_asset or tr(language, "无杠杆", "No leverage"), f"{allocation.leveraged_percent:,.2f}%"),
        (allocation.defensive_asset, f"{allocation.defensive_percent:,.2f}%"),
    ]
    # Zone A — PDF button (right slot of command bar)
    with ctrl_cols[3]:
        deps.pdf_download_button(
            language,
            "PDF",
            deps.build_pdf_report(
                tr(language, "今日信号", "Daily Signal"),
                settings,
                language,
                sections=[
                    (tr(language, "市场状态", "Market State"), daily_rows),
                    (tr(language, "策略信息", "Strategy Information"), deps.strategy_summary_rows(settings, language)),
                ],
                notes=allocation.notes,
            ),
            deps.pdf_filename("daily-signal", settings),
            key="daily_pdf_download",
        )

    # Zone B — Market State (full-width, 4 per row)
    st.markdown(
        f'<div class="leo-section-head leo-section-head--prussian">'
        f'<span class="leo-section-dot"></span>'
        f'<span class="leo-section-overline">{tr(language, "市场状态", "Market State")}</span>'
        f'<span class="leo-section-rule"></span></div>',
        unsafe_allow_html=True,
    )
    sig_r1 = st.columns(4)
    sig_r1[0].metric(tr(language, "SPY 收盘价", "SPY close"), f"{signal.price:,.2f}")
    sig_r1[1].metric(tr(language, "趋势", "Trend"), deps.state_label(signal.trend_label, language), f"{signal.trend_exposure:,.0f}%")
    sig_r1[2].metric("VIX", f"{signal.vix:.2f}", deps.state_label(signal.vix_label, language))
    sig_r1[3].metric(tr(language, "VIX 系数", "VIX multiplier"), f"x{signal.vix_multiplier:.2f}")
    sig_r2 = st.columns(4)
    sig_r2[0].metric(tr(language, "目标等效仓位", "Target exposure"), f"{signal.target_exposure:,.0f}%")
    sig_r2[1].metric(ma_short_label, f"{signal.ma_short:,.2f}")
    sig_r2[2].metric(ma_medium_label, f"{signal.ma_medium:,.2f}")
    sig_r2[3].metric(ma_long_label, f"{signal.ma_long:,.2f}")
    if settings.get("position", {}).get("trend_quality_ma_cross_slow_decline_enabled", False) and signal.trend_quality_slow_decline:
        st.warning(
            tr(
                language,
                f"趋势质量警告：120 日均线（{signal.trend_quality_ma_120:,.2f}）低于 200 日均线（{signal.trend_quality_ma_200:,.2f}），系统判定当前处于（阴跌）状态。",
                f"Trend quality warning: the 120-day MA ({signal.trend_quality_ma_120:,.2f}) is below the 200-day MA ({signal.trend_quality_ma_200:,.2f}), so the system treats the market as being in slow-decline state.",
            )
        )

    # Zone C — Execution Allocation (full-width, 4 per row)
    st.markdown(
        f'<div class="leo-section-head leo-section-head--green">'
        f'<span class="leo-section-dot"></span>'
        f'<span class="leo-section-overline">{tr(language, "执行仓位", "Execution Allocation")}</span>'
        f'<span class="leo-section-rule"></span></div>',
        unsafe_allow_html=True,
    )
    alloc_row = st.columns(4)
    alloc_row[0].metric(allocation.core_asset, f"{allocation.core_percent:,.2f}%")
    alloc_row[1].metric(allocation.leveraged_asset or tr(language, "无杠杆", "No leverage"), f"{allocation.leveraged_percent:,.2f}%")
    alloc_row[2].metric(allocation.defensive_asset, f"{allocation.defensive_percent:,.2f}%")
    alloc_row[3].metric(tr(language, "等效仓位", "Equivalent exposure"), f"{allocation.equivalent_exposure:,.2f}%")
    if allocation.notes:
        st.warning("\n".join(allocation.notes))

    # Zone D — market windows (full-width, unchanged)
    deps.market_windows(settings, timeline_mode)

    # Zone E — portfolio adjustment (collapsed by default)
    with st.expander(tr(language, "组合调整", "Portfolio Adjustment"), expanded=False):
        deps.portfolio_adjustment_section(settings, allocation, st.session_state.get("daily_prices", {}), signal.date)
