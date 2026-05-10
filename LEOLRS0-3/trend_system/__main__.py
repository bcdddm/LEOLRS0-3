from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

from trend_system.backtest import run_backtest
from trend_system.config import load_settings, required_symbols
from trend_system.data import download_prices
from trend_system.portfolio import build_allocation
from trend_system.report import daily_report
from trend_system.signals import history_start_date, latest_signal


def main() -> None:
    parser = argparse.ArgumentParser(prog="trend_system")
    parser.add_argument("--config", default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    daily = subparsers.add_parser("daily")
    daily.add_argument("--config", default=None)
    daily.add_argument("--start", default="2000-01-01")

    backtest = subparsers.add_parser("backtest")
    backtest.add_argument("--config", default=None)
    backtest.add_argument("--start", default=None)
    backtest.add_argument("--end", default=None)
    backtest.add_argument("--output", default="outputs/backtest.csv")
    backtest.add_argument("--trades-output", default="outputs/trades.csv")

    args = parser.parse_args()
    settings = load_settings(args.config or "config/settings.toml")

    if args.command == "daily":
        data_start = history_start_date(args.start, settings.raw)
        prices = download_prices(required_symbols(settings), start=data_start)
        signal = latest_signal(
            prices[settings.primary_symbol][settings.price_field],
            prices[settings.vix_symbol][settings.price_field],
            settings.raw,
        )
        allocation = build_allocation(signal.target_exposure, signal.vix, settings.raw)
        print(daily_report(signal, allocation, settings.raw))
        return

    if args.command == "backtest":
        start = args.start or settings.raw["backtest"]["start"]
        data_start = history_start_date(start, settings.raw)
        prices = download_prices(
            [settings.primary_symbol, settings.vix_symbol],
            start=data_start,
            end=_exclusive_end(args.end),
        )
        result = run_backtest(
            prices[settings.primary_symbol][settings.price_field],
            prices[settings.vix_symbol][settings.price_field],
            settings.raw,
            result_start=start,
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        result.equity_curve.to_csv(output)
        trades_output = Path(args.trades_output)
        trades_output.parent.mkdir(parents=True, exist_ok=True)
        result.trades.to_csv(trades_output, index=False)
        print("Backtest metrics")
        for key, value in result.metrics.items():
            print(f"- {key}: {value}")
        print(f"Rows: {len(result.equity_curve)}")
        print(f"Trades: {len(result.trades)}")
        print(f"Saved equity curve: {output}")
        print(f"Saved trades: {trades_output}")


def _exclusive_end(value: str | None) -> str | None:
    if not value:
        return None
    return str(date.fromisoformat(value) + timedelta(days=1))


if __name__ == "__main__":
    main()
