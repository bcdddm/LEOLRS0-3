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
        # Primary: URL query param written by render_theme_bridge() JS.
        # The JS bridge reads window.matchMedia("prefers-color-scheme: dark")
        # on the parent frame and writes ?system_theme=dark|light, then
        # reloads.  This is the only reliable signal for the actual OS
        # preference — st.context.theme.type reflects Streamlit's hamburger
        # setting, which the user may have pinned independently of the OS, so
        # it is intentionally excluded from this chain.
        browser_theme = resolve_browser_theme()
        if browser_theme is not None:
            st.session_state[SessionKeys.BROWSER_THEME] = browser_theme
            return browser_theme

        # Secondary: last OS theme confirmed by the JS bridge in a prior rerun.
        cached_theme = _normalize_theme(st.session_state.get(SessionKeys.BROWSER_THEME))
        if cached_theme is not None:
            return cached_theme

        # First-load: URL param not yet written.  Trigger one extra rerun so
        # render_theme_bridge() has a chance to inject the JS that sets it.
        # _theme_probe_done is cleared by gui.py whenever the user enters
        # system mode from another mode, so the probe fires fresh each time.
        if not st.session_state.get("_theme_probe_done"):
            st.session_state["_theme_probe_done"] = True
            st.rerun()
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


def render_native_theme_sync(theme: str) -> None:
    """Inject JS to keep Streamlit's built-in localStorage theme in sync.

    Tries the known candidate keys in priority order.  If a key exists and
    already holds the right name, it is skipped.  If it holds the wrong name
    it is updated and a StorageEvent is dispatched so Streamlit's frontend
    React store picks up the change without a full reload.
    """
    st_name = "Light theme" if theme == "light" else "Dark theme"
    escaped = html.escape(st_name, quote=True)
    components.html(
        f"""
<script>
(() => {{
  const target = "{escaped}";
  const w = window.parent ?? window;
  // Keys tried in order: Streamlit stores the active built-in theme under
  // stActiveTheme (v1.28+).  Older builds used stTheme.
  const candidates = ["stActiveTheme", "stTheme", "streamlit:theme"];
  let updated = false;
  for (const key of candidates) {{
    try {{
      const raw = w.localStorage.getItem(key);
      if (raw === null) continue;           // key absent — skip
      const parsed = JSON.parse(raw);
      if (parsed.name === target) continue; // already correct — skip
      const next = JSON.stringify({{...parsed, name: target}});
      w.localStorage.setItem(key, next);
      w.dispatchEvent(new StorageEvent("storage", {{
        key: key,
        newValue: next,
        storageArea: w.localStorage
      }}));
      updated = true;
    }} catch (_) {{}}
  }}
  // If none of the known keys existed yet, prime stActiveTheme so Streamlit
  // picks it up on the next internal theme check.
  if (!updated) {{
    try {{
      const payload = JSON.stringify({{name: target}});
      w.localStorage.setItem("stActiveTheme", payload);
      w.dispatchEvent(new StorageEvent("storage", {{
        key: "stActiveTheme",
        newValue: payload,
        storageArea: w.localStorage
      }}));
    }} catch (_) {{}}
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
