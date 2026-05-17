# UI Rebuild Phase 2 Update

Date: 2026-05-18

Worktree baseline:
- Repository: `/Users/leolinum/Documents/LEOLRS0-3-ui-rebuild`
- Branch: `codex/ui-rebuild-baseline`
- Git baseline: `7495af7` (`Release v0.2.5 UI and timeline stability updates`)

## 1. Scope of this update

This note records the audit-driven work completed after the 2026-05-17 Phase 2 review.

This round focused on the items that were still blocking clean acceptance:
- make theme switching reliable in real browser runs
- remove remaining visual ownership conflicts in the Streamlit host shell
- make parameter sweep results reliably visible and verifiable
- preserve Phase 2's state-governance direction while reducing regression risk

## 2. Completed audit items

### 2.1 Parameter sweep results moved out of the expander

`trend_system/gui.py`

`_parameter_debug_section(...)` now uses this structure:
- expander contains only description, controls, and trigger button
- computation runs inside `st.status(...)`
- result sections render after the expander, not inside it

This resolves the main visibility problem from the audit:
- users no longer need to scroll inside the expander to discover whether results appeared
- long-running work now exposes explicit progress stages instead of a generic spinner

Current progress stages:
- `Preparing price data...`
- `Running full-range sweep...`
- `Running target-window sweep...`
- `Building comparison curves...`
- `Parameter sweep complete`

### 2.2 Sidebar background is now theme-owned

Files:
- `trend_system/interfaces/streamlit/styles/tokens.css`
- `trend_system/interfaces/streamlit/styles/base.css`

Added tokens:
- `--leo-page-bg`
- `--leo-sidebar-bg`

Applied host-shell background rules to:
- `body`
- `#root`
- `.stApp`
- `[data-testid="stAppViewContainer"]`
- `[data-testid="stMain"]`
- `[data-testid="stMainBlockContainer"]`
- `[data-testid="stSidebar"] > div:first-child`

This gives the rebuilt shell explicit control over:
- page background
- main canvas background
- sidebar background

It no longer depends on Streamlit's default host colors for theme coherence.

### 2.3 Segmented control radius conflict resolved

File:
- `trend_system/interfaces/streamlit/styles/components.css`

The global square-corner reset block no longer overrides:
- `div[data-testid="stSegmentedControl"] > div`
- `div[data-testid="stSegmentedControl"] button`

Result:
- shell-level segmented controls can preserve the pill styling defined in `shell.css`
- the reset block still keeps the broader square-corner language for cards, inputs, timeline elements, and metrics

### 2.4 Prussian metric and first-row Daily metrics were normalized

Files:
- `trend_system/interfaces/streamlit/pages/daily_page.py`
- `trend_system/interfaces/streamlit/styles/components.css`

Changes:
- `SPY close` and `VIX multiplier` now render through `_render_side_badge_metric(...)`
- `badge=None` is supported for no-badge metric rows
- `.leo-sidebadge-metric` is included in the square-corner reset block
- `.leo-sidebadge-metric__row--solo` was added for no-badge layout
- dark-mode prussian badge colors were added to avoid low contrast if a prussian badge appears in dark mode later

Result:
- Daily page Market State first row no longer mixes native `st.metric` and custom metric cards
- card rhythm and visual language are now consistent across that row

### 2.5 CSS loading now uses mtime-aware cache instead of process-sticky cache

File:
- `trend_system/interfaces/streamlit/shared/theme.py`

`stylesheet_text()` now uses a module cache keyed by file mtime:
- unchanged CSS files do not re-read from disk every rerun
- changed CSS files invalidate automatically without restarting the Streamlit process

This replaces the previous extremes:
- `lru_cache` was too sticky during theme and CSS iteration
- no cache caused repeated disk reads on every rerun

### 2.6 Theme override behavior is documented

File:
- `trend_system/interfaces/streamlit/shared/theme.py`

`theme_override_text(...)` now carries an inline comment documenting its current boundary:
- safe for the current flat CSS rule structure
- not designed for nested blocks or declarations containing braces

This is intentionally sufficient for the current extracted styles and avoids silent ambiguity for future edits.

### 2.7 Parameter sweep ownership moved into the Backtest page module

Files:
- `trend_system/interfaces/streamlit/pages/backtest_page.py`
- `trend_system/gui.py`

The parameter sweep UI and workflow now live in:
- `_render_parameter_debug_section(...)` inside `backtest_page.py`

`gui.py` no longer contains the sweep renderer itself.
It now only wires the required helpers into `BacktestPageDeps`, including:
- default raw settings loader
- cached parameter sweep runner
- parameter-frame localization helpers
- comparison-curve builders
- PDF summary formatter

Result:
- `gui.py` returns to acting as a composition root
- backtest-specific rendering logic now lives with the backtest page
- the next boundary-cleanup step can focus on helper extraction rather than first moving the UI entrypoint

## 3. Real-browser verification completed

Target:
- `http://localhost:8522`

### 3.1 Theme verification

Verified through live DOM inspection in the running Streamlit app.

Light mode computed values:
- `--leo-page-bg = #F5F1EB`
- `--leo-sidebar-bg = rgba(244, 240, 232, 0.55)`
- `.stApp background = rgb(245, 241, 235)`
- sidebar background = `rgba(244, 240, 232, 0.55)`
- `--leo-ink = #0A0C0D`

Dark mode computed values:
- `--leo-page-bg = #1A1D1F`
- `--leo-sidebar-bg = rgba(20, 22, 24, 0.80)`
- `.stApp background = rgb(26, 29, 31)`
- sidebar background = `rgba(20, 22, 24, 0.8)`
- `--leo-ink = rgba(244, 240, 232, 0.92)`

Conclusion:
- theme control is not just changing stored values
- host page, main canvas, and sidebar all follow the active theme in live browser state

### 3.2 Parameter sweep verification

Backtest page verification was run in the browser with the rebuilt flow.

Observed runtime:
- progress moved through all five `st.status(...)` stages
- results became visible after roughly `0.76` minutes in the current environment

Confirmed visible result sections:
- `Full-Range Parameter Recommendations`
- `Target-Date Parameter Recommendations`
- `Preferred Parameter Ranges`
- `Unified Test Results`
- comparison charts for both full-range and target-window sweep runs

Conclusion:
- the earlier "results not appearing" problem is resolved in the current worktree
- the main issue was result placement and observability, not a current Streamlit spinner regression

## 4. Test and compile status

Local verification completed after the latest code changes:
- `python3 -m py_compile ...` passed for the edited core modules
- `pytest tests/test_streamlit_shared_helpers.py tests/test_streamlit_page_registry.py -q` passed

Current test result:
- `11 passed`

The helper tests currently protect:
- `SessionKeys` constant values
- legacy key migration
- theme override extraction for both dark and light token blocks

## 5. Current code ownership state

### 5.1 Stable enough to keep

These pieces are now behaving as intended:
- extracted CSS bundle under `styles/`
- render-only `inject_styles(...)`
- `SessionKeys` ownership and legacy migration
- live light/dark host-shell switching
- Daily first-row metric consistency
- parameter sweep result visibility and progress reporting
- parameter sweep page ownership now living in `backtest_page.py`

### 5.2 Still intentionally transitional

These items remain in transitional form:
- `theme_override_text(...)` still relies on regex extraction
- settings/theme writes still happen in more than one place in the session flow
- full visual QA across every page and both themes is not yet complete
- parameter sweep still depends on helper functions that are injected from `gui.py`

## 6. Remaining work after this update

Priority order for the next conversation:

1. Move parameter sweep logic out of `trend_system/gui.py`
   - completed for the page entrypoint
   - next refinement is extracting sweep-specific helpers into a backtest-local helper module if needed

2. Tighten theme state write ownership
   - keep current behavior stable
   - then reduce duplicate write paths for `UI_THEME` / `SETTINGS_UI_THEME`

3. Run page-by-page visual QA
   - Daily
   - Backtest
   - Market Health
   - Settings
   - each page in both light and dark themes

4. Capture baseline screenshots for visual equivalence review
   - timeline
   - section heads
   - metric cards
   - sidebar clusters
   - shell navigation

## 7. Summary

This round closes the main Phase 2 acceptance blockers from the audit:
- live theme switching now controls the host shell, not just text tokens
- sidebar background is theme-aware
- parameter sweep results are visible and verified in the browser
- long-running sweep work now has usable progress feedback
- Daily page first-row metric rendering is visually consistent
- parameter sweep no longer physically lives in `gui.py`

The next phase should stop focusing on theme repair and start focusing on boundary repair:
- shrinking the remaining sweep-helper surface still injected from `gui.py`
- then finishing visual QA against the rebuild spec
