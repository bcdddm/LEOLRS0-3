from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

import pandas as pd
import streamlit as st

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
    cols = st.columns([1, 1, 1, 1, 1])
    start = cols[0].date_input(tr(language, "数据起始日期", "Data start date"), value=date.today(), key="daily_start")
    run = deps.aligned_button(cols[1], tr(language, "更新今日信号", "Update daily signal"), type="primary", use_container_width=True)
    timeline_mode_labels = deps.daily_timeline_mode_labels(language)
    nz_label = tr(language, "NZ 盘末 / 美股开盘", "NZ close / US open")
    if "daily_timeline_mode" not in st.session_state:
        st.session_state["daily_timeline_mode"] = nz_label
    selected_timeline_mode_label = cols[2].selectbox(
        tr(language, "交易时间轴模式", "Timeline mode"),
        list(timeline_mode_labels.keys()),
        key="daily_timeline_mode",
    )
    timeline_mode = timeline_mode_labels[selected_timeline_mode_label]
    settings.setdefault("backtest", {})["execution_timing"] = timeline_mode

    if not run and "daily_result" not in st.session_state:
        deps.disabled_pdf_button(language, tr(language, "打印/下载今日信号 PDF", "Print/Download Daily Signal PDF"), key="daily_pdf_disabled")
        st.info(tr(language, "今日信号尚未加载。", "Daily signal has not been loaded yet."))
        deps.market_windows(settings, timeline_mode)
        return

    if run:
        with st.spinner(tr(language, "正在下载 Yahoo Finance 数据...", "Downloading Yahoo Finance data...")):
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
                st.error(
                    f"{tr(language, '信号计算失败，数据不足，请尝试将数据起始日期调早。', 'Signal calculation failed — not enough data. Try moving the data start date further back.')}"
                    f"\n\n`{exc}`"
                )
                st.session_state.pop("daily_result", None)
                return
            prices = deps.cached_prices(symbols, str(start), None, True)
            st.session_state["daily_result"] = (result.signal, result.allocation)
            st.session_state["daily_prices"] = prices
            st.session_state["daily_fingerprint"] = deps.fingerprint(settings, {"start": str(start)})

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
    deps.pdf_download_button(
        language,
        tr(language, "打印/下载今日信号 PDF", "Print/Download Daily Signal PDF"),
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
    st.subheader(tr(language, "市场状态", "Market State"))
    metric_cols = st.columns(5)
    metric_cols[0].metric(tr(language, "SPY 收盘价", "SPY close"), f"{signal.price:,.2f}")
    metric_cols[1].metric(tr(language, "趋势", "Trend"), deps.state_label(signal.trend_label, language), f"{signal.trend_exposure:,.0f}%")
    metric_cols[2].metric("VIX", f"{signal.vix:.2f}", deps.state_label(signal.vix_label, language))
    metric_cols[3].metric(tr(language, "VIX 系数", "VIX multiplier"), f"x{signal.vix_multiplier:.2f}")
    metric_cols[4].metric(tr(language, "目标等效仓位", "Target equivalent exposure"), f"{signal.target_exposure:,.0f}%")
    if settings.get("position", {}).get("trend_quality_ma_cross_slow_decline_enabled", False) and signal.trend_quality_slow_decline:
        st.warning(
            tr(
                language,
                f"趋势质量警告：120 日均线（{signal.trend_quality_ma_120:,.2f}）低于 200 日均线（{signal.trend_quality_ma_200:,.2f}），系统判定当前处于（阴跌）状态。",
                f"Trend quality warning: the 120-day MA ({signal.trend_quality_ma_120:,.2f}) is below the 200-day MA ({signal.trend_quality_ma_200:,.2f}), so the system treats the market as being in slow-decline state.",
            )
        )

    st.subheader(tr(language, "执行仓位", "Execution Allocation"))
    alloc_cols = st.columns(4)
    alloc_cols[0].metric(allocation.core_asset, f"{allocation.core_percent:,.2f}%")
    alloc_cols[1].metric(allocation.leveraged_asset or tr(language, "无杠杆", "No leverage"), f"{allocation.leveraged_percent:,.2f}%")
    alloc_cols[2].metric(allocation.defensive_asset, f"{allocation.defensive_percent:,.2f}%")
    alloc_cols[3].metric(tr(language, "等效仓位", "Equivalent exposure"), f"{allocation.equivalent_exposure:,.2f}%")
    if allocation.notes:
        st.warning("\n".join(allocation.notes))

    ma_frame = pd.DataFrame(
        {
            tr(language, "数值", "Value"): {
                ma_short_label: signal.ma_short,
                ma_medium_label: signal.ma_medium,
                ma_long_label: signal.ma_long,
            }
        }
    )
    st.bar_chart(ma_frame)
    deps.portfolio_adjustment_section(settings, allocation, st.session_state.get("daily_prices", {}), signal.date)
    deps.market_windows(settings, timeline_mode)
