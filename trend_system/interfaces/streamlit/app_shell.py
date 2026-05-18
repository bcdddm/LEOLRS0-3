from __future__ import annotations

import streamlit as st

from trend_system.interfaces.streamlit.page_registry import (
    build_page_context,
    build_page_specs,
    page_map_by_title,
)


def _set_active_page(nav_state_key: str, label: str) -> None:
    st.session_state[nav_state_key] = label


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
[class*="st-key-app_shell_burger_row"] {
  display: none;
}
[class*="st-key-app_shell_mobile_row"] {
  display: none;
}
[data-testid="stHorizontalBlock"]:has([class*="st-key-app_shell_nav"]) {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0.25rem 0 1rem;
}
[data-testid="stHorizontalBlock"]:has([class*="st-key-app_shell_nav"]) [data-testid="stColumn"] {
  flex: 1 1 10rem;
}
[data-testid="stHorizontalBlock"]:has([class*="st-key-app_shell_nav"]) [data-testid="stButton"] > button {
  width: 100%;
  border-radius: 0;
  border: 1px solid rgba(174, 143, 84, 0.30);
  background: rgba(244, 240, 232, 0.10);
  color: var(--text-color, rgba(26, 29, 31, 0.70));
  font-weight: 600;
  font-size: 0.80rem;
  letter-spacing: 0.04em;
  padding: 0.55rem 0.9rem;
  transition: border-color 140ms ease, background 140ms ease, color 140ms ease;
}
[data-testid="stHorizontalBlock"]:has([class*="st-key-app_shell_nav"]) [data-testid="stButton"] > button:hover {
  border-color: rgba(18, 57, 91, 0.55);
  background: rgba(18, 57, 91, 0.07);
  color: var(--leo-kicker, rgb(18, 57, 91));
}
[data-testid="stHorizontalBlock"]:has([class*="st-key-app_shell_nav"]) [data-testid="stButton"] > button[kind="primary"] {
  background: linear-gradient(135deg, rgba(18, 57, 91, 0.14), rgba(18, 57, 91, 0.26));
  border-color: rgba(18, 57, 91, 0.55);
  color: var(--text-color, rgb(18, 57, 91));
  font-weight: 700;
}
[data-theme="dark"] [data-testid="stHorizontalBlock"]:has([class*="st-key-app_shell_nav"]) [data-testid="stButton"] > button {
  background: rgba(255, 255, 255, 0.05);
  color: rgba(244, 240, 232, 0.65);
  border-color: rgba(174, 143, 84, 0.22);
}
[data-theme="dark"] [data-testid="stHorizontalBlock"]:has([class*="st-key-app_shell_nav"]) [data-testid="stButton"] > button:hover {
  background: rgba(18, 57, 91, 0.18);
  border-color: rgba(18, 57, 91, 0.55);
  color: rgba(244, 240, 232, 0.92);
}
[data-theme="dark"] [data-testid="stHorizontalBlock"]:has([class*="st-key-app_shell_nav"]) [data-testid="stButton"] > button[kind="primary"] {
  background: linear-gradient(135deg, rgba(18, 57, 91, 0.28), rgba(18, 57, 91, 0.44));
  color: rgba(244, 240, 232, 0.92);
  border-color: rgba(18, 57, 91, 0.65);
}
[class*="st-key-app_shell_burger_row"] [data-testid="stPopover"] > button,
[class*="st-key-app_shell_burger_row"] [data-testid="baseButton-secondary"],
[class*="st-key-app_shell_mobile_row"] [data-testid="stPopover"] > button,
[class*="st-key-app_shell_mobile_row"] [data-testid="baseButton-secondary"] {
  border-radius: 0;
  border: 1px solid rgba(174, 143, 84, 0.30);
  background: rgba(244, 240, 232, 0.10);
  color: var(--text-color, rgba(26, 29, 31, 0.82));
  font-weight: 700;
  min-width: 2.9rem;
  height: 2.55rem;
}
[data-theme="dark"] [class*="st-key-app_shell_burger_row"] [data-testid="stPopover"] > button,
[data-theme="dark"] [class*="st-key-app_shell_burger_row"] [data-testid="baseButton-secondary"],
[data-theme="dark"] [class*="st-key-app_shell_mobile_row"] [data-testid="stPopover"] > button,
[data-theme="dark"] [class*="st-key-app_shell_mobile_row"] [data-testid="baseButton-secondary"] {
  background: rgba(255, 255, 255, 0.05);
  color: rgba(244, 240, 232, 0.92);
  border-color: rgba(174, 143, 84, 0.22);
}
@media (max-width: 640px) {
  [data-testid="stHorizontalBlock"]:has([class*="st-key-app_shell_nav"]) {
    display: none !important;
  }
  [class*="st-key-app_shell_burger_row"] {
    display: none !important;
  }
  [class*="st-key-app_shell_mobile_row"] {
    display: block !important;
    margin: 0.1rem 0 0.75rem;
  }
  [class*="st-key-app_shell_mobile_row"] [data-testid="stHorizontalBlock"] {
    display: grid !important;
    grid-template-columns: minmax(2.75rem, 0.78fr) minmax(0, 1fr) minmax(0, 1fr);
    gap: 0.45rem;
    align-items: center;
  }
  [class*="st-key-app_shell_mobile_row"] [data-testid="stHorizontalBlock"] [data-testid="stColumn"] {
    min-width: 0 !important;
  }
  [class*="st-key-app_shell_mobile_row"] [data-testid="stHorizontalBlock"] [data-testid="stSegmentedControl"] {
    margin: 0 !important;
  }
}
</style>
""",
        unsafe_allow_html=True,
    )
    theme = settings.get("ui", {}).get("theme", "dark")
    mobile_theme_label = "Dark" if theme == "dark" else "Light"
    mobile_language_label = "EN" if language == "en" else "中文"

    with st.container(key="app_shell_mobile_row"):
        mobile_cols = st.columns([0.78, 1, 1], vertical_alignment="center")
        with mobile_cols[0]:
            with st.popover("☰"):
                for index, label in enumerate(page_labels):
                    active = st.session_state[nav_state_key] == label
                    if st.button(
                        label,
                        key=f"app_shell_mobile_burger_{index}",
                        use_container_width=True,
                        type="primary" if active else "secondary",
                    ):
                        st.session_state[nav_state_key] = label
                        st.rerun()
        with mobile_cols[1]:
            selected_mobile_theme = st.segmented_control(
                "Theme",
                ["Dark", "Light"],
                default=mobile_theme_label,
                key="app_shell_mobile_theme",
                label_visibility="collapsed",
                width="stretch",
            )
        with mobile_cols[2]:
            selected_mobile_language = st.segmented_control(
                "Language",
                ["EN", "中文"],
                default=mobile_language_label,
                key="app_shell_mobile_language",
                label_visibility="collapsed",
                width="stretch",
            )
        resolved_mobile_theme = "dark" if selected_mobile_theme == "Dark" else "light"
        resolved_mobile_language = "en" if selected_mobile_language == "EN" else "zh"
        if resolved_mobile_theme != theme:
            st.session_state["ui_theme"] = resolved_mobile_theme
            settings.setdefault("ui", {})["theme"] = resolved_mobile_theme
        if resolved_mobile_language != language:
            st.session_state["ui_language"] = resolved_mobile_language
            settings.setdefault("ui", {})["language"] = resolved_mobile_language

    with st.container(key="app_shell_burger_row"):
        with st.popover("☰"):
            for index, label in enumerate(page_labels):
                active = st.session_state[nav_state_key] == label
                if st.button(
                    label,
                    key=f"app_shell_burger_{index}",
                    use_container_width=True,
                    type="primary" if active else "secondary",
                ):
                    st.session_state[nav_state_key] = label
                    st.rerun()

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
