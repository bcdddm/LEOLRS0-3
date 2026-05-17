from __future__ import annotations

from html import escape

import streamlit as st


def preparing_markup(language: str, title: str | None = None, detail: str | None = None) -> str:
    resolved_title = title or ("Preparing" if language == "en" else "准备中")
    resolved_detail = detail or (
        "Collecting the next view of the system."
        if language == "en"
        else "正在为你整理下一层系统视图。"
    )
    return f"""
<div class="leolrs-preparing-card" aria-live="polite">
  <div class="leolrs-preparing-dots" aria-hidden="true">
    <span class="leolrs-dot leolrs-dot-blue"></span>
    <span class="leolrs-dot leolrs-dot-green"></span>
    <span class="leolrs-dot leolrs-dot-red"></span>
  </div>
  <div class="leolrs-preparing-copy">
    <div class="leolrs-preparing-title">{escape(resolved_title)}</div>
    <div class="leolrs-preparing-detail">{escape(resolved_detail)}</div>
  </div>
</div>
"""


def render_preparing(container: st.delta_generator.DeltaGenerator, language: str, *, title: str | None = None, detail: str | None = None) -> None:
    container.markdown(preparing_markup(language, title=title, detail=detail), unsafe_allow_html=True)
