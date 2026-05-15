from __future__ import annotations

from datetime import date

import pandas as pd

from trend_system.data import download_prices


def get_prices(
    symbols: list[str],
    start: str | date,
    end: str | date | None = None,
    *,
    auto_adjust: bool = True,
) -> dict[str, pd.DataFrame]:
    """Default market-data adapter used by service layer entrypoints."""
    return download_prices(symbols, start=start, end=end, auto_adjust=auto_adjust)
