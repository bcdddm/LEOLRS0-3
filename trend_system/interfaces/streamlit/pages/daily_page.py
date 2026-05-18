from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd
import streamlit as st

from trend_system.interfaces.streamlit.shared.preparing import render_preparing
from trend_system.interfaces.streamlit.shared.state import sync_date_input_default
from trend_system.models import DailySignalRequest, DailySignalResult
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


def _render_control_label(container: Any, label: str) -> None:
    container.markdown(
        f"""
<div style="
  font-size: 0.88rem;
  font-weight: 500;
  line-height: 1.25;
  color: var(--text-color);
  margin: 0 0 0.28rem;
  min-height: 1.35rem;
  display: flex;
  align-items: flex-end;
">
  {label}
</div>
""",
        unsafe_allow_html=True,
    )

def _delta_text(
    language: str,
    current: float,
    previous: float | None,
    *,
    decimals: int = 2,
    prefix: str = "",
    suffix: str = "",
) -> str:
    if previous is None:
        return ""
    change = current - previous
    return (
        f"{'较昨' if language == 'zh' else 'vs prev'} "
        f"{prefix}{change:+,.{decimals}f}{suffix}"
    )


def _state_delta_text(
    language: str,
    current_label: str,
    previous_label: str | None,
    current_detail: str,
    previous_detail: str | None,
) -> str:
    if previous_label is None:
        return ""
    previous_text = previous_label
    if previous_detail:
        previous_text = f"{previous_text} | {previous_detail}"
    if current_label == previous_label and current_detail == (previous_detail or ""):
        return "和昨天相同" if language == "zh" else "Same as previous day"
    return f"{'昨' if language == 'zh' else 'Prev'}: {previous_text}"


def _render_plain_metric(
    container: Any,
    label: str,
    value: str,
    delta: str = "",
) -> None:
    container.metric(label, value, delta=delta, delta_color="off")


def _coerce_daily_result(raw_result: Any) -> tuple[Any, Any, Any | None, Any | None]:
    if isinstance(raw_result, DailySignalResult):
        return (
            raw_result.signal,
            raw_result.allocation,
            raw_result.previous_signal,
            raw_result.previous_allocation,
        )
    signal, allocation = raw_result
    return signal, allocation, None, None


def render_daily_page(
    settings: dict[str, Any],
    language: str,
    *,
    deps: DailyPageDeps,
) -> None:
    tr = deps.tr
    home_tz = settings.get("profile", {}).get("home_timezone", "Pacific/Auckland")
    default_start = sync_date_input_default(
        "daily_start",
        "daily_date_anchor",
        tz_name=home_tz,
    )
    # Zone A — command bar
    ctrl_cols = st.columns(4, vertical_alignment="bottom")
    start = ctrl_cols[0].date_input(
        tr(language, "数据起始日期", "Data start date"),
        value=default_start,
        key="daily_start",
    )
    _render_control_label(ctrl_cols[1], tr(language, "更新", "Update"))
    run = ctrl_cols[1].button(
        tr(language, "更新今日信号", "Update daily signal"),
        type="primary",
        use_container_width=True,
    )
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
        st.session_state["daily_result"] = result
        st.session_state["daily_prices"] = prices
        st.session_state["daily_fingerprint"] = deps.fingerprint(settings, {"start": str(start)})
        preparing.empty()

    if deps.is_stale("daily_fingerprint", settings, {"start": str(start)}):
        st.warning(tr(language, "数据已更改，请重新回测并刷新数据。", "Settings changed. Please refresh the data."))

    signal, allocation, previous_signal, previous_allocation = _coerce_daily_result(
        st.session_state["daily_result"]
    )
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
        _render_control_label(st, "PDF")
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
        f'<div class="leo-section-head leo-section-head--green">'
        f'<span class="leo-section-dot"></span>'
        f'<span class="leo-section-overline">{tr(language, "市场状态", "Market State")}</span>'
        f'<span class="leo-section-rule"></span></div>',
        unsafe_allow_html=True,
    )
    sig_r1 = st.columns(4)
    _render_plain_metric(
        sig_r1[1],
        tr(language, "趋势", "Trend"),
        f"{deps.state_label(signal.trend_label, language)} | {signal.trend_exposure:,.0f}%",
        _state_delta_text(
            language,
            signal.trend_label,
            previous_signal.trend_label if previous_signal is not None else None,
            f"{signal.trend_exposure:,.0f}%",
            f"{previous_signal.trend_exposure:,.0f}%" if previous_signal is not None else None,
        ),
    )
    _render_plain_metric(
        sig_r1[2],
        "VIX",
        f"{signal.vix:.2f} | {deps.state_label(signal.vix_label, language)}",
        _state_delta_text(
            language,
            signal.vix_label,
            previous_signal.vix_label if previous_signal is not None else None,
            f"{signal.vix:,.2f}",
            f"{previous_signal.vix:,.2f}" if previous_signal is not None else None,
        ),
    )
    _render_plain_metric(
        sig_r1[0],
        tr(language, "SPY 收盘价", "SPY close"),
        f"{signal.price:,.2f}",
        _delta_text(language, signal.price, previous_signal.price if previous_signal is not None else None),
    )
    _render_plain_metric(
        sig_r1[3],
        tr(language, "VIX 系数", "VIX multiplier"),
        f"x{signal.vix_multiplier:.2f}",
        _delta_text(
            language,
            signal.vix_multiplier,
            previous_signal.vix_multiplier if previous_signal is not None else None,
            decimals=2,
            prefix="x",
        ),
    )
    sig_r2 = st.columns(4)
    _render_plain_metric(
        sig_r2[0],
        tr(language, "目标等效仓位", "Target exposure"),
        f"{signal.target_exposure:,.0f}%",
        _delta_text(
            language,
            signal.target_exposure,
            previous_signal.target_exposure if previous_signal is not None else None,
            decimals=0,
            suffix="%",
        ),
    )
    _render_plain_metric(
        sig_r2[1],
        ma_short_label,
        f"{signal.ma_short:,.2f}",
        _delta_text(language, signal.ma_short, previous_signal.ma_short if previous_signal is not None else None),
    )
    _render_plain_metric(
        sig_r2[2],
        ma_medium_label,
        f"{signal.ma_medium:,.2f}",
        _delta_text(language, signal.ma_medium, previous_signal.ma_medium if previous_signal is not None else None),
    )
    _render_plain_metric(
        sig_r2[3],
        ma_long_label,
        f"{signal.ma_long:,.2f}",
        _delta_text(language, signal.ma_long, previous_signal.ma_long if previous_signal is not None else None),
    )
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
    _render_plain_metric(
        alloc_row[0],
        allocation.core_asset,
        f"{allocation.core_percent:,.2f}%",
        _delta_text(
            language,
            allocation.core_percent,
            previous_allocation.core_percent if previous_allocation is not None else None,
            suffix="%",
        ),
    )
    _render_plain_metric(
        alloc_row[1],
        allocation.leveraged_asset or tr(language, "无杠杆", "No leverage"),
        f"{allocation.leveraged_percent:,.2f}%",
        _delta_text(
            language,
            allocation.leveraged_percent,
            previous_allocation.leveraged_percent if previous_allocation is not None else None,
            suffix="%",
        ),
    )
    _render_plain_metric(
        alloc_row[2],
        allocation.defensive_asset,
        f"{allocation.defensive_percent:,.2f}%",
        _delta_text(
            language,
            allocation.defensive_percent,
            previous_allocation.defensive_percent if previous_allocation is not None else None,
            suffix="%",
        ),
    )
    _render_plain_metric(
        alloc_row[3],
        tr(language, "等效仓位", "Equivalent exposure"),
        f"{allocation.equivalent_exposure:,.2f}%",
        _delta_text(
            language,
            allocation.equivalent_exposure,
            previous_allocation.equivalent_exposure if previous_allocation is not None else None,
            suffix="%",
        ),
    )
    if allocation.notes:
        st.warning("\n".join(allocation.notes))

    # Zone D — market windows (full-width, unchanged)
    deps.market_windows(settings, timeline_mode)

    # Zone E — portfolio adjustment (collapsed by default)
    with st.expander(tr(language, "组合调整", "Portfolio Adjustment"), expanded=False):
        deps.portfolio_adjustment_section(settings, allocation, st.session_state.get("daily_prices", {}), signal.date)
