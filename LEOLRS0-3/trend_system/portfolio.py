from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Allocation:
    core_asset: str
    core_percent: float
    leveraged_asset: str | None
    leveraged_percent: float
    defensive_asset: str
    defensive_percent: float
    equivalent_exposure: float
    notes: list[str]


def build_allocation(target_exposure: float, vix: float, settings_raw: dict) -> Allocation:
    execution = settings_raw["execution"]
    leverage_multiple = float(execution["leverage_multiple"])
    core_asset = (
        execution["asx_core_asset"]
        if execution.get("default_market") == "asx"
        else execution["core_asset"]
    )
    defensive_asset = _defensive_asset(execution)
    notes: list[str] = []

    allow_leverage = bool(execution["allow_leverage"])
    use_vix_exposure_caps = bool(settings_raw.get("position", {}).get("vix_exposure_cap_enabled", False))
    if vix >= float(execution["clear_leverage_when_vix_at_or_above"]):
        allow_leverage = False
        notes.append("VIX is high enough to clear leveraged exposure.")
    elif not use_vix_exposure_caps and vix >= float(execution["leverage_only_when_vix_below"]):
        allow_leverage = False
        notes.append("VIX is above the leverage permission threshold.")

    if target_exposure <= 100 or not allow_leverage:
        core_percent = min(target_exposure, 100.0)
        defensive_percent = max(0.0, 100.0 - core_percent)
        if target_exposure > 100 and not allow_leverage:
            notes.append("Target exposure was capped to unleveraged core exposure.")
        return Allocation(
            core_asset=core_asset,
            core_percent=round(core_percent, 2),
            leveraged_asset=None,
            leveraged_percent=0.0,
            defensive_asset=defensive_asset,
            defensive_percent=round(defensive_percent, 2),
            equivalent_exposure=round(core_percent, 2),
            notes=notes,
        )

    capped_target = min(target_exposure, leverage_multiple * 100.0)
    if capped_target < target_exposure:
        notes.append("Target exposure exceeded the configured leveraged ETF maximum and was capped.")

    # Fully invested blend: core + leveraged = 100%, core + leverage_multiple*leveraged = target.
    leveraged_percent = (capped_target - 100.0) / (leverage_multiple - 1.0)
    core_percent = 100.0 - leveraged_percent
    total_used = core_percent + leveraged_percent
    defensive_percent = max(0.0, 100.0 - total_used)
    equivalent = core_percent + leveraged_percent * leverage_multiple
    return Allocation(
        core_asset=core_asset,
        core_percent=round(core_percent, 2),
        leveraged_asset=execution["leveraged_asset"],
        leveraged_percent=round(leveraged_percent, 2),
        defensive_asset=defensive_asset,
        defensive_percent=round(defensive_percent, 2),
        equivalent_exposure=round(equivalent, 2),
        notes=notes,
    )


def _defensive_asset(execution: dict) -> str:
    if execution.get("default_market") == "asx":
        return execution.get("au_defensive_asset") or execution["defensive_asset"]
    return execution.get("nz_defensive_asset") or execution["defensive_asset"]
