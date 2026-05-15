from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from trend_system.backtest import BacktestResult
from trend_system.config import Settings
from trend_system.portfolio import Allocation
from trend_system.signals import Signal


@dataclass(frozen=True)
class DailySignalRequest:
    settings: Settings
    start: str | date = "2000-01-01"


@dataclass(frozen=True)
class DailySignalResult:
    signal: Signal
    allocation: Allocation
    previous_signal: Signal | None
    previous_allocation: Allocation | None
    report: str


@dataclass(frozen=True)
class BacktestRequest:
    settings: Settings
    start: str
    end: str | None = None
    use_actual_leveraged_returns: bool = False
    output: Path | None = None
    trades_output: Path | None = None


@dataclass(frozen=True)
class BacktestUseCaseResult:
    result: BacktestResult
    output: Path | None
    trades_output: Path | None


@dataclass(frozen=True)
class HealthcheckRequest:
    settings: Settings
    start: str | date


@dataclass(frozen=True)
class HealthcheckResult:
    symbol: str
    latest_date: date
    latest_price: float
    ma120: float
    ma200: float
    slow_decline: bool
    healthy: bool
    stage: str
    history_start: date
    price: pd.Series


@dataclass(frozen=True)
class FutureModuleRequest:
    settings: Settings
    module_key: str = "future_module"


@dataclass(frozen=True)
class FutureModuleResult:
    module_key: str
    enabled: bool
    status: str
    notes: str
