"""Shared Streamlit helpers used across pages and the app shell."""

from trend_system.interfaces.streamlit.shared.release_notes import (
    release_notes_path,
    release_notes_text,
    render_release_notes,
)
from trend_system.interfaces.streamlit.shared.preparing import preparing_markup, render_preparing
from trend_system.interfaces.streamlit.shared.state import (
    fingerprint,
    is_stale,
    local_today,
    model_settings,
    sync_date_input_default,
)
from trend_system.interfaces.streamlit.shared.text import option_index, tr, ui_language
from trend_system.interfaces.streamlit.shared.tradingview_chart import (
    build_lightweight_chart_payload,
    render_lightweight_chart,
)

__all__ = [
    "build_lightweight_chart_payload",
    "fingerprint",
    "is_stale",
    "local_today",
    "model_settings",
    "option_index",
    "preparing_markup",
    "render_lightweight_chart",
    "render_preparing",
    "release_notes_path",
    "release_notes_text",
    "render_release_notes",
    "sync_date_input_default",
    "tr",
    "ui_language",
]
