from __future__ import annotations

import argparse
from pathlib import Path

from trend_system.config import load_settings
from trend_system.models import BacktestRequest, DailySignalRequest
from trend_system.services.backtest_service import run_backtest_use_case
from trend_system.services.daily_signal_service import run_daily_signal


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
        result = run_daily_signal(DailySignalRequest(settings=settings, start=args.start))
        print(result.report)
        return

    if args.command == "backtest":
        service_result = run_backtest_use_case(
            BacktestRequest(
                settings=settings,
                start=args.start or settings.raw["backtest"]["start"],
                end=args.end,
                output=Path(args.output),
                trades_output=Path(args.trades_output),
            )
        )
        result = service_result.result
        print("Backtest metrics")
        for key, value in result.metrics.items():
            print(f"- {key}: {value}")
        print(f"Rows: {len(result.equity_curve)}")
        print(f"Trades: {len(result.trades)}")
        print(f"Saved equity curve: {service_result.output}")
        print(f"Saved trades: {service_result.trades_output}")


if __name__ == "__main__":
    main()
