from __future__ import annotations

from trend_system.config import load_settings
from trend_system.models import FutureModuleRequest
from trend_system.services.future_module_service import prepare_future_module


def test_prepare_future_module_returns_reserved_contract():
    settings = load_settings("config/settings.toml")

    result = prepare_future_module(FutureModuleRequest(settings=settings))

    assert result.module_key == "future_module"
    assert result.enabled is False
    assert result.status == "reserved"
