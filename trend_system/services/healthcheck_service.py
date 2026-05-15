from __future__ import annotations

from typing import Callable

import pandas as pd

from trend_system.adapters.market_data.yfinance_client import get_prices
from trend_system.models import HealthcheckRequest, HealthcheckResult
from trend_system.signals import history_start_date

PriceLoader = Callable[..., dict[str, pd.DataFrame]]


def run_healthcheck(
    request: HealthcheckRequest,
    *,
    price_loader: PriceLoader = get_prices,
) -> HealthcheckResult:
    settings = request.settings
    primary = settings.primary_symbol
    data_start = history_start_date(request.start, settings.raw, include_market_health=True)
    prices = price_loader([primary], start=data_start)
    price_field = settings.price_field
    price = _price_series(prices[primary], price_field).dropna()
    if price.empty:
        raise RuntimeError("No usable price data returned for health check.")

    ma120 = price.rolling(120, min_periods=1).mean()
    ma200 = price.rolling(200, min_periods=1).mean()
    latest_price = float(price.iloc[-1])
    latest_ma120 = float(ma120.iloc[-1])
    latest_ma200 = float(ma200.iloc[-1])
    slow_decline = latest_ma120 < latest_ma200
    healthy = latest_ma120 > latest_ma200
    if slow_decline:
        stage = "warning"
    elif healthy:
        stage = "recovery"
    else:
        stage = "neutral"

    return HealthcheckResult(
        symbol=primary,
        latest_date=price.index[-1].date(),
        latest_price=latest_price,
        ma120=latest_ma120,
        ma200=latest_ma200,
        slow_decline=slow_decline,
        healthy=healthy,
        stage=stage,
        history_start=data_start,
        price=price,
    )


def _price_series(frame: pd.DataFrame, price_field: str) -> pd.Series:
    if price_field in frame.columns:
        return frame[price_field]
    if "Close" in frame.columns:
        return frame["Close"]
    raise KeyError(f"Price field '{price_field}' not found in downloaded data.")
