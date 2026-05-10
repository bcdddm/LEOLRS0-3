from __future__ import annotations

from datetime import datetime

from trend_system.portfolio import Allocation
from trend_system.signals import Signal
from trend_system.timezones import market_window


def daily_report(signal: Signal, allocation: Allocation, settings_raw: dict) -> str:
    home_tz = settings_raw["profile"]["home_timezone"]
    trend = settings_raw["trend"]
    ma_label = f"MA{trend['short_window']}/{trend['medium_window']}/{trend['long_window']}"
    us_window = market_window(settings_raw, "us").relevant_local_trading_window(datetime.now())
    asx_window = market_window(settings_raw, "asx").relevant_local_trading_window(datetime.now())
    lines = [
        f"Profile: {settings_raw['profile']['name']} ({home_tz})",
        f"Signal date: {signal.date.date()}",
        "",
        "Market state",
        f"- Price: {signal.price:.2f}",
        f"- {ma_label}: {signal.ma_short:.2f} / {signal.ma_medium:.2f} / {signal.ma_long:.2f}",
        f"- Trend: {signal.trend_label} -> {signal.trend_exposure:.0f}%",
        f"- VIX: {signal.vix:.2f} ({signal.vix_label}, x{signal.vix_multiplier:.2f})",
        f"- Target exposure: {signal.target_exposure:.0f}%",
        "",
        "Execution allocation",
        f"- Core: {allocation.core_percent:.2f}% {allocation.core_asset}",
        f"- Leveraged: {allocation.leveraged_percent:.2f}% {allocation.leveraged_asset or 'none'}",
        f"- Defensive/cash: {allocation.defensive_percent:.2f}% {allocation.defensive_asset}",
        f"- Equivalent exposure: {allocation.equivalent_exposure:.2f}%",
        "",
        "Local trading windows",
        f"- US regular session in your timezone: {us_window[0]:%Y-%m-%d %H:%M} -> {us_window[1]:%Y-%m-%d %H:%M}",
        f"- ASX regular session in your timezone: {asx_window[0]:%Y-%m-%d %H:%M} -> {asx_window[1]:%Y-%m-%d %H:%M}",
    ]
    if allocation.notes:
        lines.extend(["", "Notes"])
        lines.extend(f"- {note}" for note in allocation.notes)
    return "\n".join(lines)
