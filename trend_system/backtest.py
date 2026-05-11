from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import pandas as pd

from trend_system.exposure_rules import apply_foreign_asset_cap_to_weights
from trend_system.portfolio import build_allocation
from trend_system.signals import signal_frame


@dataclass(frozen=True)
class BacktestResult:
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    metrics: dict[str, float]


SWEEP_FACTORS = (0.5, 0.75, 1.0, 1.25, 1.5)
SWEEP_SORT_DIRECTIONS = {
    "total_return_pct": False,
    "cagr_pct": False,
    "sharpe_no_rf": False,
    "max_drawdown_pct": False,
    "annual_volatility_pct": True,
    "trades": True,
}
OPTIMIZABLE_PARAMETERS = (
    ("trend.short_window", "int", 1.0),
    ("trend.medium_window", "int", 1.0),
    ("trend.long_window", "int", 1.0),
    ("trend.confirmation_days", "int", 1.0),
    ("trend.exposure.below_long", "float", 0.0),
    ("trend.exposure.above_long", "float", 0.0),
    ("trend.exposure.medium_above_long", "float", 0.0),
    ("trend.exposure.short_above_medium_above_long", "float", 0.0),
    ("position.max_exposure", "float", 0.0),
    ("position.rebalance_threshold", "float", 0.0),
)


def run_backtest(
    price: pd.Series,
    vix: pd.Series,
    settings_raw: dict,
    *,
    open_price: pd.Series | None = None,
    leveraged_price: pd.Series | None = None,
    leveraged_open_price: pd.Series | None = None,
    result_start: str | pd.Timestamp | None = None,
) -> BacktestResult:
    signals = signal_frame(price, vix, settings_raw)
    result_start_ts = pd.Timestamp(result_start) if result_start is not None else None
    daily_returns = signals["price"].pct_change().fillna(0.0)
    cash_daily = float(settings_raw["backtest"]["annual_cash_return"]) / 252.0
    ma120_timing_targets = _ma120_timing_targets(signals["price"])
    leveraged_ma120_timing_targets = _price_above_ma120_targets(signals["price"])
    intraday_returns = _intraday_returns(signals["price"], open_price)
    overnight_returns = ((1.0 + daily_returns) / (1.0 + intraday_returns) - 1.0).fillna(0.0)
    initial_capital = float(settings_raw["backtest"]["initial_capital"])
    leveraged_fee_daily = float(settings_raw["backtest"]["annual_leveraged_fee"]) / 252.0
    leveraged_daily_returns = _leveraged_returns(
        signals.index,
        daily_returns,
        settings_raw,
        leveraged_fee_daily,
        leveraged_price,
    )
    leveraged_intraday_returns = (
        _actual_intraday_returns(
            signals.index,
            leveraged_price,
            leveraged_open_price,
            intraday_returns,
            settings_raw,
            leveraged_fee_daily,
        )
        if leveraged_price is not None
        else None
    )
    leveraged_overnight_returns = (
        ((1.0 + leveraged_daily_returns) / (1.0 + leveraged_intraday_returns) - 1.0).fillna(0.0)
        if leveraged_intraday_returns is not None
        else None
    )
    threshold = float(settings_raw["position"]["rebalance_threshold"])
    execution_timing = _execution_timing(settings_raw)
    weekly_contribution = float(settings_raw.get("backtest", {}).get("weekly_contribution", 0.0))

    capital = initial_capital
    benchmark_capital = initial_capital
    leveraged_buy_hold_capital = initial_capital
    ma120_timing_capital = initial_capital
    leveraged_ma120_timing_capital = initial_capital
    current_core = 0.0
    current_lev = 0.0
    current_cash = 100.0
    current_local = 0.0
    # When going 1x→3x the SPXL buy executes at the next US open (not overnight).
    # These pending_* fields hold the post-buy allocation until that open arrives.
    pending_core: float | None = None
    pending_lev: float | None = None
    pending_local: float | None = None
    pending_cash: float | None = None
    last_rebalance_week: tuple[int, int] | None = None
    ma120_timing_invested = True
    ma120_pending_open_invested: bool | None = None
    leveraged_ma120_timing_invested = True
    leveraged_ma120_pending_open_invested: bool | None = None
    rows = []
    trades = []
    result_has_started = False
    last_contribution_week: tuple[int, int] | None = None

    for dt, row in signals.iterrows():
        include_result = result_start_ts is None or dt >= result_start_ts
        first_result_row = include_result and not result_has_started
        iso = dt.isocalendar()
        week_key = (int(iso.year), int(iso.week))
        contribution_applied = 0.0
        if include_result and first_result_row:
            last_contribution_week = week_key
        elif include_result and weekly_contribution > 0.0 and week_key != last_contribution_week:
            contribution_applied = weekly_contribution
            capital += contribution_applied
            benchmark_capital += contribution_applied
            leveraged_buy_hold_capital += contribution_applied
            ma120_timing_capital += contribution_applied
            leveraged_ma120_timing_capital += contribution_applied
            last_contribution_week = week_key
        target = float(row["target_exposure"])

        if execution_timing == "same_close":
            current_core, current_lev, current_local, current_cash, last_rebalance_week = _rebalance_if_needed(
                dt,
                row,
                target,
                capital,
                current_core,
                current_lev,
                current_local,
                current_cash,
                last_rebalance_week,
                week_key,
                threshold,
                settings_raw,
                trades if include_result else [],
            )

        leverage_multiple_float = float(settings_raw["execution"]["leverage_multiple"])

        # For nz_close_us_open, a pending 1x→3x rebalance takes effect at the US open
        # (intraday), not overnight.  Resolve it here so overnight uses pre-buy positions
        # and intraday uses post-buy positions.
        if execution_timing == "nz_close_us_open" and pending_core is not None:
            intraday_core = pending_core
            intraday_lev = pending_lev
            intraday_local = pending_local
            intraday_cash = pending_cash
        else:
            intraday_core = current_core
            intraday_lev = current_lev
            intraday_local = current_local
            intraday_cash = current_cash

        overnight_exposure_for_return = current_core + current_lev * leverage_multiple_float
        intraday_exposure_for_return = intraday_core + intraday_lev * leverage_multiple_float
        equivalent_exposure_for_return = intraday_exposure_for_return
        local_defensive_for_return = intraday_local

        r = float(daily_returns.loc[dt])
        leveraged_return = float(leveraged_daily_returns.loc[dt])
        leveraged_buy_hold_return = leveraged_return
        ma120_timing_target = bool(ma120_timing_targets.loc[dt])
        leveraged_ma120_timing_target = bool(leveraged_ma120_timing_targets.loc[dt])
        if execution_timing == "same_close":
            ma120_timing_invested = ma120_timing_target
            leveraged_ma120_timing_invested = leveraged_ma120_timing_target
        if execution_timing == "nz_close_us_open":
            overnight_return = float(overnight_returns.loc[dt])
            intraday_return = float(intraday_returns.loc[dt])
            leveraged_overnight_return = (
                float(leveraged_overnight_returns.loc[dt])
                if leveraged_overnight_returns is not None
                else leveraged_fee_daily
            )
            leveraged_intraday_return = (
                float(leveraged_intraday_returns.loc[dt])
                if leveraged_intraday_returns is not None
                else leveraged_fee_daily
            )
            # Overnight: SPXL held at full leverage (steady-state 3x is maintained
            # overnight; only the transition night uses pre-buy positions via pending).
            overnight_portfolio_return = _portfolio_return(
                current_core,
                current_lev,
                current_local,
                current_cash,
                overnight_return,
                leveraged_overnight_return,
                cash_daily,
                settings_raw,
                leveraged_return_is_actual=leveraged_overnight_returns is not None,
            )
            # Intraday: post-pending positions (SPXL bought at US open on transition day).
            intraday_portfolio_return = _portfolio_return(
                intraday_core,
                intraday_lev,
                intraday_local,
                intraday_cash,
                intraday_return,
                leveraged_intraday_return,
                cash_daily,
                settings_raw,
                leveraged_return_is_actual=leveraged_intraday_returns is not None,
            )
            portfolio_return = (1.0 + overnight_portfolio_return) * (1.0 + intraday_portfolio_return) - 1.0
        else:
            portfolio_return = _portfolio_return(
                current_core,
                current_lev,
                current_local,
                current_cash,
                r,
                leveraged_return if leveraged_price is not None else leveraged_fee_daily,
                cash_daily,
                settings_raw,
                leveraged_return_is_actual=leveraged_price is not None,
            )
        ma120_timing_return = _ma120_timing_return(
            ma120_timing_invested,
            ma120_pending_open_invested,
            r,
            float(overnight_returns.loc[dt]),
            float(intraday_returns.loc[dt]),
            cash_daily,
            execution_timing,
        )
        leveraged_overnight_for_timing = (
            float(leveraged_overnight_returns.loc[dt])
            if leveraged_overnight_returns is not None
            else float(overnight_returns.loc[dt]) * float(settings_raw["execution"]["leverage_multiple"])
            - leveraged_fee_daily
        )
        leveraged_intraday_for_timing = (
            float(leveraged_intraday_returns.loc[dt])
            if leveraged_intraday_returns is not None
            else float(intraday_returns.loc[dt]) * float(settings_raw["execution"]["leverage_multiple"])
            - leveraged_fee_daily
        )
        leveraged_ma120_timing_return = _timing_return(
            leveraged_ma120_timing_invested,
            leveraged_ma120_pending_open_invested,
            leveraged_return,
            leveraged_overnight_for_timing,
            leveraged_intraday_for_timing,
            cash_daily,
            execution_timing,
        )
        if include_result and not first_result_row:
            capital *= 1.0 + portfolio_return
            benchmark_capital *= 1.0 + r
            leveraged_buy_hold_capital *= 1.0 + leveraged_buy_hold_return
            ma120_timing_capital *= 1.0 + ma120_timing_return
            leveraged_ma120_timing_capital *= 1.0 + leveraged_ma120_timing_return

        # After intraday returns are applied, promote the pending positions to current
        # so that the rebalance check and future overnights use the correct state.
        if execution_timing == "nz_close_us_open" and pending_core is not None:
            current_core, current_lev = pending_core, pending_lev
            current_local, current_cash = pending_local, pending_cash
            pending_core = pending_lev = pending_local = pending_cash = None

        if execution_timing == "next_session":
            ma120_timing_invested = ma120_timing_target
            leveraged_ma120_timing_invested = leveraged_ma120_timing_target
            current_core, current_lev, current_local, current_cash, last_rebalance_week = _rebalance_if_needed(
                dt,
                row,
                target,
                capital,
                current_core,
                current_lev,
                current_local,
                current_cash,
                last_rebalance_week,
                week_key,
                threshold,
                settings_raw,
                trades if include_result else [],
            )
        elif execution_timing == "nz_close_us_open":
            if ma120_pending_open_invested is not None:
                ma120_timing_invested = ma120_pending_open_invested
                ma120_pending_open_invested = None
            if leveraged_ma120_pending_open_invested is not None:
                leveraged_ma120_timing_invested = leveraged_ma120_pending_open_invested
                leveraged_ma120_pending_open_invested = None
            if ma120_timing_target and not ma120_timing_invested:
                ma120_pending_open_invested = True
            elif not ma120_timing_target and ma120_timing_invested:
                ma120_timing_invested = False
            if leveraged_ma120_timing_target and not leveraged_ma120_timing_invested:
                leveraged_ma120_pending_open_invested = True
            elif not leveraged_ma120_timing_target and leveraged_ma120_timing_invested:
                leveraged_ma120_timing_invested = False
            rebalance = _rebalance_target_if_needed(
                dt,
                row,
                target,
                capital,
                current_core,
                current_lev,
                current_local,
                current_cash,
                last_rebalance_week,
                week_key,
                threshold,
                settings_raw,
                execution_timing,
            )
            if rebalance is not None:
                new_core, new_lev, new_local, new_cash = rebalance[:4]
                last_rebalance_week = week_key
                if include_result:
                    trades.append(rebalance[4])
                if new_lev > current_lev:
                    # Buying SPXL: order placed at next US open → pending until intraday.
                    pending_core, pending_lev = new_core, new_lev
                    pending_local, pending_cash = new_local, new_cash
                else:
                    # Selling SPXL (or no leverage change): executed at US close →
                    # new positions are in effect from the next overnight onward.
                    current_core, current_lev = new_core, new_lev
                    current_local, current_cash = new_local, new_cash

        if include_result:
            row_portfolio_return = 0.0 if first_result_row else portfolio_return
            row_market_return = 0.0 if first_result_row else r
            row_leveraged_buy_hold_return = 0.0 if first_result_row else leveraged_buy_hold_return
            row_ma120_timing_return = 0.0 if first_result_row else ma120_timing_return
            row_leveraged_ma120_timing_return = 0.0 if first_result_row else leveraged_ma120_timing_return
            rows.append(
                {
                    "date": dt,
                    "equity": capital,
                    "buy_hold_equity": benchmark_capital,
                    "leveraged_buy_hold_equity": leveraged_buy_hold_capital,
                    "ma120_timing_equity": ma120_timing_capital,
                    "leveraged_ma120_timing_equity": leveraged_ma120_timing_capital,
                    "daily_return": row_portfolio_return,
                    "buy_hold_daily_return": row_market_return,
                    "leveraged_buy_hold_daily_return": row_leveraged_buy_hold_return,
                    "ma120_timing_daily_return": row_ma120_timing_return,
                    "leveraged_ma120_timing_daily_return": row_leveraged_ma120_timing_return,
                    "weekly_contribution": contribution_applied,
                    "target_exposure": target,
                    "actual_equivalent_exposure": equivalent_exposure_for_return,
                    "overnight_equivalent_exposure": overnight_exposure_for_return,
                    "intraday_equivalent_exposure": intraday_exposure_for_return,
                    "post_close_equivalent_exposure": _post_close_equivalent_exposure(
                        current_core,
                        current_lev,
                        settings_raw,
                        execution_timing,
                    ),
                    "pending_next_open_equivalent_exposure": _next_open_equivalent_exposure(
                        pending_core if pending_core is not None else current_core,
                        pending_lev if pending_lev is not None else current_lev,
                        settings_raw,
                    ),
                    "local_defensive_percent": local_defensive_for_return,
                    "post_close_local_defensive_percent": current_local,
                    "trend_label": row["trend_label"],
                    "vix_label": row["vix_label"],
                }
            )
            result_has_started = True

    equity_curve = pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame()
    trades_frame = pd.DataFrame(trades)
    return BacktestResult(
        equity_curve=equity_curve,
        trades=trades_frame,
        metrics=_metrics(equity_curve),
    )


def run_parameter_sweep(
    price: pd.Series,
    vix: pd.Series,
    settings_raw: dict,
    *,
    open_price: pd.Series | None = None,
    result_start: str | pd.Timestamp | None = None,
    baseline_settings: dict | None = None,
    sort_metric: str = "total_return_pct",
    factors: tuple[float, ...] = SWEEP_FACTORS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    baseline = run_backtest(price, vix, settings_raw, open_price=open_price, result_start=result_start)
    baseline_return = float(baseline.metrics.get("total_return_pct", 0.0))
    default_baseline = (
        run_backtest(price, vix, baseline_settings, open_price=open_price, result_start=result_start)
        if baseline_settings is not None
        else None
    )
    default_baseline_return = (
        float(default_baseline.metrics.get("total_return_pct", 0.0))
        if default_baseline is not None
        else baseline_return
    )
    parameter_specs = list(OPTIMIZABLE_PARAMETERS) + _vix_multiplier_specs(settings_raw)
    for path, value_type, minimum in parameter_specs:
        original = _get_setting(settings_raw, path)
        for factor in factors:
            candidate = build_parameter_sweep_candidate(settings_raw, "individual", path, factor)
            value = _get_setting(candidate, path)
            rows.append(
                _sweep_row(
                    "individual",
                    path,
                    factor,
                    original,
                    value,
                    run_backtest(price, vix, candidate, open_price=open_price, result_start=result_start),
                    baseline_return=baseline_return,
                    default_baseline_return=default_baseline_return,
                )
            )

    unified_rows = []
    for factor in factors:
        candidate = build_parameter_sweep_candidate(settings_raw, "unified", "all_parameters", factor)
        changed = []
        for path, value_type, minimum in parameter_specs:
            original = _get_setting(settings_raw, path)
            value = _get_setting(candidate, path)
            changed.append(f"{path}={value}")
        unified_rows.append(
            _sweep_row(
                "unified",
                "all_parameters",
                factor,
                1.0,
                factor,
                run_backtest(price, vix, candidate, open_price=open_price, result_start=result_start),
                note=", ".join(changed),
                baseline_return=baseline_return,
                default_baseline_return=default_baseline_return,
            )
        )

    individual = _sort_sweep_results(pd.DataFrame(rows), sort_metric)
    unified = _sort_sweep_results(pd.DataFrame(unified_rows), sort_metric)
    ranges = _preferred_ranges(pd.DataFrame(rows), pd.DataFrame(unified_rows))
    recommendations = _parameter_recommendations(individual, ranges, baseline_return, sort_metric)
    return individual, unified, ranges, recommendations


def build_parameter_sweep_candidate(
    settings_raw: dict,
    mode: str,
    parameter: str,
    factor: float,
) -> dict:
    candidate = deepcopy(settings_raw)
    parameter_specs = list(OPTIMIZABLE_PARAMETERS) + _vix_multiplier_specs(settings_raw)
    if mode == "individual":
        specs = [spec for spec in parameter_specs if spec[0] == parameter]
    elif mode == "unified":
        specs = parameter_specs
    else:
        specs = []
    for path, value_type, minimum in specs:
        original = _get_setting(settings_raw, path)
        _set_setting(
            candidate,
            path,
            _scaled_value(
                original,
                factor,
                value_type,
                minimum,
                _parameter_maximum(path, settings_raw),
            ),
        )
    return candidate


def _sort_sweep_results(frame: pd.DataFrame, sort_metric: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    metric = sort_metric if sort_metric in frame.columns else "total_return_pct"
    ascending = SWEEP_SORT_DIRECTIONS.get(metric, False)
    secondary = "total_return_pct" if metric != "total_return_pct" else "cagr_pct"
    return frame.sort_values([metric, secondary], ascending=[ascending, False])


def _vix_multiplier_specs(settings_raw: dict) -> list[tuple[str, str, float]]:
    return [
        (f"vix.rules.{index}.multiplier", "float", 0.0)
        for index, _ in enumerate(settings_raw.get("vix", {}).get("rules", []))
    ]


def _sweep_row(
    mode: str,
    parameter: str,
    factor: float,
    original: Any,
    value: Any,
    result: BacktestResult,
    *,
    note: str = "",
    baseline_return: float = 0.0,
    default_baseline_return: float = 0.0,
) -> dict[str, Any]:
    metrics = result.metrics
    total_return = metrics.get("total_return_pct", 0.0)
    return {
        "mode": mode,
        "parameter": parameter,
        "factor": factor,
        "original_value": original,
        "tested_value": value,
        "total_return_pct": total_return,
        "cagr_pct": metrics.get("cagr_pct", 0.0),
        "max_drawdown_pct": metrics.get("max_drawdown_pct", 0.0),
        "annual_volatility_pct": metrics.get("annual_volatility_pct", 0.0),
        "sharpe_no_rf": metrics.get("sharpe_no_rf", 0.0),
        "trades": len(result.trades),
        "current_baseline_delta_pct": round(float(total_return) - baseline_return, 2),
        "default_baseline_delta_pct": round(float(total_return) - default_baseline_return, 2),
        "note": note,
    }


def _preferred_ranges(individual: pd.DataFrame, unified: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for parameter, frame in individual.groupby("parameter", sort=False):
        rows.append(_preferred_range_row("individual", parameter, frame))
    rows.append(_preferred_range_row("unified", "all_parameters", unified))
    return pd.DataFrame(rows).sort_values("best_total_return_pct", ascending=False)


def _preferred_range_row(mode: str, parameter: str, frame: pd.DataFrame) -> dict[str, Any]:
    best = float(frame["total_return_pct"].max())
    threshold = best * 0.95 if best > 0 else best
    preferred = frame[frame["total_return_pct"] >= threshold]
    best_row = frame.sort_values(["total_return_pct", "cagr_pct"], ascending=[False, False]).iloc[0]
    return {
        "mode": mode,
        "parameter": parameter,
        "best_factor": best_row["factor"],
        "best_value": best_row["tested_value"],
        "best_total_return_pct": best,
        "preferred_factor_min": preferred["factor"].min(),
        "preferred_factor_max": preferred["factor"].max(),
        "preferred_value_min": preferred["tested_value"].min(),
        "preferred_value_max": preferred["tested_value"].max(),
    }


def _parameter_recommendations(
    individual: pd.DataFrame,
    ranges: pd.DataFrame,
    baseline_return: float,
    sort_metric: str = "total_return_pct",
) -> pd.DataFrame:
    rows = []
    individual_ranges = ranges[ranges["mode"] == "individual"].set_index("parameter")
    for parameter, frame in individual.groupby("parameter", sort=False):
        best_row = frame.sort_values(["total_return_pct", "cagr_pct"], ascending=[False, False]).iloc[0]
        factor = float(best_row["factor"])
        current = best_row["original_value"]
        best_value = best_row["tested_value"]
        impact = float(best_row["total_return_pct"]) - baseline_return
        range_row = individual_ranges.loc[parameter]
        rows.append(
            {
                "parameter": parameter,
                "current_value": current,
                "recommended_value": best_value,
                "recommended_direction": _recommendation_direction(factor),
                "recommended_action": _recommendation_action(factor, impact, sort_metric),
                "sort_metric": sort_metric,
                "best_total_return_pct": best_row["total_return_pct"],
                "baseline_delta_pct": round(impact, 2),
                "default_baseline_delta_pct": best_row.get("default_baseline_delta_pct", 0.0),
                "preferred_value_min": range_row["preferred_value_min"],
                "preferred_value_max": range_row["preferred_value_max"],
            }
        )
    return pd.DataFrame(rows).sort_values("baseline_delta_pct", ascending=False)


def _recommendation_direction(factor: float) -> str:
    if factor > 1.0:
        return "increase"
    if factor < 1.0:
        return "decrease"
    return "keep"


def _recommendation_action(factor: float, impact: float, sort_metric: str = "total_return_pct") -> str:
    if abs(factor - 1.0) < 1e-9:
        return "keep current"
    if sort_metric in {"total_return_pct", "cagr_pct"} and impact <= 0:
        return "keep current"
    return f"{_recommendation_direction(factor)} toward {factor:.0%}"


def _get_setting(settings_raw: dict, path: str) -> Any:
    node: Any = settings_raw
    for part in path.split("."):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def _set_setting(settings_raw: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    node: Any = settings_raw
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    last = parts[-1]
    if isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value


def _scaled_value(
    original: Any,
    factor: float,
    value_type: str,
    minimum: float,
    maximum: float | None = None,
) -> int | float:
    value = max(float(original) * factor, minimum)
    if maximum is not None:
        value = min(value, maximum)
    if value_type == "int":
        return max(int(round(value)), int(minimum))
    return round(value, 4)


def _parameter_maximum(path: str, settings_raw: dict) -> float | None:
    maxima = {
        "trend.short_window": 100.0,
        "trend.medium_window": 150.0,
        "trend.long_window": 300.0,
        "trend.confirmation_days": 10.0,
        "position.max_exposure": 300.0,
        "position.rebalance_threshold": 30.0,
    }
    if path.startswith("trend.exposure."):
        return min(float(settings_raw.get("position", {}).get("max_exposure", 300.0)), 300.0)
    if path.startswith("vix.rules.") and path.endswith(".multiplier"):
        return 5.0
    return maxima.get(path)


def _execution_timing(settings_raw: dict) -> str:
    backtest = settings_raw.get("backtest", {})
    timing = backtest.get("execution_timing")
    if timing in {"next_session", "same_close", "nz_close_us_open"}:
        return timing
    return "next_session" if backtest.get("signal_effective_next_day", True) else "same_close"


def _nz_close_us_open_overnight_equivalent_exposure(current_core: float, current_lev: float) -> float:
    # Kept for backward-compatibility; callers inside the loop now compute this
    # directly as current_core + current_lev * leverage_multiple.
    return current_core + current_lev


def _intraday_returns(close: pd.Series, open_price: pd.Series | None) -> pd.Series:
    if open_price is None:
        return close.pct_change().fillna(0.0)
    aligned_open = open_price.reindex(close.index).astype(float)
    returns = (close.astype(float) / aligned_open - 1.0).replace([float("inf"), float("-inf")], pd.NA)
    return returns.fillna(close.pct_change().fillna(0.0))


def _leveraged_returns(
    index: pd.Index,
    market_returns: pd.Series,
    settings_raw: dict,
    leveraged_fee_daily: float,
    leveraged_price: pd.Series | None,
) -> pd.Series:
    synthetic_returns = market_returns * float(settings_raw["execution"]["leverage_multiple"]) - leveraged_fee_daily
    if leveraged_price is None:
        return synthetic_returns

    aligned_price = leveraged_price.astype(float).reindex(index)
    actual_returns = aligned_price.pct_change(fill_method=None)
    has_actual_return = aligned_price.notna() & aligned_price.shift(1).notna()
    return actual_returns.where(has_actual_return, synthetic_returns).fillna(0.0).astype(float)


def _actual_intraday_returns(
    index: pd.Index,
    close: pd.Series | None,
    open_price: pd.Series | None,
    market_intraday_returns: pd.Series,
    settings_raw: dict,
    leveraged_fee_daily: float,
) -> pd.Series:
    synthetic_returns = (
        market_intraday_returns * float(settings_raw["execution"]["leverage_multiple"]) - leveraged_fee_daily
    )
    if close is None or open_price is None:
        return synthetic_returns.reindex(index).fillna(0.0).astype(float)
    aligned_close = close.astype(float).reindex(index)
    aligned_open = open_price.astype(float).reindex(index)
    returns = (aligned_close / aligned_open - 1.0).replace([float("inf"), float("-inf")], pd.NA)
    has_actual_return = aligned_close.notna() & aligned_open.notna()
    return returns.where(has_actual_return, synthetic_returns).fillna(0.0).astype(float)


def _ma120_timing_targets(price: pd.Series) -> pd.Series:
    ma120 = price.rolling(120, min_periods=1).mean()
    ma120_rising = ma120.diff().gt(0.0)
    invested = True
    targets: list[bool] = []
    for dt, value in price.items():
        if float(value) < float(ma120.loc[dt]):
            invested = False
        elif not invested and bool(ma120_rising.loc[dt]):
            invested = True
        targets.append(invested)
    return pd.Series(targets, index=price.index)


def _price_above_ma120_targets(price: pd.Series) -> pd.Series:
    ma120 = price.rolling(120, min_periods=1).mean()
    return (price >= ma120).astype(bool)


def _ma120_timing_return(
    invested: bool,
    pending_open_invested: bool | None,
    daily_return: float,
    overnight_return: float,
    intraday_return: float,
    cash_daily: float,
    execution_timing: str,
) -> float:
    return _timing_return(
        invested,
        pending_open_invested,
        daily_return,
        overnight_return,
        intraday_return,
        cash_daily,
        execution_timing,
    )


def _timing_return(
    invested: bool,
    pending_open_invested: bool | None,
    daily_return: float,
    overnight_return: float,
    intraday_return: float,
    cash_daily: float,
    execution_timing: str,
) -> float:
    if execution_timing == "nz_close_us_open" and pending_open_invested is not None:
        overnight_leg = overnight_return if invested else cash_daily
        intraday_leg = intraday_return if pending_open_invested else cash_daily
        return (1.0 + overnight_leg) * (1.0 + intraday_leg) - 1.0
    return daily_return if invested else cash_daily


def _portfolio_return(
    current_core: float,
    current_lev: float,
    current_local: float,
    current_cash: float,
    market_return: float,
    leveraged_return_or_fee: float,
    cash_daily: float,
    settings_raw: dict,
    *,
    leveraged_return_is_actual: bool = False,
) -> float:
    leveraged_return = (
        leveraged_return_or_fee
        if leveraged_return_is_actual
        else market_return * float(settings_raw["execution"]["leverage_multiple"]) - leveraged_return_or_fee
    )
    return (
        (current_core / 100.0) * market_return
        + (current_lev / 100.0) * leveraged_return
        + (current_local / 100.0) * cash_daily
        + (current_cash / 100.0) * cash_daily
    )


def _rebalance_if_needed(
    dt: pd.Timestamp,
    row: pd.Series,
    target: float,
    capital: float,
    current_core: float,
    current_lev: float,
    current_local: float,
    current_cash: float,
    last_rebalance_week: tuple[int, int] | None,
    week_key: tuple[int, int],
    threshold: float,
    settings_raw: dict,
    trades: list[dict],
) -> tuple[float, float, float, float, tuple[int, int] | None]:
    rebalance = _rebalance_target_if_needed(
        dt,
        row,
        target,
        capital,
        current_core,
        current_lev,
        current_local,
        current_cash,
        last_rebalance_week,
        week_key,
        threshold,
        settings_raw,
        _execution_timing(settings_raw),
    )
    if rebalance is None:
        return current_core, current_lev, current_local, current_cash, last_rebalance_week
    trades.append(rebalance[4])
    return rebalance[0], rebalance[1], rebalance[2], rebalance[3], week_key


def _rebalance_target_if_needed(
    dt: pd.Timestamp,
    row: pd.Series,
    target: float,
    capital: float,
    current_core: float,
    current_lev: float,
    current_local: float,
    current_cash: float,
    last_rebalance_week: tuple[int, int] | None,
    week_key: tuple[int, int],
    threshold: float,
    settings_raw: dict,
    execution_timing: str,
) -> tuple[float, float, float, float, dict] | None:
    current_equivalent = current_core + current_lev * float(settings_raw["execution"]["leverage_multiple"])
    change = abs(target - current_equivalent)
    frequency_allows_rebalance = execution_timing == "nz_close_us_open" or last_rebalance_week != week_key
    may_rebalance = frequency_allows_rebalance and change >= threshold

    if not may_rebalance:
        return None

    allocation = build_allocation(target, float(row["vix"]), settings_raw)
    target_weights = {
        allocation.core_asset: allocation.core_percent,
        allocation.defensive_asset: allocation.defensive_percent,
    }
    if allocation.leveraged_asset:
        target_weights[allocation.leveraged_asset] = allocation.leveraged_percent
    cap_note = apply_foreign_asset_cap_to_weights(
        target_weights,
        settings_raw,
        portfolio_value_nzd=capital,
    )
    current_core = target_weights.get(allocation.core_asset, 0.0)
    current_lev = target_weights.get(allocation.leveraged_asset, 0.0) if allocation.leveraged_asset else 0.0
    current_local = target_weights.get(allocation.defensive_asset, 0.0)
    current_cash = max(0.0, 100.0 - sum(target_weights.values()))
    trade = {
        "date": dt,
        "execution_timing": execution_timing,
        "target_exposure": target,
        "core_percent": current_core,
        "leveraged_percent": current_lev,
        "local_defensive_percent": current_local,
        "cash_percent": current_cash,
        "trend_label": row["trend_label"],
        "vix": row["vix"],
        "cap_note": cap_note or "",
    }
    return current_core, current_lev, current_local, current_cash, trade


def _post_close_equivalent_exposure(
    current_core: float,
    current_lev: float,
    settings_raw: dict,
    execution_timing: str,
) -> float:
    return current_core + current_lev * float(settings_raw["execution"]["leverage_multiple"])


def _next_open_equivalent_exposure(
    current_core: float,
    current_lev: float,
    settings_raw: dict,
) -> float:
    return current_core + current_lev * float(settings_raw["execution"]["leverage_multiple"])


def _metrics(equity_curve: pd.DataFrame) -> dict[str, float]:
    if equity_curve.empty:
        return {}
    daily = equity_curve["daily_return"]
    benchmark_daily = equity_curve["buy_hold_daily_return"]
    years = len(equity_curve) / 252.0
    total_return = (1.0 + daily).prod() - 1.0
    benchmark_total_return = (1.0 + benchmark_daily).prod() - 1.0
    cagr = (1.0 + total_return) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    benchmark_cagr = (
        (1.0 + benchmark_total_return) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    )
    running_max = equity_curve["equity"].cummax()
    drawdown = equity_curve["equity"] / running_max - 1.0
    benchmark_running_max = equity_curve["buy_hold_equity"].cummax()
    benchmark_drawdown = equity_curve["buy_hold_equity"] / benchmark_running_max - 1.0
    volatility = daily.std() * (252.0**0.5)
    benchmark_volatility = benchmark_daily.std() * (252.0**0.5)
    sharpe = (daily.mean() * 252.0) / volatility if volatility else 0.0
    benchmark_sharpe = (
        (benchmark_daily.mean() * 252.0) / benchmark_volatility if benchmark_volatility else 0.0
    )
    return {
        "total_return_pct": round(total_return * 100.0, 2),
        "cagr_pct": round(cagr * 100.0, 2),
        "max_drawdown_pct": round(drawdown.min() * 100.0, 2),
        "annual_volatility_pct": round(volatility * 100.0, 2),
        "sharpe_no_rf": round(sharpe, 2),
        "buy_hold_total_return_pct": round(benchmark_total_return * 100.0, 2),
        "buy_hold_cagr_pct": round(benchmark_cagr * 100.0, 2),
        "buy_hold_max_drawdown_pct": round(benchmark_drawdown.min() * 100.0, 2),
        "buy_hold_annual_volatility_pct": round(benchmark_volatility * 100.0, 2),
        "buy_hold_sharpe_no_rf": round(benchmark_sharpe, 2),
    }
