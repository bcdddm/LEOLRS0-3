from __future__ import annotations

import html
from pathlib import Path
from typing import Callable

import streamlit as st


def render_release_notes(
    language: str,
    *,
    tr: Callable[[str, str, str], str],
    changelog_path: Path,
    changelog_en_path: Path,
) -> None:
    st.markdown(
        f'<div class="leo-section-head leo-section-head--green">'
        f'<span class="leo-section-dot"></span>'
        f'<span class="leo-section-overline">{tr(language, "更新与修复日志", "Update and Fix Log")}</span>'
        f'<span class="leo-section-rule"></span></div>',
        unsafe_allow_html=True,
    )
    changelog = release_notes_text(
        language,
        changelog_path=changelog_path,
        changelog_en_path=changelog_en_path,
    )
    escaped = html.escape(changelog)
    st.markdown(
        f"""
<div style="height: 320px; overflow-y: auto; border: 1px solid rgba(174,143,84,0.22); border-radius: 0; clip-path: polygon(0.45rem 0, calc(100% - 0.45rem) 0, 100% 0.45rem, 100% calc(100% - 0.45rem), calc(100% - 0.45rem) 100%, 0.45rem 100%, 0 calc(100% - 0.45rem), 0 0.45rem); padding: 12px; background: rgba(244,240,232,0.04); white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace; font-size: 13px; line-height: 1.45; color: inherit;">
{escaped}
</div>
""",
        unsafe_allow_html=True,
    )
    st.caption(
        f"{tr(language, '日志文件', 'Log file')}: "
        f"{release_notes_path(language, changelog_path=changelog_path, changelog_en_path=changelog_en_path).resolve()}"
    )


def release_notes_text(
    language: str = "zh",
    *,
    changelog_path: Path,
    changelog_en_path: Path,
) -> str:
    path = release_notes_path(
        language,
        changelog_path=changelog_path,
        changelog_en_path=changelog_en_path,
    )
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "CHANGELOG.md not found."


def release_notes_path(
    language: str = "zh",
    *,
    changelog_path: Path,
    changelog_en_path: Path,
) -> Path:
    return changelog_en_path if language == "en" and changelog_en_path.exists() else changelog_path
