from trend_system.portfolio import build_allocation


def test_leveraged_allocation_uses_configured_core_percent():
    settings = {
        "execution": {
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "SGOV",
            "leveraged_asset": "UPRO",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        }
    }

    allocation = build_allocation(120.0, 16.0, settings)

    assert allocation.core_percent == 90.0
    assert allocation.leveraged_percent == 10.0
    assert allocation.equivalent_exposure == 120.0


def test_vix_blocks_leverage():
    settings = {
        "execution": {
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "SGOV",
            "leveraged_asset": "UPRO",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        }
    }

    allocation = build_allocation(120.0, 25.0, settings)

    assert allocation.core_percent == 100.0
    assert allocation.leveraged_percent == 0.0
    assert allocation.notes


def test_vix_exposure_cap_mode_keeps_partial_leverage_above_permission_threshold():
    settings = {
        "position": {"vix_exposure_cap_enabled": True},
        "execution": {
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "SGOV",
            "leveraged_asset": "UPRO",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        },
    }

    allocation = build_allocation(200.0, 25.0, settings)

    assert allocation.core_percent == 50.0
    assert allocation.leveraged_percent == 50.0
    assert allocation.equivalent_exposure == 200.0


def test_full_3x_allocation_maps_to_100_percent_leveraged_etf():
    settings = {
        "execution": {
            "core_asset": "VOO",
            "asx_core_asset": "IVV.AX",
            "default_market": "us",
            "defensive_asset": "SGOV",
            "leveraged_asset": "SPXL",
            "leverage_multiple": 3.0,
            "allow_leverage": True,
            "leverage_only_when_vix_below": 20.0,
            "clear_leverage_when_vix_at_or_above": 30.0,
        }
    }

    allocation = build_allocation(300.0, 16.0, settings)

    assert allocation.core_percent == 0.0
    assert allocation.leveraged_percent == 100.0
    assert allocation.equivalent_exposure == 300.0
