from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class Signal:
    date: pd.Timestamp
    price: float
    ma_short: float
    ma_medium: float
    ma_long: float
    trend_label: str
    trend_exposure: float
    vix: float
    vix_label: str
    vix_multiplier: float
    target_exposure: float
    trend_quality_ma_120: float = 0.0
    trend_quality_ma_200: float = 0.0
    trend_quality_slow_decline: bool = False


def moving_average_frame(price: pd.Series, short: int, medium: int, long: int) -> pd.DataFrame:
    frame = pd.DataFrame({"price": price}).dropna()
    frame["ma_short"] = frame["price"].rolling(short).mean()
    frame["ma_medium"] = frame["price"].rolling(medium).mean()
    frame["ma_long"] = frame["price"].rolling(long).mean()
    return frame.dropna()


def latest_signal(
    price: pd.Series,
    vix: pd.Series,
    settings_raw: dict,
) -> Signal:
    return recent_signals(price, vix, settings_raw, count=1)[-1]


def recent_signals(
    price: pd.Series,
    vix: pd.Series,
    settings_raw: dict,
    *,
    count: int = 2,
) -> list[Signal]:
    frame = signal_frame(price, vix, settings_raw)
    if frame.empty:
        raise RuntimeError("Not enough data to calculate signal.")
    return [_row_to_signal(index, row) for index, row in frame.tail(count).iterrows()]


def required_history_days(settings_raw: dict, *, include_market_health: bool = False) -> int:
    trend = settings_raw.get("trend", {})
    position = settings_raw.get("position", {})
    windows = [
        int(trend.get("short_window", 0)),
        int(trend.get("medium_window", 0)),
        int(trend.get("long_window", 0)),
    ]
    if position.get("drawdown_exposure_cap_enabled", False):
        windows.append(int(position.get("drawdown_lookback_days", 0)))
    if position.get("no_new_high_cap_enabled", False):
        windows.append(
            int(position.get("no_new_high_days", 0))
            + int(position.get("no_new_high_high_window", position.get("no_new_high_days", 0)))
        )
    if position.get("trend_quality_cap_enabled", False):
        windows.append(
            int(position.get("trend_quality_ma_window", 120))
            + int(position.get("trend_quality_slope_lookback_days", 20))
        )
    if position.get("trend_quality_ma_cross_slow_decline_enabled", False) or include_market_health:
        windows.extend([120, 200])
    return max(windows, default=0)


def history_start_date(
    start: str | date | pd.Timestamp,
    settings_raw: dict,
    *,
    include_market_health: bool = False,
) -> date:
    days = required_history_days(settings_raw, include_market_health=include_market_health)
    if days <= 0:
        return pd.Timestamp(start).date()
    return (pd.Timestamp(start) - pd.tseries.offsets.BDay(days)).date()


def signal_frame(price: pd.Series, vix: pd.Series, settings_raw: dict) -> pd.DataFrame:
    trend = settings_raw["trend"]
    position = settings_raw["position"]
    confirmation_days = int(trend.get("confirmation_days", 1))
    days_since_new_high = _days_since_new_high(
        price.dropna(),
        int(position.get("no_new_high_high_window", position.get("no_new_high_days", 0)))
        if position.get("no_new_high_cap_enabled", False)
        else None,
    )
    full_price = price.dropna()
    trend_quality_ma_120 = full_price.rolling(120, min_periods=1).mean()
    trend_quality_ma_200 = full_price.rolling(200, min_periods=1).mean()
    frame = moving_average_frame(
        price,
        short=trend["short_window"],
        medium=trend["medium_window"],
        long=trend["long_window"],
    )
    frame = frame.join(vix.rename("vix"), how="inner").dropna()
    frame["price_above_long_confirmed"] = _confirmed(frame["price"] > frame["ma_long"], confirmation_days)
    frame["price_below_long_confirmed"] = _confirmed(frame["price"] < frame["ma_long"], confirmation_days)
    frame["medium_above_long_confirmed"] = _confirmed(
        frame["ma_medium"] > frame["ma_long"], confirmation_days
    )
    frame["stacked_bull_confirmed"] = _confirmed(
        (frame["ma_short"] > frame["ma_medium"]) & (frame["ma_medium"] > frame["ma_long"]),
        confirmation_days,
    )
    _trend_results = [_trend_state(row, settings_raw) for _, row in frame.iterrows()]
    frame["trend_label"] = [r[0] for r in _trend_results]
    frame["trend_exposure"] = [r[1] for r in _trend_results]
    _vix_results = [_vix_state(float(v), settings_raw) for v in frame["vix"]]
    frame["vix_label"] = [r[0] for r in _vix_results]
    frame["vix_multiplier"] = [r[1] for r in _vix_results]
    frame["trend_quality_ma_120"] = trend_quality_ma_120.reindex(frame.index)
    frame["trend_quality_ma_200"] = trend_quality_ma_200.reindex(frame.index)
    frame["trend_quality_slow_decline"] = frame["trend_quality_ma_120"] < frame["trend_quality_ma_200"]
    exposure_floor = _exposure_floor(frame, position)
    target = _apply_vix_exposure_caps(
        _apply_exposure_tiers(
            (frame["trend_exposure"] * frame["vix_multiplier"]).clip(
                upper=position["max_exposure"],
            ),
            position,
        ),
        frame["vix"],
        position,
    )
    frame["drawdown_pct"] = _drawdown_pct(
        frame["price"],
        int(position.get("drawdown_lookback_days", 252)),
    )
    target = _apply_drawdown_exposure_caps(
        target,
        frame["drawdown_pct"],
        position,
    )
    frame["days_since_new_high"] = days_since_new_high.reindex(frame.index).fillna(0).astype(int)
    target = _apply_no_new_high_exposure_cap(
        target,
        frame["days_since_new_high"],
        position,
    )
    frame["trend_quality_ma"] = frame["price"].rolling(
        int(position.get("trend_quality_ma_window", 120)),
        min_periods=1,
    ).mean()
    frame["trend_quality_ma_slope_pct"] = _trend_quality_ma_slope_pct(
        frame["trend_quality_ma"],
        int(position.get("trend_quality_slope_lookback_days", 20)),
    )
    frame["trend_quality_price_below_ma"] = frame["price"] < frame["trend_quality_ma"]
    capped_target = _apply_trend_quality_exposure_cap(
        target,
        frame,
        position,
    )
    frame["target_exposure"] = capped_target.where(capped_target >= exposure_floor, exposure_floor).clip(
        upper=position["max_exposure"],
    )
    return frame


def _trend_state(row: pd.Series, settings_raw: dict) -> tuple[str, float]:
    exposure = settings_raw["trend"]["exposure"]

    if bool(row["price_below_long_confirmed"]):
        return "risk_off", exposure["below_long"]
    if bool(row["stacked_bull_confirmed"]):
        return "accelerating_bull", exposure["short_above_medium_above_long"]
    if bool(row["medium_above_long_confirmed"]):
        return "confirmed_bull", exposure["medium_above_long"]
    if bool(row["price_above_long_confirmed"]):
        return "allowed", exposure["above_long"]
    if float(row["price"]) < float(row["ma_long"]):
        return "risk_watch", exposure["above_long"]
    return "allowed", exposure["above_long"]


def _vix_state(vix: float, settings_raw: dict) -> tuple[str, float]:
    for rule in settings_raw["vix"]["rules"]:
        min_value = rule.get("min_inclusive", float("-inf"))
        max_value = rule.get("max_exclusive", float("inf"))
        if min_value <= vix < max_value:
            return rule["label"], float(rule["multiplier"])
    raise RuntimeError(f"No VIX rule matched value: {vix}")


def _confirmed(condition: pd.Series, days: int) -> pd.Series:
    if days <= 1:
        return condition.astype(bool)
    return condition.astype(int).rolling(days).sum().fillna(0).ge(days)


def _apply_exposure_tiers(target: pd.Series, position: dict) -> pd.Series:
    if not position.get("fixed_exposure_tiers_enabled", False):
        return target

    tiers = position.get("fixed_exposure_tiers", [0.0, 100.0, 300.0])
    min_exposure = float(position["min_exposure"])
    max_exposure = float(position["max_exposure"])
    allowed_tiers = sorted(
        {
            float(tier)
            for tier in tiers
            if min_exposure <= float(tier) <= max_exposure
        }
    )
    if not allowed_tiers:
        allowed_tiers = [min_exposure]

    def nearest_tier(value: float) -> float:
        return min(allowed_tiers, key=lambda tier: (abs(tier - value), tier))

    return target.apply(nearest_tier)


def _apply_vix_exposure_caps(target: pd.Series, vix: pd.Series, position: dict) -> pd.Series:
    if not position.get("vix_exposure_cap_enabled", False):
        return target

    return _apply_exposure_cap_rules(target, vix, position, "vix_exposure_caps")


def _apply_drawdown_exposure_caps(target: pd.Series, drawdown_pct: pd.Series, position: dict) -> pd.Series:
    if not position.get("drawdown_exposure_cap_enabled", False):
        return target

    return _apply_exposure_cap_rules(target, drawdown_pct, position, "drawdown_exposure_caps")


def _apply_no_new_high_exposure_cap(
    target: pd.Series,
    days_since_new_high: pd.Series,
    position: dict,
) -> pd.Series:
    if not position.get("no_new_high_cap_enabled", False):
        return target

    window = max(int(position.get("no_new_high_days", 100)), 1)
    cap = float(position.get("no_new_high_max_exposure", 100.0))
    capped = target.where(days_since_new_high < window, target.clip(upper=cap))
    return capped


def _apply_trend_quality_exposure_cap(
    target: pd.Series,
    frame: pd.DataFrame,
    position: dict,
) -> pd.Series:
    if not position.get("trend_quality_cap_enabled", False):
        return target

    min_exposure = float(position["min_exposure"])
    rising_threshold = float(position.get("trend_quality_rising_slope_min_pct", 0.5))
    falling_threshold = float(position.get("trend_quality_falling_slope_max_pct", 0.0))
    rising_cap = float(position.get("trend_quality_rising_max_exposure", position["max_exposure"]))
    flat_cap = float(position.get("trend_quality_flat_max_exposure", 220.0))
    falling_cap = float(position.get("trend_quality_falling_max_exposure", 150.0))
    below_ma_cap = float(position.get("trend_quality_below_ma_max_exposure", 100.0))
    ma_cross_enabled = bool(position.get("trend_quality_ma_cross_slow_decline_enabled", False))

    def capped_value(value: float, slope_pct: float, price_below_ma: bool, slow_decline: bool) -> float:
        floor = 0.0 if ma_cross_enabled and slow_decline else min_exposure
        cap = rising_cap
        if slope_pct < falling_threshold:
            cap = falling_cap
        elif slope_pct < rising_threshold:
            cap = flat_cap
        if price_below_ma:
            cap = min(cap, below_ma_cap)
        if ma_cross_enabled and slow_decline:
            cap = min(cap, below_ma_cap)
        return max(floor, min(value, cap))

    return pd.Series(
        [
            capped_value(float(target_value), float(slope_pct), bool(price_below_ma), bool(slow_decline))
            for target_value, slope_pct, price_below_ma, slow_decline in zip(
                target,
                frame["trend_quality_ma_slope_pct"],
                frame["trend_quality_price_below_ma"],
                frame["trend_quality_slow_decline"],
                strict=True,
            )
        ],
        index=target.index,
    )


def _apply_exposure_cap_rules(
    target: pd.Series,
    signal: pd.Series,
    position: dict,
    rules_key: str,
) -> pd.Series:
    caps = position.get(rules_key, [])
    if not caps:
        return target
    def capped_value(value: float, signal_value: float) -> float:
        for rule in caps:
            min_value = rule.get("min_inclusive", float("-inf"))
            max_value = rule.get("max_exclusive", float("inf"))
            if min_value <= signal_value < max_value:
                return min(value, float(rule["max_exposure"]))
        return value

    return pd.Series(
        [
            capped_value(float(target_value), float(signal_value))
            for target_value, signal_value in zip(target, signal, strict=True)
        ],
        index=target.index,
    )


def _drawdown_pct(price: pd.Series, lookback_days: int) -> pd.Series:
    window = max(int(lookback_days), 1)
    rolling_high = price.rolling(window, min_periods=1).max()
    return ((rolling_high - price) / rolling_high * 100.0).fillna(0.0)


def _days_since_new_high(price: pd.Series, window: int | None = None) -> pd.Series:
    window = max(int(window), 1) if window else None
    running_high = (
        price.rolling(window + 1, min_periods=1).max()
        if window is not None
        else price.cummax()
    )
    days = []
    count = 0
    for value, high in zip(price, running_high, strict=True):
        if float(value) >= float(high):
            count = 0
        else:
            count = count + 1 if window is None else min(count + 1, window)
        days.append(count)
    return pd.Series(days, index=price.index)


def _trend_quality_ma_slope_pct(ma: pd.Series, lookback_days: int) -> pd.Series:
    lookback = max(int(lookback_days), 1)
    return (ma / ma.shift(lookback) - 1.0).mul(100.0).fillna(0.0)


def _exposure_floor(frame: pd.DataFrame, position: dict) -> pd.Series:
    floor = pd.Series(float(position["min_exposure"]), index=frame.index)
    if (
        position.get("trend_quality_ma_cross_slow_decline_enabled", False)
        and position.get("trend_quality_slow_decline_zero_floor_enabled", False)
    ):
        floor = floor.where(~frame["trend_quality_slow_decline"], 0.0)
    return floor


def _row_to_signal(date: pd.Timestamp, row: pd.Series) -> Signal:
    return Signal(
        date=date,
        price=float(row["price"]),
        ma_short=float(row["ma_short"]),
        ma_medium=float(row["ma_medium"]),
        ma_long=float(row["ma_long"]),
        trend_label=str(row["trend_label"]),
        trend_exposure=float(row["trend_exposure"]),
        vix=float(row["vix"]),
        vix_label=str(row["vix_label"]),
        vix_multiplier=float(row["vix_multiplier"]),
        target_exposure=float(row["target_exposure"]),
        trend_quality_ma_120=float(row.get("trend_quality_ma_120", 0.0)),
        trend_quality_ma_200=float(row.get("trend_quality_ma_200", 0.0)),
        trend_quality_slow_decline=bool(row.get("trend_quality_slow_decline", False)),
    )
