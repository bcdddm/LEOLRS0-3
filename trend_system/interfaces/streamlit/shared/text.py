from __future__ import annotations

from typing import Any

import streamlit as st

from trend_system.interfaces.streamlit.shared.session_state import SessionKeys


def ui_language(settings: dict[str, Any]) -> str:
    selected = st.session_state.get(SessionKeys.UI_LANGUAGE) or settings.get("ui", {}).get("language", "en")
    return "en" if selected == "en" else "zh"


def tr(language: str, zh: str, en: str) -> str:
    return en if language == "en" else zh


def option_index(options: list[str], value: str) -> int:
    return options.index(value) if value in options else 0
