from __future__ import annotations


def counts_toward_foreign_cap(asset: str) -> bool:
    normalized = asset.strip().upper()
    if not normalized or normalized.startswith("未分配"):
        return False
    if normalized == "CASH":
        return False
    if normalized.endswith((".NZ", ".NZX", ".AX", ".ASX")):
        return False
    return True


def local_overflow_asset(settings_raw: dict) -> str:
    execution = settings_raw["execution"]
    if execution.get("default_market") == "asx":
        return execution.get("au_defensive_asset", "BILL.AX")
    return execution.get("nz_defensive_asset", "NZC.NZ")


def apply_foreign_asset_cap_to_values(
    target_values: dict[str, float],
    settings_raw: dict,
    *,
    portfolio_value_nzd: float | None = None,
) -> str | None:
    execution = settings_raw["execution"]
    if not execution.get(
        "limit_foreign_assets_nzd_value",
        execution.get("limit_usd_assets_nzd_value", False),
    ):
        return None

    limit_nzd = float(
        execution.get(
            "foreign_assets_nzd_limit",
            execution.get("usd_assets_nzd_limit", 50000.0),
        )
    )
    foreign_assets = [
        asset
        for asset in target_values
        if counts_toward_foreign_cap(asset) and not asset.startswith("未分配")
    ]
    foreign_total = sum(target_values[asset] for asset in foreign_assets)
    if foreign_total <= limit_nzd:
        return None

    excess = foreign_total - limit_nzd
    for asset in foreign_assets:
        target_values[asset] *= limit_nzd / foreign_total

    local_asset = local_overflow_asset(settings_raw)
    target_values[local_asset] = target_values.get(local_asset, 0.0) + excess
    if portfolio_value_nzd:
        pct = limit_nzd / portfolio_value_nzd * 100.0
        return f"海外/FIF资产目标市值已限制为 {limit_nzd:,.0f} NZD（约 {pct:.2f}%）；NZX/ASX 标的不计入此限制，超出部分已转入 {local_asset}。"
    return f"海外/FIF资产目标市值已限制为 {limit_nzd:,.0f} NZD；NZX/ASX 标的不计入此限制，超出部分已转入 {local_asset}。"


def apply_foreign_asset_cap_to_weights(
    target_weights: dict[str, float],
    settings_raw: dict,
    *,
    portfolio_value_nzd: float,
) -> str | None:
    if portfolio_value_nzd <= 0:
        return None
    target_values = {
        asset: portfolio_value_nzd * weight / 100.0
        for asset, weight in target_weights.items()
    }
    note = apply_foreign_asset_cap_to_values(
        target_values,
        settings_raw,
        portfolio_value_nzd=portfolio_value_nzd,
    )
    if not note:
        return None
    target_weights.clear()
    target_weights.update(
        {
            asset: value / portfolio_value_nzd * 100.0
            for asset, value in target_values.items()
        }
    )
    return note
