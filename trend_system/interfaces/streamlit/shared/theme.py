from __future__ import annotations

import html
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

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
SUPPORTED_THEME_MODES = {"light", "dark", "system"}
SYSTEM_THEME_QUERY_PARAM = "system_theme"
_css_cache: dict[str, tuple[float, str]] = {}


def resolve_theme_mode(settings: dict) -> str:
    selected = _normalize_theme_mode(st.session_state.get(SessionKeys.UI_THEME_MODE))
    if selected is None:
        # Backward compatibility: older sessions only stored the effective theme.
        selected = _normalize_theme(st.session_state.get(SessionKeys.UI_THEME))
    if selected is None:
        selected = _normalize_theme_mode(settings.get("ui", {}).get("theme", "dark"))
    return selected or "dark"


def resolve_theme(settings: dict) -> str:
    mode = resolve_theme_mode(settings)
    if mode == "system":
        # Primary: read Streamlit's own theme (handles light/dark/OS-follow natively).
        # st.context.theme.type is populated from the frontend ClientState proto and
        # is updated on every rerun triggered by a Streamlit theme change.
        try:
            streamlit_type = _normalize_theme(st.context.theme.type)
            if streamlit_type is not None:
                st.session_state[SessionKeys.BROWSER_THEME] = streamlit_type
                return streamlit_type
        except Exception:
            pass
        # Fallback: URL query param written by render_theme_bridge() JS (first load,
        # or Streamlit version without st.context.theme support).
        browser_theme = resolve_browser_theme()
        if browser_theme is not None:
            st.session_state[SessionKeys.BROWSER_THEME] = browser_theme
            return browser_theme
        cached_theme = _normalize_theme(st.session_state.get(SessionKeys.BROWSER_THEME))
        if cached_theme is not None:
            return cached_theme
        return "dark"
    return mode


def _normalize_theme(value: object) -> str | None:
    text = str(value).strip().lower() if value is not None else ""
    return text if text in SUPPORTED_THEMES else None


def _normalize_theme_mode(value: object) -> str | None:
    text = str(value).strip().lower() if value is not None else ""
    return text if text in SUPPORTED_THEME_MODES else None


def resolve_browser_theme() -> str | None:
    query_value = st.query_params.get(SYSTEM_THEME_QUERY_PARAM)
    if isinstance(query_value, list):
        query_value = query_value[-1] if query_value else None
    return _normalize_theme(query_value)


def render_theme_bridge(theme_mode: str) -> None:
    if theme_mode != "system":
        return

    current_theme = resolve_browser_theme() or _normalize_theme(st.session_state.get(SessionKeys.BROWSER_THEME)) or "dark"
    escaped_theme = html.escape(current_theme, quote=True)
    escaped_param = html.escape(SYSTEM_THEME_QUERY_PARAM, quote=True)
    components.html(
        f"""
<script>
(() => {{
  const current = "{escaped_theme}";
  const param = "{escaped_param}";
  const parentWindow = window.parent ?? window;
  const media = parentWindow.matchMedia?.("(prefers-color-scheme: dark)");
  if (!media) return;

  const applyTheme = () => {{
    const nextTheme = media.matches ? "dark" : "light";
    if (nextTheme === current) return;
    const url = new URL(parentWindow.location.href);
    if (url.searchParams.get(param) === nextTheme) return;
    url.searchParams.set(param, nextTheme);
    parentWindow.location.replace(url.toString());
  }};

  applyTheme();

  if (typeof media.addEventListener === "function") {{
    media.addEventListener("change", applyTheme);
  }} else if (typeof media.addListener === "function") {{
    media.addListener(applyTheme);
  }}
}})();
</script>
""",
        height=0,
    )


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


def _selector_blocks(css_text: str, selector: str) -> list[str]:
    """Return all CSS rule blocks that start with ``selector``.

    This scanner is resilient to nested braces inside the matched block, which
    allows theme token blocks to grow more safely than the previous flat-regex
    approach. It is still intentionally lightweight and only targets standard
    rule-block syntax.
    """

    blocks: list[str] = []
    cursor = 0
    text_len = len(css_text)
    while cursor < text_len:
        start = _next_selector_start(css_text, selector, cursor)
        if start == -1:
            break
        brace_open = _find_rule_brace(css_text, start + len(selector))
        if brace_open == -1:
            cursor = start + len(selector)
            continue
        depth = 0
        index = brace_open
        in_comment = False
        while index < text_len:
            if in_comment:
                if css_text.startswith("*/", index):
                    in_comment = False
                    index += 2
                    continue
                index += 1
                continue
            if css_text.startswith("/*", index):
                in_comment = True
                index += 2
                continue
            char = css_text[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    blocks.append(css_text[start:index + 1])
                    cursor = index + 1
                    break
            index += 1
        else:
            # Unbalanced braces: stop rather than returning a truncated block.
            break
    return blocks


def _next_selector_start(css_text: str, selector: str, cursor: int) -> int:
    text_len = len(css_text)
    index = cursor
    in_comment = False
    while index < text_len:
        if in_comment:
            if css_text.startswith("*/", index):
                in_comment = False
                index += 2
                continue
            index += 1
            continue
        if css_text.startswith("/*", index):
            in_comment = True
            index += 2
            continue
        if css_text.startswith(selector, index):
            prefix = css_text[index - 1] if index > 0 else ""
            if not prefix or prefix.isspace() or prefix in {"}", ";"}:
                return index
        index += 1
    return -1


def _find_rule_brace(css_text: str, cursor: int) -> int:
    text_len = len(css_text)
    index = cursor
    in_comment = False
    while index < text_len:
        if in_comment:
            if css_text.startswith("*/", index):
                in_comment = False
                index += 2
                continue
            index += 1
            continue
        if css_text.startswith("/*", index):
            in_comment = True
            index += 2
            continue
        char = css_text[index]
        if char == "{":
            return index
        if not char.isspace():
            return -1
        index += 1
    return -1


def theme_override_text(theme: str) -> str:
    selector = f'[data-theme="{theme}"]'
    normalized_root = ":root"
    blocks = _selector_blocks(stylesheet_text(), selector)
    normalized: list[str] = []
    for block in blocks:
        normalized.append(normalized_root + block[len(selector):])
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
