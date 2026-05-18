from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable

import altair as alt
import pandas as pd
import streamlit as st

from trend_system.backtest import build_parameter_sweep_candidate, run_backtest, run_parameter_sweep
from trend_system.interfaces.streamlit.components import render_info_panel, render_section_head
from trend_system.interfaces.streamlit.shared.session_state import SessionKeys
from trend_system.interfaces.streamlit.shared.state import model_settings as shared_model_settings
from trend_system.models import BacktestRequest
from trend_system.services.backtest_service import run_backtest_use_case
from trend_system.signals import history_start_date


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
    trade_summary_rows: Callable[..., list[tuple[str, str]]]
    equity_columns_for_pdf: Callable[[bool, bool, bool], list[str]]
    exposure_columns_for_timing: Callable[[str], list[str]]
    zoomable_line_chart: Callable[..., None]
    execution_timing_labels: Callable[[str], dict[str, str]]
    backtest_date_defaults: Callable[[str, dict[str, Any]], tuple[date, date]]
    fingerprint: Callable[[dict[str, Any], dict[str, str]], str]
    is_stale: Callable[[str, dict[str, Any], dict[str, str]], bool]
    default_raw_settings: Callable[[], dict[str, Any]]


def render_backtest_page(
    settings: dict[str, Any],
    language: str,
    *,
    deps: BacktestPageDeps,
) -> None:
    tr = deps.tr
    st.subheader(tr(language, "历史回测", "Historical Backtest"))
    render_info_panel(
        st,
        tr(language, "仓位曲线显示的是实际目标等效仓位。最大等效仓位只是上限；若趋势仓位 × VIX 系数达不到上限，曲线不会碰到 300%。", "The exposure curve shows actual target equivalent exposure. The maximum exposure is only a cap."),
        title=tr(language, "回测中", "Backtesting"),
    )
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

    control_row = st.columns(4)
    start = control_row[0].date_input(tr(language, "回测起始日期", "Backtest start date"), value=default_start, key=f"backtest_start_{preset}")
    end = control_row[1].date_input(tr(language, "回测结束日期", "Backtest end date"), value=default_end, key=f"backtest_end_{preset}")
    initial = control_row[2].number_input(tr(language, "初始资金", "Initial capital"), 1000.0, 10_000_000.0, float(settings["backtest"]["initial_capital"]), 1000.0)
    settings["backtest"]["initial_capital"] = initial
    weekly_contribution = control_row[3].number_input(
        tr(language, "每周追加资金", "Weekly contribution"),
        0.0,
        1_000_000.0,
        float(settings["backtest"].get("weekly_contribution", 0.0)),
        100.0,
        help=tr(language, "每个新交易周开始时追加到策略和所有参考曲线。第一条回测记录只使用初始资金。", "Added to the strategy and all benchmark curves at the start of each new trading week. The first backtest row uses only initial capital."),
    )
    settings["backtest"]["weekly_contribution"] = weekly_contribution
    chart_settings = st.columns(4)
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
    st.caption(tr(language, "前三个开关只影响净值图显示；真实杠杆 ETF 收益会改变回测结果。", "The first three toggles only affect the equity chart display; actual leveraged ETF returns change the backtest result."))
    execution_timing_labels = deps.execution_timing_labels(language)
    current_execution_timing = settings["backtest"].get("execution_timing", "next_session" if settings["backtest"].get("signal_effective_next_day", True) else "same_close")
    timing_cols = st.columns([3, 1])
    selected_execution_timing_label = timing_cols[0].selectbox(
        tr(language, "回测执行时点", "Backtest execution timing"),
        list(execution_timing_labels.keys()),
        index=deps.option_index(
            list(execution_timing_labels.keys()),
            next((label for label, value in execution_timing_labels.items() if value == current_execution_timing), list(execution_timing_labels.keys())[0]),
        ),
        help=tr(language, "选择信号生成后用哪一个交易时点进入新仓位。", "Choose when a new position starts after a signal is generated."),
    )
    run = deps.aligned_button(timing_cols[1], tr(language, "运行回测", "Run backtest"), type="primary", use_container_width=True)
    execution_timing = execution_timing_labels[selected_execution_timing_label]
    settings["backtest"]["execution_timing"] = execution_timing
    settings["backtest"]["signal_effective_next_day"] = execution_timing != "same_close"
    if execution_timing == "next_session":
        render_info_panel(
            st,
            tr(language, "回测备忘：当日收益使用前一交易日收盘后已经持有的仓位计算；当日收盘数据只生成新的调仓信号，新仓位从下一交易日开始生效。因此，即使当天暴涨才触发加仓，策略也不会吃到当天涨幅，只会在当天收盘后记录调仓。", "Backtest note: each day's return is calculated using the position already held after the previous close. The current close only generates a new rebalance signal, and the new position starts from the next trading day. So if a sharp rally triggers an add-exposure signal, the strategy does not capture that same-day rally; it records the rebalance after the close."),
            title=tr(language, "回测备忘", "Backtest Note"),
        )
    elif execution_timing == "same_close":
        st.warning(tr(language, "当前为激进口径：当天收盘信号会在当天收益前生效，可能包含前视偏差，只适合与下一交易日生效口径做对照。", "Aggressive mode is active: the same-day close signal applies before that day's return. This can include look-ahead bias and should only be used for comparison."))

    if end < start:
        st.error(tr(language, "回测结束日期不能早于开始日期。", "Backtest end date cannot be earlier than the start date."))
        return

    fingerprint_extras = {
        "start": str(start),
        "end": str(end),
        "initial_capital": str(initial),
        "weekly_contribution": str(weekly_contribution),
        "execution_timing": execution_timing,
        "use_actual_leveraged_returns": str(use_actual_leveraged_returns),
    }
    should_prepare = run or SessionKeys.BACKTEST_RESULT not in st.session_state
    if should_prepare:
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
            st.session_state[SessionKeys.BACKTEST_RESULT] = result
            st.session_state[SessionKeys.BACKTEST_FINGERPRINT] = deps.fingerprint(settings, fingerprint_extras)

    result = st.session_state[SessionKeys.BACKTEST_RESULT]
    if deps.is_stale(SessionKeys.BACKTEST_FINGERPRINT, settings, fingerprint_extras):
        st.warning(tr(language, "数据已更改，请重新回测并刷新数据。", "Settings changed. Please rerun the backtest."))

    parameter_report = _render_parameter_debug_section(settings, start, end, language, deps=deps)
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
    render_section_head(st, tr(language, "策略表现", "Strategy Performance"), tone="prussian")
    _strat_cagr = metrics.get("cagr_pct", 0)
    _strat_dd   = metrics.get("max_drawdown_pct", 0)
    _strat_calmar = abs(_strat_cagr / _strat_dd) if _strat_dd else 0.0
    _strat_sharpe = metrics.get("sharpe_no_rf", 0)
    _strat_volatility = metrics.get("annual_volatility_pct", 0)
    benchmark_symbol = settings["signals"]["primary"]
    _bh_cagr = metrics.get("buy_hold_cagr_pct", 0)
    _bh_dd   = metrics.get("buy_hold_max_drawdown_pct", 0)
    _bh_sharpe = metrics.get("buy_hold_sharpe_no_rf", 0)
    _bh_calmar = abs(_bh_cagr / _bh_dd) if _bh_dd else 0.0
    _bh_volatility = metrics.get("buy_hold_annual_volatility_pct", 0)
    comparison_cards = [
        {
            "label": tr(language, "总收益对照", "Return comparison"),
            "strategy_label": tr(language, "策略", "Strategy"),
            "strategy_value": f'{metrics.get("total_return_pct", 0):,.2f}%',
            "benchmark_label": benchmark_symbol,
            "benchmark_value": f'{metrics.get("buy_hold_total_return_pct", 0):,.2f}%',
            "tone": _comparison_tone(metrics.get("total_return_pct", 0), metrics.get("buy_hold_total_return_pct", 0), higher_is_better=True),
        },
        {
            "label": tr(language, "CAGR 对照", "CAGR comparison"),
            "strategy_label": tr(language, "策略", "Strategy"),
            "strategy_value": f"{_strat_cagr:,.2f}%",
            "benchmark_label": benchmark_symbol,
            "benchmark_value": f"{_bh_cagr:,.2f}%",
            "tone": _comparison_tone(_strat_cagr, _bh_cagr, higher_is_better=True),
        },
        {
            "label": tr(language, "最大回撤对照", "Drawdown comparison"),
            "strategy_label": tr(language, "策略", "Strategy"),
            "strategy_value": f"{_strat_dd:,.2f}%",
            "benchmark_label": benchmark_symbol,
            "benchmark_value": f"{_bh_dd:,.2f}%",
            "tone": _comparison_tone(_strat_dd, _bh_dd, higher_is_better=True),
        },
        {
            "label": tr(language, "年化波动对照", "Annual volatility comparison"),
            "strategy_label": tr(language, "策略", "Strategy"),
            "strategy_value": f"{_strat_volatility:,.2f}%",
            "benchmark_label": benchmark_symbol,
            "benchmark_value": f"{_bh_volatility:,.2f}%",
            "tone": _comparison_tone(_strat_volatility, _bh_volatility, higher_is_better=False),
        },
    ]
    comparison_markup = "".join(
        [
            f'<span class="strategy-console-chip"><strong>{tr(language, "基准产品", "Benchmark")}</strong>: {benchmark_symbol}</span>',
            f'<span class="strategy-console-chip"><strong>{tr(language, "Sharpe 对照", "Sharpe comparison")}</strong>: {_strat_sharpe:.2f} / {_bh_sharpe:.2f}</span>',
            f'<span class="strategy-console-chip"><strong>{tr(language, "Calmar 对照", "Calmar comparison")}</strong>: {_strat_calmar:.2f} / {_bh_calmar:.2f}</span>',
        ]
    )
    st.markdown(f'<div class="strategy-console-grid">{comparison_markup}</div>', unsafe_allow_html=True)
    _render_comparison_rows(comparison_cards, per_row=4)
    st.caption(tr(language, "CAGR = 年化复合增长率，表示资金按复利计算后平均每年增长多少；它不是简单平均年收益。", "CAGR is compound annual growth rate. It is not a simple average annual return."))

    if st.button(tr(language, "回正净值图", "Reset equity chart")):
        st.session_state[SessionKeys.EQUITY_CHART_RESET] = st.session_state.get(SessionKeys.EQUITY_CHART_RESET, 0) + 1
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
    deps.zoomable_line_chart(result.equity_curve, equity_columns, tr(language, "净值曲线", "Equity curve"), key=f"equity_chart_{st.session_state.get(SessionKeys.EQUITY_CHART_RESET, 0)}", language=language, line_styles=equity_line_styles)
    if st.button(tr(language, "回正仓位图", "Reset exposure chart")):
        st.session_state[SessionKeys.EXPOSURE_CHART_RESET] = st.session_state.get(SessionKeys.EXPOSURE_CHART_RESET, 0) + 1
    deps.zoomable_line_chart(result.equity_curve, deps.exposure_columns_for_timing(execution_timing), tr(language, "仓位曲线", "Exposure curve"), key=f"exposure_chart_{st.session_state.get(SessionKeys.EXPOSURE_CHART_RESET, 0)}", language=language)
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

    with st.expander(tr(language, "调仓记录", "Rebalance Log")):
        trade_view = st.radio(tr(language, "显示范围", "Rows"), [tr(language, "最近 50 笔", "Latest 50"), tr(language, "全部", "All")], horizontal=True)
        trades_to_show = result.trades.tail(50) if trade_view.startswith(tr(language, "最近", "Latest")) else result.trades
        st.dataframe(trades_to_show, use_container_width=True, height=320)
        st.download_button(tr(language, "下载调仓记录 CSV", "Download rebalance log CSV"), data=result.trades.to_csv(index=False).encode("utf-8"), file_name="trades.csv", mime="text/csv")


def _render_parameter_debug_section(
    settings: dict[str, Any],
    start: date,
    end: date,
    language: str,
    *,
    deps: BacktestPageDeps,
) -> dict[str, Any] | None:
    tr = deps.tr
    has_result = isinstance(st.session_state.get(SessionKeys.PARAMETER_SWEEP), dict)
    with st.expander(tr(language, "调试模式：参数扫描", "Debug mode: parameter sweep"), expanded=has_result):
        st.caption(
            tr(
                language,
                "在当前回测区间内，把核心模型参数按当前值的 50%、75%、100%、125%、150% 测试，并额外围绕目标日期生成时间窗口优化。结果会同时对比当前配置基准线和默认配置基准线。",
                "Within the current backtest range, test core model parameters at 50%, 75%, 100%, 125%, and 150% of their current values, then run an additional target-date window optimization. Results compare against both the current configuration baseline and the default configuration baseline.",
            )
        )
        controls = st.columns(4)
        target_date = controls[0].date_input(
            tr(language, "目标日期", "Target date"),
            value=end,
            min_value=start,
            max_value=end,
            key=SessionKeys.SWEEP_TARGET_DATE,
        )
        months_before = controls[1].number_input(
            tr(language, "目标日前月数", "Months before"),
            min_value=0,
            max_value=120,
            value=6,
            step=1,
            key=SessionKeys.SWEEP_MONTHS_BEFORE,
        )
        months_after = controls[2].number_input(
            tr(language, "目标日后月数", "Months after"),
            min_value=0,
            max_value=120,
            value=6,
            step=1,
            key=SessionKeys.SWEEP_MONTHS_AFTER,
        )
        sort_options = {
            tr(language, "策略总收益", "Strategy total return"): "total_return_pct",
            "CAGR": "cagr_pct",
            "Sharpe": "sharpe_no_rf",
            tr(language, "最大回撤（越高越好）", "Max drawdown, higher is better"): "max_drawdown_pct",
            tr(language, "年化波动（越低越好）", "Annual volatility, lower is better"): "annual_volatility_pct",
            tr(language, "调仓次数（越少越好）", "Rebalances, lower is better"): "trades",
        }
        sort_label = controls[3].selectbox(
            tr(language, "排序目标", "Ranking objective"),
            list(sort_options.keys()),
            key=SessionKeys.SWEEP_SORT_METRIC,
        )
        sort_metric = sort_options[sort_label]
        run_sweep = st.button(
            tr(language, "运行 50% 参数扫描", "Run 50% parameter sweep"),
            use_container_width=True,
        )
        if not run_sweep and not has_result:
            return None
        if not run_sweep and not isinstance(st.session_state.get(SessionKeys.PARAMETER_SWEEP), dict):
            st.session_state.pop(SessionKeys.PARAMETER_SWEEP, None)
            return None

        if run_sweep:
            with st.status(tr(language, "扫描中...", "Scanning..."), expanded=True) as status:
                primary = settings["signals"]["primary"]
                vix_symbol = settings["signals"]["volatility"]
                price_field = settings["signals"].get("price_field", "Close")
                default_raw = deps.default_raw_settings()
                status.update(
                    label=tr(language, "正在准备价格数据...", "Preparing price data..."),
                    state="running",
                )
                data_start = min(
                    history_start_date(start, settings),
                    history_start_date(start, default_raw),
                )
                prices = deps.cached_prices((primary, vix_symbol), str(data_start), _inclusive_end(end), True)
                price = prices[primary][price_field]
                vix = prices[vix_symbol][price_field]
                open_price = prices[primary].get("Open")
                model_settings = shared_model_settings(settings)
                default_settings = shared_model_settings(default_raw)
                status.update(
                    label=tr(language, "正在运行全区间扫描...", "Running full-range sweep..."),
                    state="running",
                )
                individual, unified, ranges, recommendations = _cached_parameter_sweep(
                    price,
                    vix,
                    model_settings,
                    open_price=open_price,
                    result_start=str(start),
                    baseline_settings=default_settings,
                    sort_metric=sort_metric,
                )
                individual = _with_parameter_ui_names(individual, model_settings, language, tr)
                unified = _with_parameter_ui_names(unified, model_settings, language, tr)
                ranges = _with_parameter_ui_names(ranges, model_settings, language, tr)
                recommendations = _with_parameter_ui_names(recommendations, model_settings, language, tr)
                window_start = max(start, target_date - timedelta(days=int(months_before) * 30))
                window_end = min(end, target_date + timedelta(days=int(months_after) * 30))
                target_price = price.loc[: pd.Timestamp(window_end)]
                target_vix = vix.loc[: pd.Timestamp(window_end)]
                target_open_price = open_price.loc[: pd.Timestamp(window_end)] if open_price is not None else None
                status.update(
                    label=tr(language, "正在运行目标窗口扫描...", "Running target-window sweep..."),
                    state="running",
                )
                target_individual, target_unified, target_ranges, target_recommendations = _cached_parameter_sweep(
                    target_price,
                    target_vix,
                    model_settings,
                    open_price=target_open_price,
                    result_start=str(window_start),
                    baseline_settings=default_settings,
                    sort_metric=sort_metric,
                )
                target_individual = _with_parameter_ui_names(target_individual, model_settings, language, tr)
                target_unified = _with_parameter_ui_names(target_unified, model_settings, language, tr)
                target_ranges = _with_parameter_ui_names(target_ranges, model_settings, language, tr)
                target_recommendations = _with_parameter_ui_names(target_recommendations, model_settings, language, tr)
                status.update(
                    label=tr(language, "正在生成比较曲线...", "Building comparison curves..."),
                    state="running",
                )
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
                st.session_state[SessionKeys.PARAMETER_SWEEP] = {
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
                status.update(
                    label=tr(language, "参数扫描完成", "Parameter sweep complete"),
                    state="complete",
                )

    stored = st.session_state.get(SessionKeys.PARAMETER_SWEEP)
    if not isinstance(stored, dict):
        return None

    individual, unified, ranges, recommendations = stored["full"]
    _, _, target_ranges, target_recommendations = stored["target"]
    render_section_head(st, tr(language, "全区间参数调整建议", "Full-Range Parameter Recommendations"), tone="prussian")
    st.dataframe(_localized_recommendations(recommendations, language), use_container_width=True, hide_index=True)
    render_section_head(st, tr(language, "最适合的参数范围", "Preferred Parameter Ranges"), tone="prussian")
    st.dataframe(_localized_parameter_frame(ranges, language), use_container_width=True, hide_index=True)
    render_section_head(st, tr(language, "逐个测试最佳结果", "Best Individual Tests"), tone="prussian")
    st.dataframe(_localized_parameter_frame(individual.head(25), language), use_container_width=True, hide_index=True)
    render_section_head(st, tr(language, "统一测试结果", "Unified Test Results"), tone="prussian")
    st.dataframe(_localized_parameter_frame(unified, language), use_container_width=True, hide_index=True)
    render_section_head(st, tr(language, "全区间对比净值曲线", "Full-Range Comparison Equity Curves"), tone="prussian")
    deps.zoomable_line_chart(
        stored["full_curves"],
        list(stored["full_curves"].columns),
        tr(language, "扫描对比净值", "Sweep comparison equity"),
        key="parameter_sweep_full_curves",
        language=language,
    )
    _sweep_metric_line_chart(
        stored["full_factor_curves"],
        tr(language, "全区间单参数扫描折线", "Full-range individual sweep lines"),
        stored["sort_metric"],
        language,
        tr,
        key="parameter_sweep_full_factor_lines",
    )
    render_section_head(st, tr(language, "目标日期参数建议表", "Target-Date Parameter Recommendations"), tone="green")
    st.caption(
        tr(
            language,
            f"目标日期：{stored['target_date']}；时间窗口：{stored['window_start']} ~ {stored['window_end']}；排序目标：{stored['sort_label']}",
            f"Target date: {stored['target_date']}; window: {stored['window_start']} to {stored['window_end']}; objective: {stored['sort_label']}",
        )
    )
    st.dataframe(_localized_recommendations(target_recommendations, language), use_container_width=True, hide_index=True)
    render_section_head(st, tr(language, "目标日期窗口最适合的参数范围", "Target Window Preferred Parameter Ranges"), tone="green")
    st.dataframe(_localized_parameter_frame(target_ranges, language), use_container_width=True, hide_index=True)
    render_section_head(st, tr(language, "目标日期窗口对比净值曲线", "Target Window Comparison Equity Curves"), tone="green")
    deps.zoomable_line_chart(
        stored["target_curves"],
        list(stored["target_curves"].columns),
        tr(language, "目标窗口扫描对比净值", "Target window sweep comparison equity"),
        key="parameter_sweep_target_curves",
        language=language,
    )
    _sweep_metric_line_chart(
        stored["target_factor_curves"],
        tr(language, "目标窗口单参数扫描折线", "Target-window individual sweep lines"),
        stored["sort_metric"],
        language,
        tr,
        key="parameter_sweep_target_factor_lines",
    )
    return {
        "sections": _parameter_pdf_sections(stored, language, tr),
        "charts": [
            (tr(language, "全区间扫描对比净值曲线", "Full-range sweep comparison equity"), stored["full_curves"], list(stored["full_curves"].columns)),
            (tr(language, "全区间单参数扫描折线", "Full-range individual sweep lines"), stored["full_factor_curves"], list(stored["full_factor_curves"].columns)),
            (tr(language, "目标窗口扫描对比净值曲线", "Target-window sweep comparison equity"), stored["target_curves"], list(stored["target_curves"].columns)),
            (tr(language, "目标窗口单参数扫描折线", "Target-window individual sweep lines"), stored["target_factor_curves"], list(stored["target_factor_curves"].columns)),
        ],
    }


def _inclusive_end(value: date) -> str:
    return str(value + timedelta(days=1))


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


def _with_parameter_ui_names(
    frame: pd.DataFrame,
    settings: dict[str, Any],
    language: str,
    tr: Callable[[str, str, str], str],
) -> pd.DataFrame:
    if frame.empty or "parameter" not in frame.columns:
        return frame
    labelled = frame.copy()
    names = labelled["parameter"].apply(lambda parameter: _parameter_ui_name(str(parameter), settings, language, tr))
    if "parameter_ui_name" in labelled.columns:
        labelled["parameter_ui_name"] = names
    else:
        labelled.insert(min(1, len(labelled.columns)), "parameter_ui_name", names)
    return labelled


def _parameter_ui_name(
    parameter: str,
    settings: dict[str, Any],
    language: str,
    tr: Callable[[str, str, str], str],
) -> str:
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
        return tr(language, f"{label} 系数", f"{label} multiplier")
    zh, en = labels.get(parameter, (parameter, parameter))
    return tr(language, zh, en)


def _vix_rule_label(parameter: str, settings: dict[str, Any]) -> str:
    try:
        index = int(parameter.split(".")[2])
        return str(settings.get("vix", {}).get("rules", [])[index].get("label", f"rule {index + 1}"))
    except (IndexError, ValueError, AttributeError):
        return parameter


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
    tr: Callable[[str, str, str], str],
    *,
    key: str,
) -> None:
    if frame.empty:
        st.info(tr(language, "没有足够数据生成扫描折线。", "Not enough data to render sweep lines."))
        return
    is_dark = st.session_state.get(SessionKeys.UI_THEME, "dark") == "dark"
    axis_color = "rgba(244, 240, 232, 0.78)" if is_dark else "rgba(17, 18, 20, 0.72)"
    grid_color = "rgba(174, 143, 84, 0.14)" if is_dark else "rgba(148, 163, 184, 0.18)"
    title_color = "rgba(244, 240, 232, 0.94)" if is_dark else "rgba(17, 18, 20, 0.92)"
    chart_data = (
        frame.reset_index()
        .melt(id_vars="factor", var_name="parameter", value_name="value")
        .dropna()
    )
    chart = (
        alt.Chart(chart_data)
        .mark_line(point=True, strokeCap="round")
        .encode(
            x=alt.X("factor:Q", title=tr(language, "参数倍率", "Parameter factor")),
            y=alt.Y("value:Q", title=metric),
            color=alt.Color("parameter:N", title=tr(language, "参数", "Parameter")),
            tooltip=[
                alt.Tooltip("factor:Q", title=tr(language, "参数倍率", "Parameter factor"), format=".2f"),
                alt.Tooltip("parameter:N", title=tr(language, "参数", "Parameter")),
                alt.Tooltip("value:Q", title=metric, format=",.2f"),
            ],
        )
        .properties(title=title, height=320)
        .configure(background="transparent")
        .configure_axis(
            labelColor=axis_color,
            titleColor=axis_color,
            domainColor=grid_color,
            gridColor=grid_color,
            tickColor=grid_color,
        )
        .configure_legend(
            labelColor=axis_color,
            titleColor=axis_color,
        )
        .configure_title(
            color=title_color,
            anchor="start",
        )
        .interactive()
    )
    st.altair_chart(chart, use_container_width=True, key=key)


def _render_metric_rows(metrics: list[dict[str, str]], *, per_row: int = 4) -> None:
    for index in range(0, len(metrics), per_row):
        row = st.columns(per_row)
        for col, metric in zip(row, metrics[index:index + per_row]):
            col.metric(metric["label"], metric["value"])


def _render_comparison_rows(comparisons: list[dict[str, str]], *, per_row: int = 4) -> None:
    for index in range(0, len(comparisons), per_row):
        row = st.columns(per_row)
        for col, comparison in zip(row, comparisons[index:index + per_row]):
            col.markdown(
                f"""
<div class="leo-comparison-card leo-comparison-card--{comparison.get("tone", "neutral")}">
  <div class="leo-comparison-card__label">{comparison["label"]}</div>
  <div class="leo-comparison-card__strategy">
    <div class="leo-comparison-card__meta">{comparison["strategy_label"]}</div>
    <div class="leo-comparison-card__value">{comparison["strategy_value"]}</div>
  </div>
  <div class="leo-comparison-card__benchmark">
    <div class="leo-comparison-card__meta leo-comparison-card__meta--benchmark">{comparison["benchmark_label"]}</div>
    <div class="leo-comparison-card__value leo-comparison-card__value--benchmark">{comparison["benchmark_value"]}</div>
  </div>
</div>
""",
                unsafe_allow_html=True,
            )


def _comparison_tone(strategy_value: float, benchmark_value: float, *, higher_is_better: bool) -> str:
    if abs(strategy_value - benchmark_value) < 1e-9:
        return "neutral"
    if higher_is_better:
        return "better" if strategy_value > benchmark_value else "worse"
    return "better" if strategy_value < benchmark_value else "worse"


def _parameter_pdf_sections(
    stored: dict[str, Any],
    language: str,
    tr: Callable[[str, str, str], str],
) -> list[tuple[str, list[tuple[str, str]]]]:
    _, _, _, recommendations = stored["full"]
    _, _, _, target_recommendations = stored["target"]
    full_rows = [
        (tr(language, "扫描范围", "Sweep range"), "50% / 75% / 100% / 125% / 150%"),
        (tr(language, "排序目标", "Ranking objective"), str(stored["sort_label"])),
    ]
    full_rows.extend(_recommendation_rows_for_pdf(recommendations, language, tr))
    target_rows = [
        (tr(language, "目标日期", "Target date"), str(stored["target_date"])),
        (tr(language, "时间窗口", "Time window"), f"{stored['window_start']} ~ {stored['window_end']}"),
        (tr(language, "排序目标", "Ranking objective"), str(stored["sort_label"])),
    ]
    target_rows.extend(_recommendation_rows_for_pdf(target_recommendations, language, tr))
    return [
        (tr(language, "全区间参数扫描建议", "Full-Range Parameter Sweep Recommendations"), full_rows),
        (tr(language, "目标日期参数建议表", "Target-Date Parameter Recommendations"), target_rows),
    ]


def _recommendation_rows_for_pdf(
    frame: pd.DataFrame,
    language: str,
    tr: Callable[[str, str, str], str],
    *,
    limit: int = 8,
) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for _, row in frame.head(limit).iterrows():
        label = str(row.get("parameter", ""))
        ui_name = str(row.get("parameter_ui_name", label))
        value = (
            f"{tr(language, 'UI 命名', 'UI name')} {ui_name} | "
            f"{tr(language, '当前', 'current')} {row.get('current_value')} -> "
            f"{tr(language, '建议', 'recommended')} {row.get('recommended_value')} | "
            f"{tr(language, '相对当前', 'vs current')} {row.get('baseline_delta_pct', 0):.2f}pp | "
            f"{tr(language, '相对默认', 'vs default')} {row.get('default_baseline_delta_pct', 0):.2f}pp"
        )
        rows.append((label, value))
    return rows
