from __future__ import annotations

from html import escape

import streamlit as st


def preparing_markup(language: str, title: str | None = None, detail: str | None = None) -> str:
    theme = st.session_state.get("ui_theme", "dark")
    resolved_title = title or ("Preparing" if language == "en" else "准备中")
    resolved_detail = detail or (
        "Collecting the next view of the system."
        if language == "en"
        else "正在为你整理下一层系统视图。"
    )
    is_dark = theme == "dark"
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
<style>
  .leolrs-preparing-card {{
    --leo-prep-surface-a: {"rgba(26, 29, 31, 0.25)" if is_dark else "rgba(244, 240, 232, 0.25)"};
    --leo-prep-surface-b: {"rgba(244, 240, 232, 0.06)" if is_dark else "rgba(255, 255, 255, 0.10)"};
    --leo-prep-rim: {"rgba(174, 143, 84, 0.18)" if is_dark else "rgba(174, 143, 84, 0.20)"};
    --leo-prep-inner: {"rgba(255, 255, 255, 0.05)" if is_dark else "rgba(255, 255, 255, 0.14)"};
    --leo-prep-text: {"rgba(244, 240, 232, 0.92)" if is_dark else "#1a1d1f"};
    --leo-prep-subtext: {"rgba(244, 240, 232, 0.64)" if is_dark else "rgba(26, 29, 31, 0.72)"};
  }}
  .leolrs-preparing-card {{
    display: flex;
    align-items: center;
    gap: 0.9rem;
    margin: 0.5rem 0 1rem;
    padding: 0.9rem 1rem;
    background: linear-gradient(145deg, var(--leo-prep-surface-a), var(--leo-prep-surface-b));
    border: 1px solid var(--leo-prep-rim);
    clip-path: polygon(0.85rem 0, calc(100% - 0.85rem) 0, 100% 0.85rem, 100% calc(100% - 0.85rem), calc(100% - 0.85rem) 100%, 0.85rem 100%, 0 calc(100% - 0.85rem), 0 0.85rem);
    box-shadow:
      0 1px 0 var(--leo-prep-inner) inset,
      0 0 0 1px rgba(255, 250, 242, 0.11) inset,
      0 10px 24px rgba(30, 29, 27, 0.08);
    backdrop-filter: blur(8px);
  }}
  .leolrs-preparing-dots {{
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    min-width: 4rem;
  }}
  .leolrs-dot {{
    width: 0.72rem;
    height: 0.72rem;
    border-radius: 999px;
    position: relative;
    animation: leolrs-dot-drift 1.35s ease-in-out infinite;
    box-shadow:
      0 0 0 1px rgba(255,255,255,0.28) inset,
      0 0 10px rgba(255,255,255,0.08);
  }}
  .leolrs-dot::after {{
    content: "";
    position: absolute;
    inset: -22%;
    border-radius: 999px;
    background: radial-gradient(circle, rgba(255,255,255,0.09) 0%, rgba(255,255,255,0.01) 70%, transparent 100%);
    opacity: 0.42;
  }}
  .leolrs-dot-blue {{
    background: radial-gradient(circle at 30% 28%, rgba(201, 226, 247, 0.95) 0%, rgba(44, 93, 134, 0.85) 24%, rgba(18, 57, 91, 0.96) 58%, rgba(11, 34, 54, 1) 100%);
    animation-delay: 0s;
  }}
  .leolrs-dot-green {{
    background: linear-gradient(140deg, rgba(125, 181, 161, 0.95) 0%, rgba(58, 122, 102, 0.92) 28%, rgba(36, 88, 71, 1) 58%, rgba(16, 47, 38, 1) 100%);
    animation-delay: 0.12s;
  }}
  .leolrs-dot-red {{
    background: radial-gradient(circle at 38% 32%, rgba(213, 148, 148, 0.74) 0%, rgba(181, 72, 72, 0.94) 22%, rgba(158, 47, 47, 0.98) 56%, rgba(111, 32, 32, 1) 100%);
    filter: saturate(0.92) contrast(0.98);
    animation-delay: 0.24s;
  }}
  .leolrs-preparing-copy {{
    display: flex;
    flex-direction: column;
    gap: 0.12rem;
  }}
  .leolrs-preparing-title {{
    font-size: 0.95rem;
    font-weight: 650;
    color: var(--leo-prep-text);
    letter-spacing: 0.01em;
  }}
  .leolrs-preparing-detail {{
    font-size: 0.82rem;
    color: var(--leo-prep-subtext);
  }}
  @keyframes leolrs-dot-drift {{
    0%, 100% {{ transform: translateY(0) scale(0.96); opacity: 0.8; }}
    45% {{ transform: translateY(-3px) scale(1.04); opacity: 1; }}
    70% {{ transform: translateY(1px) scale(0.98); opacity: 0.9; }}
  }}
</style>
"""


def render_preparing(container: st.delta_generator.DeltaGenerator, language: str, *, title: str | None = None, detail: str | None = None) -> None:
    container.markdown(preparing_markup(language, title=title, detail=detail), unsafe_allow_html=True)
