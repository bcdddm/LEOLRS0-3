from __future__ import annotations

import streamlit as st

from trend_system.interfaces.streamlit.page_registry import (
    build_page_context,
    build_page_specs,
    page_map_by_title,
)


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
    nav_state_key = "app_shell_active_page"
    if st.session_state.get(nav_state_key) not in page_labels:
        st.session_state[nav_state_key] = page_labels[0]

    st.markdown(
        """
<style>
.app-shell-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0.25rem 0 1rem;
}
.app-shell-nav .stButton {
  flex: 1 1 10rem;
}
.app-shell-nav .stButton > button {
  width: 100%;
  border-radius: 999px;
  border: 1px solid rgba(174, 143, 84, 0.30);
  background: rgba(244, 240, 232, 0.10);
  color: rgba(26, 29, 31, 0.70);
  font-weight: 600;
  font-size: 0.80rem;
  letter-spacing: 0.04em;
  padding: 0.55rem 0.9rem;
  transition: border-color 140ms ease, background 140ms ease, color 140ms ease;
}
.app-shell-nav .stButton > button:hover {
  border-color: rgba(18, 57, 91, 0.55);
  background: rgba(18, 57, 91, 0.07);
  color: rgb(18, 57, 91);
}
.app-shell-nav .stButton > button[kind="primary"] {
  background: linear-gradient(135deg, rgba(18, 57, 91, 0.14), rgba(18, 57, 91, 0.26));
  border-color: rgba(18, 57, 91, 0.55);
  color: rgb(18, 57, 91);
  font-weight: 700;
}
@media (prefers-color-scheme: dark) {
  .app-shell-nav .stButton > button {
    background: rgba(255, 255, 255, 0.05);
    color: rgba(244, 240, 232, 0.65);
    border-color: rgba(174, 143, 84, 0.22);
  }
  .app-shell-nav .stButton > button:hover {
    background: rgba(18, 57, 91, 0.18);
    border-color: rgba(18, 57, 91, 0.55);
    color: rgba(244, 240, 232, 0.92);
  }
  .app-shell-nav .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, rgba(18, 57, 91, 0.28), rgba(18, 57, 91, 0.44));
    color: rgba(244, 240, 232, 0.92);
    border-color: rgba(18, 57, 91, 0.65);
  }
}
</style>
""",
        unsafe_allow_html=True,
    )
    nav_cols = st.columns(len(page_labels))
    for index, label in enumerate(page_labels):
        active = st.session_state[nav_state_key] == label
        if nav_cols[index].button(
            label,
            key=f"app_shell_nav_{index}",
            use_container_width=True,
            type="primary" if active else "secondary",
        ):
            st.session_state[nav_state_key] = label

    page = st.session_state[nav_state_key]
    context = build_page_context(settings, language, config_path)
    page_options[page].renderer(context)
