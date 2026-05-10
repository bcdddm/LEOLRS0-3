from __future__ import annotations

from datetime import datetime

from trend_system.portfolio import Allocation
from trend_system.signals import Signal
from trend_system.timezones import market_window


def daily_report(
    signal: Signal,
    allocation: Allocation,
    settings_raw: dict,
    previous_signal: Signal | None = None,
    previous_allocation: Allocation | None = None,
) -> str:
    home_tz = settings_raw["profile"]["home_timezone"]
    trend = settings_raw["trend"]
    ma_label = f"MA{trend['short_window']}/{trend['medium_window']}/{trend['long_window']}"
    us_window = market_window(settings_raw, "us").relevant_local_trading_window(datetime.now())
    asx_window = market_window(settings_raw, "asx").relevant_local_trading_window(datetime.now())
    lines = _action_summary(signal, allocation, previous_signal, previous_allocation) + [
        "",
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


def _action_summary(
    signal: Signal,
    allocation: Allocation,
    previous_signal: Signal | None,
    previous_allocation: Allocation | None,
) -> list[str]:
    if previous_signal is None or previous_allocation is None:
        return [
            "Action today: REVIEW MANUALLY",
            "- No previous signal is available for comparison.",
        ]

    changes = _allocation_changes(allocation, previous_allocation)
    signal_changes = _signal_changes(signal, previous_signal)
    if changes:
        lines = [
            "Action today: ACTION NEEDED",
            f"- Previous signal date: {previous_signal.date.date()}",
        ]
        lines.extend(f"- {change}" for change in changes)
        if signal_changes:
            lines.append(f"- Signal changed: {'; '.join(signal_changes)}")
        return lines

    lines = [
        "Action today: NO ACTION NEEDED",
        f"- Same execution allocation as previous signal date {previous_signal.date.date()}.",
    ]
    if signal_changes:
        lines.append(f"- Signal changed but allocation is unchanged: {'; '.join(signal_changes)}")
    return lines


def _allocation_changes(current: Allocation, previous: Allocation) -> list[str]:
    fields = [
        ("Core", "core_asset", "core_percent", "%"),
        ("Leveraged", "leveraged_asset", "leveraged_percent", "%"),
        ("Defensive/cash", "defensive_asset", "defensive_percent", "%"),
        ("Equivalent exposure", None, "equivalent_exposure", "%"),
    ]
    changes: list[str] = []
    for label, asset_field, percent_field, suffix in fields:
        current_asset = getattr(current, asset_field) if asset_field else None
        previous_asset = getattr(previous, asset_field) if asset_field else None
        current_value = float(getattr(current, percent_field))
        previous_value = float(getattr(previous, percent_field))
        if current_asset != previous_asset or abs(current_value - previous_value) >= 0.01:
            if asset_field:
                changes.append(
                    f"{label}: {_format_asset_percent(previous_asset, previous_value, suffix)} -> "
                    f"{_format_asset_percent(current_asset, current_value, suffix)}"
                )
            else:
                changes.append(f"{label}: {previous_value:.2f}{suffix} -> {current_value:.2f}{suffix}")
    return changes


def _signal_changes(current: Signal, previous: Signal) -> list[str]:
    changes: list[str] = []
    if current.trend_label != previous.trend_label:
        changes.append(f"trend {previous.trend_label} -> {current.trend_label}")
    if abs(float(current.target_exposure) - float(previous.target_exposure)) >= 0.01:
        changes.append(f"target exposure {previous.target_exposure:.0f}% -> {current.target_exposure:.0f}%")
    if current.vix_label != previous.vix_label:
        changes.append(f"VIX regime {previous.vix_label} -> {current.vix_label}")
    return changes


def _format_asset_percent(asset: str | None, value: float, suffix: str) -> str:
    return f"{value:.2f}{suffix} {asset or 'none'}"
