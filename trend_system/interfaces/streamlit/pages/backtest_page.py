from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

import streamlit as st

from trend_system.models import BacktestRequest
from trend_system.services.backtest_service import run_backtest_use_case


@dataclass(frozen=True)
class BacktestPageDeps:
    as_settings: Callable[[dict[str, Any]], Any]
    tr: Callable[[str, str, str], str]
    aligned_button: Callable[..., bool]
    option_index: Callable[[list[str], str], int]
    disabled_pdf_button: Callable[..., None]
    pdf_download_button: Callable[..., None]
    build_pdf_report: Callable[..., bytes]
    pdf_filename: Callable[..., str]
    cached_prices: Callable[[tuple[str, ...], str, str | None, bool], dict]
    strategy_summary_rows: Callable[[dict[str, Any], str], list[tuple[str, str]]]
    parameter_debug_section: Callable[[dict[str, Any], date, date, str], dict[str, Any] | None]
    trade_summary_rows: Callable[..., list[tuple[str, str]]]
    equity_columns_for_pdf: Callable[[bool, bool, bool], list[str]]
    exposure_columns_for_timing: Callable[[str], list[str]]
    zoomable_line_chart: Callable[..., None]
    execution_timing_labels: Callable[[str], dict[str, str]]
    backtest_date_defaults: Callable[[str, dict[str, Any]], tuple[date, date]]
    fingerprint: Callable[[dict[str, Any], dict[str, str]], str]
    is_stale: Callable[[str, dict[str, Any], dict[str, str]], bool]
    versioned_status: Callable[..., Any] | None = None


def render_backtest_page(
    settings: dict[str, Any],
    language: str,
    *,
    deps: BacktestPageDeps,
) -> None:
    tr = deps.tr
    st.subheader(tr(language, "历史回测", "Historical Backtest"))
    st.caption(tr(language, "仓位曲线显示的是实际目标等效仓位。最大等效仓位只是上限；若趋势仓位 × VIX 系数达不到上限，曲线不会碰到 300%。", "The exposure curve shows actual target equivalent exposure. The maximum exposure is only a cap."))
    preset_labels = {
        tr(language, "自定义", "Custom"): "自定义",
        tr(language, "2000-01-01 到 2010-01-01", "2000-01-01 to 2010-01-01"): "2000-01-01 到 2010-01-01",
        tr(language, "2010-01-01 到现在", "2010-01-01 to today"): "2010-01-01 到现在",
        tr(language, "2021-01-01 到 2023-12-31", "2021-01-01 to 2023-12-31"): "2021-01-01 到 2023-12-31",
        tr(language, "2000-01-01 到现在", "2000-01-01 to today"): "2000-01-01 到现在",
    }
    preset_label = st.selectbox(tr(language, "回测区间预设", "Backtest date preset"), list(preset_labels.keys()))
    preset = preset_labels[preset_label]
    default_start, default_end = deps.backtest_date_defaults(preset, settings)

    cols = st.columns([1, 1, 1, 1, 1])
    start = cols[0].date_input(tr(language, "回测起始日期", "Backtest start date"), value=default_start, key=f"backtest_start_{preset}")
    end = cols[1].date_input(tr(language, "回测结束日期", "Backtest end date"), value=default_end, key=f"backtest_end_{preset}")
    initial = cols[2].number_input(tr(language, "初始资金", "Initial capital"), 1000.0, 10_000_000.0, float(settings["backtest"]["initial_capital"]), 1000.0)
    settings["backtest"]["initial_capital"] = initial
    weekly_contribution = cols[3].number_input(
        tr(language, "每周追加资金", "Weekly contribution"),
        0.0,
        1_000_000.0,
        float(settings["backtest"].get("weekly_contribution", 0.0)),
        100.0,
        help=tr(language, "每个新交易周开始时追加到策略和所有参考曲线。第一条回测记录只使用初始资金。", "Added to the strategy and all benchmark curves at the start of each new trading week. The first backtest row uses only initial capital."),
    )
    settings["backtest"]["weekly_contribution"] = weekly_contribution
    run = deps.aligned_button(cols[4], tr(language, "运行回测", "Run backtest"), type="primary", use_container_width=True)
    chart_settings = st.columns([1, 1, 1, 2])
    show_leveraged_buy_hold = chart_settings[0].toggle(tr(language, "显示 3 倍买入持有虚线", "Show dashed 3x buy & hold"), value=bool(settings["backtest"].get("show_leveraged_buy_hold", True)))
    show_ma120_timing = chart_settings[1].toggle(tr(language, "显示 120 日择时点线", "Show dotted 120-day timing"), value=bool(settings["backtest"].get("show_ma120_timing", True)))
    show_leveraged_ma120_timing = chart_settings[2].toggle(tr(language, "显示三倍持有：跌破 120 日均线转现金", "Show 3x Hold: Cash Below 120MA"), value=bool(settings["backtest"].get("show_leveraged_ma120_timing", True)))
    use_actual_leveraged_returns = chart_settings[3].toggle(
        tr(language, "使用真实杠杆 ETF 收益", "Use actual leveraged ETF returns"),
        value=bool(settings["backtest"].get("use_actual_leveraged_asset_returns", False)),
        help=tr(language, "开启后，策略杠杆部分和 3 倍持有曲线会使用配置里的杠杆 ETF 真实价格，例如 SPXL；关闭时使用 S&P 500 日收益 × 杠杆倍数的理论口径。", "When enabled, the strategy leveraged sleeve and 3x hold line use the configured leveraged ETF's actual price, for example SPXL. When off, they use the synthetic S&P 500 daily return x leverage multiple."),
    )
    settings["backtest"]["show_leveraged_buy_hold"] = show_leveraged_buy_hold
    settings["backtest"]["show_ma120_timing"] = show_ma120_timing
    settings["backtest"]["show_leveraged_ma120_timing"] = show_leveraged_ma120_timing
    settings["backtest"]["use_actual_leveraged_asset_returns"] = use_actual_leveraged_returns
    chart_settings[3].caption(tr(language, "前三个开关只影响净值图显示；真实杠杆 ETF 收益会改变回测结果。", "The first three toggles only affect the equity chart display; actual leveraged ETF returns change the backtest result."))
    execution_timing_labels = deps.execution_timing_labels(language)
    current_execution_timing = settings["backtest"].get("execution_timing", "next_session" if settings["backtest"].get("signal_effective_next_day", True) else "same_close")
    selected_execution_timing_label = st.selectbox(
        tr(language, "回测执行时点", "Backtest execution timing"),
        list(execution_timing_labels.keys()),
        index=deps.option_index(
            list(execution_timing_labels.keys()),
            next((label for label, value in execution_timing_labels.items() if value == current_execution_timing), list(execution_timing_labels.keys())[0]),
        ),
        help=tr(language, "选择信号生成后用哪一个交易时点进入新仓位。", "Choose when a new position starts after a signal is generated."),
    )
    execution_timing = execution_timing_labels[selected_execution_timing_label]
    settings["backtest"]["execution_timing"] = execution_timing
    settings["backtest"]["signal_effective_next_day"] = execution_timing != "same_close"
    if execution_timing == "next_session":
        st.info(tr(language, "回测备忘：当日收益使用前一交易日收盘后已经持有的仓位计算；当日收盘数据只生成新的调仓信号，新仓位从下一交易日开始生效。因此，即使当天暴涨才触发加仓，策略也不会吃到当天涨幅，只会在当天收盘后记录调仓。", "Backtest note: each day's return is calculated using the position already held after the previous close. The current close only generates a new rebalance signal, and the new position starts from the next trading day. So if a sharp rally triggers an add-exposure signal, the strategy does not capture that same-day rally; it records the rebalance after the close."))
    elif execution_timing == "same_close":
        st.warning(tr(language, "当前为激进口径：当天收盘信号会在当天收益前生效，可能包含前视偏差，只适合与下一交易日生效口径做对照。", "Aggressive mode is active: the same-day close signal applies before that day's return. This can include look-ahead bias and should only be used for comparison."))

    if end < start:
        st.error(tr(language, "回测结束日期不能早于开始日期。", "Backtest end date cannot be earlier than the start date."))
        return

    if not run and "backtest_result" not in st.session_state:
        deps.disabled_pdf_button(language, tr(language, "打印/下载历史回测 PDF", "Print/Download Backtest PDF"), key="backtest_pdf_disabled")
        st.info(tr(language, "回测尚未运行。", "Backtest has not been run yet."))
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
        with st.status(tr(language, "准备回测...", "Preparing backtest..."), expanded=True) as status:
            status.update(label=tr(language, "下载或读取缓存中的历史价格...", "Downloading or reading cached price history..."))
            price_loader = lambda symbol_list, start, end=None, auto_adjust=True: deps.cached_prices(tuple(symbol_list), str(start), end, auto_adjust)
            status.update(label=tr(language, "运行回测模型...", "Running backtest model..."))
            service_result = run_backtest_use_case(
                BacktestRequest(
                    settings=deps.as_settings(settings),
                    start=str(start),
                    end=str(end),
                    use_actual_leveraged_returns=use_actual_leveraged_returns,
                ),
                price_loader=price_loader,
            )
            result = service_result.result
            status.update(label=tr(language, "生成图表和指标...", "Rendering charts and metrics..."), state="complete")
            st.session_state["backtest_result"] = result
            st.session_state["backtest_fingerprint"] = deps.fingerprint(settings, fingerprint_extras)

    result = st.session_state["backtest_result"]
    if deps.is_stale("backtest_fingerprint", settings, fingerprint_extras):
        st.warning(tr(language, "数据已更改，请重新回测并刷新数据。", "Settings changed. Please rerun the backtest."))

    parameter_report = deps.parameter_debug_section(settings, start, end, language)
    metrics = result.metrics
    backtest_rows = [
        (tr(language, "回测区间", "Backtest range"), f"{start} ~ {end}"),
        (tr(language, "初始资金", "Initial capital"), f"{initial:,.2f}"),
        (tr(language, "每周追加资金", "Weekly contribution"), f"{weekly_contribution:,.2f}"),
        (tr(language, "执行时点", "Execution timing"), execution_timing),
        (tr(language, "策略总收益", "Strategy total return"), f"{metrics.get('total_return_pct', 0):,.2f}%"),
        ("CAGR", f"{metrics.get('cagr_pct', 0):,.2f}%"),
        (tr(language, "最大回撤", "Max drawdown"), f"{metrics.get('max_drawdown_pct', 0):,.2f}%"),
        (tr(language, "年化波动", "Annual volatility"), f"{metrics.get('annual_volatility_pct', 0):,.2f}%"),
        ("Sharpe", f"{metrics.get('sharpe_no_rf', 0):.2f}"),
        (tr(language, "基准总收益", "Benchmark total return"), f"{metrics.get('buy_hold_total_return_pct', 0):,.2f}%"),
        (tr(language, "基准 CAGR", "Benchmark CAGR"), f"{metrics.get('buy_hold_cagr_pct', 0):,.2f}%"),
        (tr(language, "调仓次数", "Rebalances"), str(len(result.trades))),
    ]
    latest_curve = result.equity_curve.iloc[-1]
    curve_rows = [
        (tr(language, "策略净值", "Strategy equity"), f"{latest_curve.get('equity', 0):,.2f}"),
        (tr(language, "S&P 500 持有", "S&P 500 buy & hold"), f"{latest_curve.get('buy_hold_equity', 0):,.2f}"),
        (tr(language, "3 倍 S&P 500 买入持有", "3x S&P 500 buy & hold"), f"{latest_curve.get('leveraged_buy_hold_equity', 0):,.2f}"),
        (tr(language, "S&P 500 120 日择时", "S&P 500 120-day timing"), f"{latest_curve.get('ma120_timing_equity', 0):,.2f}"),
        (tr(language, "三倍持有：跌破 120 日均线转现金", "3x Hold: Cash Below 120MA"), f"{latest_curve.get('leveraged_ma120_timing_equity', 0):,.2f}"),
        (tr(language, "目标等效仓位", "Target equivalent exposure"), f"{latest_curve.get('target_exposure', 0):,.2f}%"),
        (tr(language, "实际等效仓位", "Actual equivalent exposure"), f"{latest_curve.get('actual_equivalent_exposure', 0):,.2f}%"),
    ]
    pdf_sections = [
        (tr(language, "回测表现", "Backtest Performance"), backtest_rows),
        (tr(language, "净值和仓位曲线摘要", "Equity and Exposure Summary"), curve_rows),
        (tr(language, "策略信息", "Strategy Information"), deps.strategy_summary_rows(settings, language)),
    ]
    trade_rows = deps.trade_summary_rows(result.trades, language)
    if trade_rows:
        pdf_sections.append((tr(language, "最近调仓记录", "Latest Rebalances"), trade_rows))
    pdf_charts = [
        (tr(language, "净值曲线", "Equity curve"), result.equity_curve, deps.equity_columns_for_pdf(show_leveraged_buy_hold, show_ma120_timing, show_leveraged_ma120_timing)),
        (tr(language, "仓位曲线", "Exposure curve"), result.equity_curve, deps.exposure_columns_for_timing(execution_timing)),
    ]
    if parameter_report:
        pdf_sections.extend(parameter_report["sections"])
        pdf_charts.extend(parameter_report["charts"])
    deps.pdf_download_button(
        language,
        tr(language, "打印/下载历史回测 PDF", "Print/Download Backtest PDF"),
        deps.build_pdf_report(
            tr(language, "历史回测", "Historical Backtest"),
            settings,
            language,
            sections=pdf_sections,
            charts=pdf_charts,
        ),
        deps.pdf_filename("backtest", settings, range_text=f"{start}_to_{end}", cagr=metrics.get("cagr_pct", 0.0)),
        key="backtest_pdf_download",
    )
    st.markdown(f"**{tr(language, '策略表现', 'Strategy Performance')}**")
    metric_cols = st.columns(5)
    metric_cols[0].metric(tr(language, "策略总收益", "Strategy total return"), f"{metrics.get('total_return_pct', 0):,.2f}%")
    metric_cols[1].metric("策略 CAGR", f"{metrics.get('cagr_pct', 0):,.2f}%")
    metric_cols[2].metric(tr(language, "策略最大回撤", "Strategy max drawdown"), f"{metrics.get('max_drawdown_pct', 0):,.2f}%")
    metric_cols[3].metric(tr(language, "策略年化波动", "Strategy annual volatility"), f"{metrics.get('annual_volatility_pct', 0):,.2f}%")
    metric_cols[4].metric("策略 Sharpe", f"{metrics.get('sharpe_no_rf', 0):.2f}")

    benchmark_symbol = settings["signals"]["primary"]
    st.markdown(f"**{tr(language, '买入并持有基准', 'Buy-and-hold benchmark')}: {benchmark_symbol}**")
    benchmark_cols = st.columns(5)
    benchmark_cols[0].metric(tr(language, "基准总收益", "Benchmark total return"), f"{metrics.get('buy_hold_total_return_pct', 0):,.2f}%")
    benchmark_cols[1].metric("基准 CAGR", f"{metrics.get('buy_hold_cagr_pct', 0):,.2f}%")
    benchmark_cols[2].metric(tr(language, "基准最大回撤", "Benchmark max drawdown"), f"{metrics.get('buy_hold_max_drawdown_pct', 0):,.2f}%")
    benchmark_cols[3].metric(tr(language, "基准年化波动", "Benchmark annual volatility"), f"{metrics.get('buy_hold_annual_volatility_pct', 0):,.2f}%")
    benchmark_cols[4].metric("基准 Sharpe", f"{metrics.get('buy_hold_sharpe_no_rf', 0):.2f}")
    st.caption(tr(language, "CAGR = 年化复合增长率，表示资金按复利计算后平均每年增长多少；它不是简单平均年收益。", "CAGR is compound annual growth rate. It is not a simple average annual return."))

    if st.button(tr(language, "回正净值图", "Reset equity chart")):
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
    deps.zoomable_line_chart(result.equity_curve, equity_columns, tr(language, "净值曲线", "Equity curve"), key=f"equity_chart_{st.session_state.get('equity_chart_reset', 0)}", language=language, line_styles=equity_line_styles)
    if st.button(tr(language, "回正仓位图", "Reset exposure chart")):
        st.session_state["exposure_chart_reset"] = st.session_state.get("exposure_chart_reset", 0) + 1
    deps.zoomable_line_chart(result.equity_curve, deps.exposure_columns_for_timing(execution_timing), tr(language, "仓位曲线", "Exposure curve"), key=f"exposure_chart_{st.session_state.get('exposure_chart_reset', 0)}", language=language)

    with st.expander(tr(language, "调仓记录", "Rebalance Log")):
        trade_view = st.radio(tr(language, "显示范围", "Rows"), [tr(language, "最近 50 笔", "Latest 50"), tr(language, "全部", "All")], horizontal=True)
        trades_to_show = result.trades.tail(50) if trade_view.startswith(tr(language, "最近", "Latest")) else result.trades
        st.dataframe(trades_to_show, use_container_width=True, height=320)
        st.download_button(tr(language, "下载调仓记录 CSV", "Download rebalance log CSV"), data=result.trades.to_csv(index=False).encode("utf-8"), file_name="trades.csv", mime="text/csv")
