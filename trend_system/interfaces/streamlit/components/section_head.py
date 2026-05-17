from __future__ import annotations

from html import escape
from typing import Any


def render_section_head(container: Any, title: str, *, tone: str = "prussian") -> None:
    container.markdown(
        (
            f'<div class="leo-section-head leo-section-head--{escape(tone, quote=True)}">'
            f'<span class="leo-section-dot"></span>'
            f'<span class="leo-section-overline">{escape(title)}</span>'
            f'<span class="leo-section-rule"></span>'
            f"</div>"
        ),
        unsafe_allow_html=True,
    )
