from __future__ import annotations

from html import escape
from typing import Any


def render_sidebar_section_plate(
    container: Any,
    *,
    overline: str,
    title: str,
    summary: str,
) -> None:
    container.markdown(
        f"""
<div class="sidebar-section-plate">
  <div class="sidebar-section-overline">{escape(overline)}</div>
  <div class="sidebar-section-title">{escape(title)}</div>
  <div class="sidebar-section-summary">{escape(summary)}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_strategy_console_intro(
    container: Any,
    *,
    title: str,
    note: str,
    chips: list[str],
) -> None:
    chip_markup = "".join(f'<span class="strategy-console-chip">{escape(chip)}</span>' for chip in chips)
    container.markdown(
        f"""
<div class="strategy-console-intro">
  <div class="strategy-console-title">{escape(title)}</div>
  <div class="strategy-console-note">{escape(note)}</div>
  <div class="strategy-console-grid">{chip_markup}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_sidebar_control_cluster(
    container: Any,
    *,
    overline: str,
    title: str,
    summary: str,
    chips: list[str] | None = None,
    tone: str = "prussian",
) -> None:
    tone_class = {
        "prussian": "",
        "green": " cluster-green",
        "red": " cluster-red",
    }.get(tone, "")
    chip_markup = ""
    if chips:
        chip_markup = '<div class="cluster-chip-row">' + "".join(
            f'<span class="cluster-chip">{escape(chip)}</span>' for chip in chips
        ) + "</div>"
    container.markdown(
        f"""
<div class="sidebar-control-cluster{tone_class}">
  <div class="cluster-overline">{escape(overline)}</div>
  <div class="cluster-title">{escape(title)}</div>
  <div class="cluster-summary">{escape(summary)}</div>
  {chip_markup}
</div>
""",
        unsafe_allow_html=True,
    )
