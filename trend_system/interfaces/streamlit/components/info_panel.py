from __future__ import annotations

from html import escape
from typing import Any


def render_info_panel(
    container: Any,
    body: str | list[str],
    *,
    title: str | None = None,
    compact: bool = False,
) -> None:
    """Render explanatory copy in the Prussian-blue information surface."""
    lines = body if isinstance(body, list) else [body]
    title_markup = f'<div class="leo-info-panel__title">{escape(title)}</div>' if title else ""
    body_markup = "".join(f'<div class="leo-info-panel__line">{escape(line)}</div>' for line in lines)
    compact_class = " leo-info-panel--compact" if compact else ""
    container.markdown(
        f"""
<div class="leo-info-panel{compact_class}">
  {title_markup}
  <div class="leo-info-panel__body">{body_markup}</div>
</div>
""",
        unsafe_allow_html=True,
    )
