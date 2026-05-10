from __future__ import annotations

from datetime import date

import pandas as pd


def download_prices(
    symbols: list[str],
    start: str | date,
    end: str | date | None = None,
    *,
    auto_adjust: bool = True,
) -> dict[str, pd.DataFrame]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError(
            "yfinance is required for live data. Install with: pip install -e '.[dev]'"
        ) from exc

    raw = yf.download(
        tickers=symbols,
        start=start,
        end=end,
        auto_adjust=auto_adjust,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    if raw.empty:
        raise RuntimeError("No price data returned. Check tickers, dates, and network access.")

    if len(symbols) == 1:
        symbol = symbols[0]
        if isinstance(raw.columns, pd.MultiIndex) and symbol in raw.columns.get_level_values(0):
            raw = raw[symbol]
        return {symbol: raw.dropna(how="all")}

    prices: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        if symbol in raw.columns.get_level_values(0):
            prices[symbol] = raw[symbol].dropna(how="all")
    return prices
