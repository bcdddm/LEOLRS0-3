"""Shared Streamlit helpers used across pages and the app shell."""

from trend_system.interfaces.streamlit.shared.release_notes import (
    release_notes_path,
    release_notes_text,
    render_release_notes,
)
from trend_system.interfaces.streamlit.shared.preparing import preparing_markup, render_preparing
from trend_system.interfaces.streamlit.shared.session_state import (
    SessionKeys,
    get_value,
    has_value,
    migrate_legacy_keys,
    pop_value,
    set_value,
)
from trend_system.interfaces.streamlit.shared.state import fingerprint, is_stale, model_settings
from trend_system.interfaces.streamlit.shared.theme import inject_styles, resolve_theme
from trend_system.interfaces.streamlit.shared.text import option_index, tr, ui_language
from trend_system.interfaces.streamlit.shared.tradingview_chart import (
    build_lightweight_chart_payload,
    render_lightweight_chart,
)
from trend_system.interfaces.streamlit.shared.cobe_globe import build_cobe_globe_html

__all__ = [
    "build_cobe_globe_html",
    "build_lightweight_chart_payload",
    "fingerprint",
    "get_value",
    "has_value",
    "inject_styles",
    "is_stale",
    "model_settings",
    "migrate_legacy_keys",
    "option_index",
    "pop_value",
    "preparing_markup",
    "render_lightweight_chart",
    "render_preparing",
    "release_notes_path",
    "release_notes_text",
    "resolve_theme",
    "render_release_notes",
    "SessionKeys",
    "set_value",
    "tr",
    "ui_language",
]
