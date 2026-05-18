from __future__ import annotations

from types import SimpleNamespace

from trend_system.interfaces.streamlit.pages.daily_page import (
    _coerce_daily_result,
    _delta_text,
    _state_delta_text,
)
from trend_system.models import DailySignalResult


def test_delta_text_formats_previous_day_change():
    assert _delta_text("zh", 18.43, 19.01) == "较昨 -0.58"
    assert _delta_text("en", 105.0, 100.0, decimals=0, suffix="%") == "vs prev +5%"


def test_state_delta_text_handles_same_and_changed_states():
    assert _state_delta_text("zh", "加速牛市", "加速牛市", "100%", "100%") == "和昨天相同"
    assert _state_delta_text("en", "Low", "High", "18.43", "22.10") == "Prev: High | 22.10"


def test_coerce_daily_result_supports_new_and_legacy_session_shapes():
    signal = SimpleNamespace(trend_label="accelerating_bull")
    allocation = SimpleNamespace(core_percent=100.0)
    previous_signal = SimpleNamespace(trend_label="confirmed_bull")
    previous_allocation = SimpleNamespace(core_percent=75.0)

    result = DailySignalResult(
        signal=signal,
        allocation=allocation,
        previous_signal=previous_signal,
        previous_allocation=previous_allocation,
        report="report",
    )

    assert _coerce_daily_result(result) == (signal, allocation, previous_signal, previous_allocation)
    assert _coerce_daily_result((signal, allocation)) == (signal, allocation, None, None)
