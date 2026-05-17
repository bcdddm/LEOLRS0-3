from __future__ import annotations

from pathlib import Path
import re

import streamlit as st

from trend_system.interfaces.streamlit.shared.session_state import SessionKeys


STYLES_DIR = Path(__file__).resolve().parents[1] / "styles"
STYLE_FILES = (
    "tokens.css",
    "base.css",
    "shell.css",
    "components.css",
    "preparing.css",
)
SUPPORTED_THEMES = {"light", "dark"}
_css_cache: dict[str, tuple[float, str]] = {}


def resolve_theme(settings: dict) -> str:
    selected = st.session_state.get(SessionKeys.UI_THEME) or settings.get("ui", {}).get("theme", "dark")
    return selected if selected in SUPPORTED_THEMES else "dark"


def stylesheet_text() -> str:
    parts: list[str] = []
    for name in STYLE_FILES:
        path = STYLES_DIR / name
        mtime = path.stat().st_mtime
        cached = _css_cache.get(name)
        if cached is None or cached[0] != mtime:
            _css_cache[name] = (mtime, path.read_text(encoding="utf-8"))
        parts.append(_css_cache[name][1])
    return "\n\n".join(parts)


def theme_override_text(theme: str) -> str:
    # This regex-based extraction works for the current flat CSS structure.
    # It does not support nested rule blocks or declarations containing braces.
    selector = f'[data-theme="{theme}"]'
    normalized_root = ":root"
    blocks = re.findall(rf"{re.escape(selector)}[^\{{]*\{{[^{{}}]*\}}", stylesheet_text(), flags=re.S)
    normalized: list[str] = []
    for block in blocks:
        normalized.append(block.replace(selector, normalized_root))
    return "\n\n".join(normalized)


def inject_styles(theme: str) -> None:
    st.markdown(
        f"""
<style>
{stylesheet_text()}
{theme_override_text(theme)}
</style>
""",
        unsafe_allow_html=True,
    )
