from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd

from trend_system.adapters.market_data.yfinance_client import get_prices
from trend_system.backtest import run_backtest
from trend_system.models import BacktestRequest, BacktestUseCaseResult
from trend_system.signals import history_start_date

PriceLoader = Callable[..., dict[str, pd.DataFrame]]


def run_backtest_use_case(
    request: BacktestRequest,
    *,
    price_loader: PriceLoader = get_prices,
) -> BacktestUseCaseResult:
    settings = request.settings
    data_start = history_start_date(request.start, settings.raw)
    symbols = [settings.primary_symbol, settings.vix_symbol]
    leveraged_symbol = settings.raw["execution"]["leveraged_asset"]
    if request.use_actual_leveraged_returns:
        symbols.append(leveraged_symbol)
    prices = price_loader(
        list(dict.fromkeys(symbols)),
        start=data_start,
        end=_exclusive_end(request.end),
    )
    price_field = settings.price_field
    open_price = prices[settings.primary_symbol].get("Open")
    leveraged_prices = prices.get(leveraged_symbol) if request.use_actual_leveraged_returns else None
    leveraged_price = (
        _price_series(leveraged_prices, price_field)
        if leveraged_prices is not None
        else None
    )
    leveraged_open_price = leveraged_prices.get("Open") if leveraged_prices is not None else None
    result = run_backtest(
        _price_series(prices[settings.primary_symbol], price_field),
        _price_series(prices[settings.vix_symbol], price_field),
        _model_settings(settings.raw),
        open_price=open_price,
        leveraged_price=leveraged_price,
        leveraged_open_price=leveraged_open_price,
        result_start=request.start,
    )
    if request.output is not None:
        request.output.parent.mkdir(parents=True, exist_ok=True)
        result.equity_curve.to_csv(request.output)
    if request.trades_output is not None:
        request.trades_output.parent.mkdir(parents=True, exist_ok=True)
        result.trades.to_csv(request.trades_output, index=False)
    return BacktestUseCaseResult(
        result=result,
        output=request.output,
        trades_output=request.trades_output,
    )


def _exclusive_end(value: str | None) -> str | None:
    if not value:
        return None
    return str(date.fromisoformat(value) + timedelta(days=1))


def _model_settings(settings: dict) -> dict:
    model_settings = deepcopy(settings)
    model_settings.get("backtest", {}).pop("show_leveraged_buy_hold", None)
    model_settings.get("backtest", {}).pop("show_ma120_timing", None)
    model_settings.get("backtest", {}).pop("show_leveraged_ma120_timing", None)
    return model_settings


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
