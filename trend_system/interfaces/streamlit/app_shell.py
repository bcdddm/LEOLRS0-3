from __future__ import annotations

import streamlit as st

from trend_system.interfaces.streamlit.page_registry import (
    build_page_context,
    build_page_specs,
    page_map_by_title,
)
from trend_system.interfaces.streamlit.shared.session_state import SessionKeys


def _set_active_page(nav_state_key: str, label: str) -> None:
    st.session_state[nav_state_key] = label


def render_sidebar_navigation(
    sidebar_container,
    *,
    language: str,
    daily_renderer,
    market_health_renderer,
    backtest_renderer,
    settings_renderer,
) -> None:
    page_specs = build_page_specs(
        daily_renderer=daily_renderer,
        market_health_renderer=market_health_renderer,
        backtest_renderer=backtest_renderer,
        settings_renderer=settings_renderer,
    )
    page_options = page_map_by_title(page_specs, language=language)
    page_labels = list(page_options)
    nav_state_key = SessionKeys.SHELL_ACTIVE_PAGE
    if st.session_state.get(nav_state_key) not in page_labels:
        st.session_state[nav_state_key] = page_labels[0]

    with sidebar_container.container(key="app_shell_sidebar_nav"):
        st.caption("Navigation")
        for index, label in enumerate(page_labels):
            active = st.session_state[nav_state_key] == label
            if st.button(
                label,
                key=f"app_shell_sidebar_nav_{index}",
                use_container_width=True,
                type="primary" if active else "secondary",
            ):
                st.session_state[nav_state_key] = label
                st.rerun()


def render_app_shell(
    *,
    settings: dict,
    language: str,
    config_path: str,
    daily_renderer,
    market_health_renderer,
    backtest_renderer,
    settings_renderer,
) -> None:
    """Render the top-level Streamlit page shell.

    This keeps navigation and page registration outside the legacy `gui.py`
    page implementations so a later UI overhaul can replace the shell
    without rewriting every page renderer at the same time.
    """
    page_specs = build_page_specs(
        daily_renderer=daily_renderer,
        market_health_renderer=market_health_renderer,
        backtest_renderer=backtest_renderer,
        settings_renderer=settings_renderer,
    )
    page_options = page_map_by_title(page_specs, language=language)
    page_labels = list(page_options)
    nav_state_key = SessionKeys.SHELL_ACTIVE_PAGE
    if st.session_state.get(nav_state_key) not in page_labels:
        st.session_state[nav_state_key] = page_labels[0]

    nav_cols = st.columns(len(page_labels))
    for index, label in enumerate(page_labels):
        active = st.session_state[nav_state_key] == label
        nav_cols[index].button(
            label,
            key=f"app_shell_nav_{index}",
            use_container_width=True,
            type="primary" if active else "secondary",
            on_click=_set_active_page,
            args=(nav_state_key, label),
        )

    page = st.session_state[nav_state_key]
    context = build_page_context(settings, language, config_path)
    page_options[page].renderer(context)
