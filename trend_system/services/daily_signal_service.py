from __future__ import annotations

from typing import Callable

import pandas as pd

from trend_system.adapters.market_data.yfinance_client import get_prices
from trend_system.config import required_symbols
from trend_system.models import DailySignalRequest, DailySignalResult
from trend_system.portfolio import build_allocation
from trend_system.report import daily_report
from trend_system.signals import history_start_date, recent_signals

PriceLoader = Callable[..., dict[str, pd.DataFrame]]


def run_daily_signal(
    request: DailySignalRequest,
    *,
    price_loader: PriceLoader = get_prices,
) -> DailySignalResult:
    settings = request.settings
    data_start = history_start_date(request.start, settings.raw)
    prices = price_loader(required_symbols(settings), start=data_start)
    signals = recent_signals(
        prices[settings.primary_symbol][settings.price_field],
        prices[settings.vix_symbol][settings.price_field],
        settings.raw,
        count=2,
    )
    previous_signal = signals[-2] if len(signals) > 1 else None
    signal = signals[-1]
    allocation = build_allocation(signal.target_exposure, signal.vix, settings.raw)
    previous_allocation = (
        build_allocation(previous_signal.target_exposure, previous_signal.vix, settings.raw)
        if previous_signal is not None
        else None
    )
    report = daily_report(signal, allocation, settings.raw, previous_signal, previous_allocation)
    return DailySignalResult(
        signal=signal,
        allocation=allocation,
        previous_signal=previous_signal,
        previous_allocation=previous_allocation,
        report=report,
    )
