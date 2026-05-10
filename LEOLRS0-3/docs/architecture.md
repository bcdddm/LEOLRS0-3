# System Architecture

## Module Split

The system is split into small modules so live operation and backtesting use the same rules.

- `config/settings.toml`: all adjustable values, including time zones, tickers, windows, thresholds, and exposure limits.
- `trend_system/config.py`: loads settings and resolves required symbols.
- `trend_system/timezones.py`: converts US and ASX market windows into the user's home time zone.
- `trend_system/data.py`: downloads market data from Yahoo Finance through `yfinance`.
- `trend_system/signals.py`: calculates configured short/medium/long moving averages, trend state, VIX state, and target exposure.
- `trend_system/portfolio.py`: translates target exposure into executable assets such as `VOO`, `IVV.AX`, `UPRO`, and `SGOV`.
- `trend_system/backtest.py`: replays the same signal and allocation rules over history.
- `trend_system/report.py`: formats daily output for manual execution.
- `trend_system/__main__.py`: command line entry point.

## New Zealand Execution Model

Default home time zone is `Pacific/Auckland`.

Signals are generated from US market data after the US session has closed. The output shows US and ASX regular sessions converted into New Zealand local time.

Use these settings to switch execution assumptions:

```toml
[profile]
home_timezone = "Pacific/Auckland"

[execution]
default_market = "us"   # use VOO / UPRO
# default_market = "asx" # use IVV.AX for the core S&P 500 allocation
```

## Adjustable Values

The floating parts of the system live in settings:

- `trend.short_window`, `trend.medium_window`, `trend.long_window`
- `trend.confirmation_days`
- `trend.exposure.*`
- `vix.rules`
- `position.min_exposure`
- `position.max_exposure`
- `position.rebalance_threshold`
- `position.vix_exposure_cap_enabled`
- `position.vix_exposure_caps`
- `position.drawdown_exposure_cap_enabled`
- `position.drawdown_lookback_days`
- `position.drawdown_exposure_caps`
- `position.trend_quality_cap_enabled`
- `position.trend_quality_ma_window`
- `position.trend_quality_slope_lookback_days`
- `execution.core_asset`
- `execution.asx_core_asset`
- `execution.leveraged_asset`
- `execution.leverage_only_when_vix_below`
- `execution.clear_leverage_when_vix_at_or_above`
- `backtest.initial_capital`
- `backtest.annual_cash_return`
- `backtest.annual_leveraged_fee`
- `backtest.use_actual_leveraged_asset_returns`

## Exposure Units

`position.min_exposure` and `position.max_exposure` are equivalent market exposure, not cash weight.

- `100` means roughly 100% S&P 500 exposure.
- `120` means roughly 90% core S&P 500 ETF plus 10% 3x ETF.
- `300` means roughly 100% 3x ETF exposure.
