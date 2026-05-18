# UI Rebuild Phase 2 Update

Date: 2026-05-17

Worktree baseline:
- Repository: `/Users/leolinum/Documents/LEOLRS0-3-ui-rebuild`
- Branch: `codex/ui-rebuild-baseline`
- Git baseline: `7495af7` (`Release v0.2.5 UI and timeline stability updates`)

## 1. Goal of this update

This note packages the current rebuild state after the Phase 2 front-half audit so the next conversation can continue without re-discovery.

The current direction remains unchanged:
- keep Streamlit as the formal product UI path
- rebuild from the clean historical baseline instead of the current dirty app state
- continue Phase 1 and early Phase 2 without mixing in unrelated business logic
- make `gui.py` lighter by moving style, component, and state ownership outward

## 2. What has already been completed

### 2.1 Phase 1: style entrypoint and CSS extraction

Global style ownership has been moved out of `trend_system/gui.py` into:
- `trend_system/interfaces/streamlit/shared/theme.py`
- `trend_system/interfaces/streamlit/styles/tokens.css`
- `trend_system/interfaces/streamlit/styles/base.css`
- `trend_system/interfaces/streamlit/styles/shell.css`
- `trend_system/interfaces/streamlit/styles/components.css`
- `trend_system/interfaces/streamlit/styles/preparing.css`

Also completed:
- `app_shell.py` no longer carries inline shell navigation CSS
- `preparing.py` no longer inlines its own style block
- TradingView card CSS now lives in `trend_system/interfaces/streamlit/shared/assets/tradingview_chart.css`
- the iframe chart theme follows `data-theme` from the document instead of Python-side theme branching

### 2.2 Phase 1 to Phase 2 bridge: component extraction

New component modules:
- `trend_system/interfaces/streamlit/components/section_head.py`
- `trend_system/interfaces/streamlit/components/sidebar_panels.py`

The following repeated UI structures are now centralized:
- section heads
- sidebar section plates
- sidebar control clusters
- strategy console intro

These components are already used by:
- `daily_page.py`
- `market_health_page.py`
- `backtest_page.py`
- `settings_page.py`
- `gui.py`

### 2.3 Early Phase 2: session_state key consolidation

Canonical key ownership now lives in:
- `trend_system/interfaces/streamlit/shared/session_state.py`

This introduced `SessionKeys` as the central naming surface for UI and page cache state.

Current canonical key set:
- `UI_LANGUAGE`
- `UI_THEME`
- `HOME_TIMEZONE`
- `BASE_CURRENCY`
- `HEADER_UI_LANGUAGE`
- `HEADER_UI_THEME`
- `SETTINGS_UI_LANGUAGE`
- `SETTINGS_UI_THEME`
- `SETTINGS_HOME_TIMEZONE`
- `SETTINGS_BASE_CURRENCY`
- `SHELL_ACTIVE_PAGE`
- `SETTINGS_PENDING_DELETE`
- `DAILY_TIMELINE_MODE`
- `DAILY_RESULT`
- `DAILY_PRICES`
- `DAILY_FINGERPRINT`
- `MARKET_HEALTH_PRICE`
- `MARKET_HEALTH_SYMBOL`
- `MARKET_HEALTH_DISPLAY_START`
- `BACKTEST_RESULT`
- `BACKTEST_FINGERPRINT`
- `EQUITY_CHART_RESET`
- `EXPOSURE_CHART_RESET`
- `PARAMETER_SWEEP`
- `SWEEP_TARGET_DATE`
- `SWEEP_MONTHS_BEFORE`
- `SWEEP_MONTHS_AFTER`
- `SWEEP_SORT_METRIC`

The following modules already use `SessionKeys` instead of ad hoc strings:
- `trend_system/gui.py`
- `trend_system/interfaces/streamlit/app_shell.py`
- `trend_system/interfaces/streamlit/pages/daily_page.py`
- `trend_system/interfaces/streamlit/pages/market_health_page.py`
- `trend_system/interfaces/streamlit/pages/backtest_page.py`
- `trend_system/interfaces/streamlit/pages/settings_page.py`
- `trend_system/interfaces/streamlit/shared/text.py`
- `trend_system/interfaces/streamlit/shared/theme.py`
- `trend_system/interfaces/streamlit/shared/__init__.py`

## 3. Audit-driven changes added in this iteration

### 3.1 Legacy key compatibility migration

To reduce silent breakage when older Streamlit sessions are still open, `session_state.py` now includes:
- `migrate_legacy_keys()`

It currently migrates:
- `"equity_chart_reset"` -> `SessionKeys.EQUITY_CHART_RESET`
- `"exposure_chart_reset"` -> `SessionKeys.EXPOSURE_CHART_RESET`
- `"parameter_sweep"` -> `SessionKeys.PARAMETER_SWEEP`

This migration is invoked early in `gui.main()` before page rendering begins.

Result:
- we keep the cleaner prefixed names
- old live sessions should not lose state unexpectedly
- chart reset counters and stored parameter sweep payloads survive the naming transition

### 3.2 Static guard tests for SessionKeys

`tests/test_streamlit_shared_helpers.py` now includes a static assertion block that verifies every canonical `SessionKeys` constant still maps to the intended historical string.

This is intentionally simple, but high leverage:
- misspelling a session key in Streamlit usually fails silently
- these assertions give us a cheap regression tripwire in CI and local runs

### 3.3 Theme and widget-key cleanup

This update also closes three audit findings:
- removed the duplicate `@media (prefers-color-scheme: dark)` paths from the Streamlit style bundle so `data-theme` is the only theme switch source
- made `inject_styles()` a render-only function by moving `UI_THEME` state writes back to `gui.py`
- added the parameter sweep widget keys to `SessionKeys` so implicit Streamlit widget state is also tracked and tested

## 4. Clarified module roles

### 4.1 `theme.py`

`trend_system/interfaces/streamlit/shared/theme.py` is real and intentional.

Its role is:
- resolve the effective UI theme from settings and session state
- provide the single style injection entrypoint for the rebuilt shell
- load the CSS bundle from the `styles/` directory on each rerun so theme fixes are not blocked by process-level cache state
- emit theme-specific CSS overrides directly from the server so runtime theme changes do not depend on browser-side script execution

It is not a token-definition file by itself.
It is the runtime bridge between:
- persisted UI theme state
- DOM theme attributes
- the extracted CSS files

`inject_styles()` is now intentionally render-only.
Theme persistence stays with the caller so state ownership remains visible in `gui.py`.

### 4.2 `session_state.py`

`trend_system/interfaces/streamlit/shared/session_state.py` is the ownership layer for:
- canonical UI/session key names
- minimal session state helpers
- legacy key migration during the Phase 2 transition

It is not yet a full state manager.
That is deliberate: Phase 2 is currently focused on key consolidation first, then ownership cleanup second.

## 5. Important decisions currently in effect

### 5.1 Chart reset keys

The canonical names are now:
- `backtest_equity_chart_reset`
- `backtest_exposure_chart_reset`

Decision:
- keep the prefixed names for long-term consistency
- preserve old runtime sessions through one-time migration

### 5.2 `parameter_sweep`

Canonical session key name is now:
- `backtest_parameter_sweep`

Decision:
- keep the semantic ownership with backtest
- accept that the logic still lives in `gui.py` for now
- defer actual relocation of the parameter sweep logic to a later Phase 2 extraction step

This means the naming surface is now corrected before the module boundary is corrected.

### 5.3 `pending_delete`

Canonical name is currently:
- `settings_pending_delete`

Decision:
- keep the broad name for now to avoid behavior changes
- revisit when settings delete flows are componentized and object scope becomes easier to narrow

## 6. Remaining gaps after this update

The following work is still open:

1. `parameter_sweep` logic still physically lives inside `gui.py`
2. `settings_pending_delete` is still semantically broad
3. `gui.py` still owns too much sidebar orchestration even though the repeated view fragments are now thinner
4. real browser validation has not yet been completed page by page after the state-key transition
5. parameter sweep widget state still lives physically in `gui.py` even though its keys are now tracked centrally

## 7. Recommended next steps for the next conversation

Priority order:

1. Run real UI verification in Streamlit
   - Daily page
   - Backtest page
   - Market Health page
   - Settings page

2. Confirm these behaviors manually
   - language switching
   - theme switching
   - settings persistence into session state
   - backtest chart reset buttons
   - parameter sweep persistence and restore behavior
   - settings delete confirmation flow

3. Continue Phase 2 extraction
   - move parameter sweep state handling out of `gui.py`
   - tighten sidebar state ownership
   - continue reducing `gui.py` to orchestration-only responsibilities

## 8. Files touched in this iteration

- `trend_system/interfaces/streamlit/shared/session_state.py`
- `trend_system/interfaces/streamlit/shared/__init__.py`
- `trend_system/gui.py`
- `tests/test_streamlit_shared_helpers.py`
- `docs/audit/02-phase2-rebuild-log-2026-05-17.md`

## 9. Verification status

Expected verification commands after this update:

```bash
python3 -m py_compile trend_system/gui.py \
  trend_system/interfaces/streamlit/shared/session_state.py \
  trend_system/interfaces/streamlit/shared/theme.py \
  trend_system/interfaces/streamlit/pages/daily_page.py \
  trend_system/interfaces/streamlit/pages/market_health_page.py \
  trend_system/interfaces/streamlit/pages/backtest_page.py \
  trend_system/interfaces/streamlit/pages/settings_page.py

pytest tests/test_streamlit_shared_helpers.py tests/test_streamlit_page_registry.py -q
```

If these pass, the branch is ready for the next round of UI validation and Phase 2 ownership cleanup.

## 10. Real UI validation completed on 2026-05-17

Local verification target:
- `http://localhost:8522`

Observed results:

1. App boot
   - Streamlit baseline launched successfully from the rebuild worktree
   - no startup exception was observed

2. Language rerender path
   - header segmented control still triggers a rerun and the shell language changes
   - `SessionKeys.UI_LANGUAGE` consolidation did not break the top-level language path

3. Backtest page
   - backtest page rendered successfully
   - clicking the equity reset and exposure reset controls did not produce a Streamlit exception
   - chart reset key migration did not surface an immediate runtime problem

4. Settings delete flow
   - clicking the delete action for a saved profile opened the confirmation state correctly
   - clicking cancel removed the confirmation state correctly
   - `settings_pending_delete` handling did not raise a runtime exception

5. Known limitation from this validation pass
   - this was a fast runtime pass, not a full visual QA sweep
   - theme switching was not fully exercised in-browser during this round; a dedicated settings-page theme control is now available for the next pass
   - parameter sweep state migration was validated structurally and by helper test, but not yet through a full manual sweep workflow

## 11. Audit follow-up completed on 2026-05-17

Completed from the next audit round:

1. Theme source of truth
   - removed `@media (prefers-color-scheme: dark)` from the rebuilt Streamlit style files
   - explicit `data-theme` selection is now the only dark/light switch path

2. Theme state ownership
   - `inject_styles()` no longer writes to `session_state`
   - `gui.py` now sets `SessionKeys.UI_THEME` before calling the style injector

3. Parameter sweep widget keys
   - `parameter_sweep_target_date`
   - `parameter_sweep_months_before`
   - `parameter_sweep_months_after`
   - `parameter_sweep_sort_metric`
   are now registered in `SessionKeys` and covered by static assertions

4. Theme validation control
   - settings page now exposes an `Interface theme` preference bound to `SessionKeys.SETTINGS_UI_THEME`
   - theme changes trigger an explicit rerun so the next app pass can re-inject the correct stylesheet bundle

5. Market-state component consistency
   - the first `Market State` row on the daily page now uses the same side-badge metric component for SPY close, trend, VIX, and VIX multiplier
   - this removes the earlier mixed rendering path where some cells used `st.metric` and others used custom HTML cards

## 12. Suggested first action in the next conversation

Resume from:
- fix the remaining light-theme visual gap in the Streamlit host layer
- re-run browser verification of the parameter sweep workflow and capture the first successful result tables
- then continue extraction of parameter sweep ownership out of `gui.py`

## 13. Additional runtime findings on 2026-05-17

1. Theme toggle state path
   - the settings-page theme control now updates its selected value correctly
   - a follow-up fix expanded the light token override set so reruns now overwrite the full surface/page palette, not only text colors
   - host-layer background is now explicitly tied to `--leo-page-bg`
   - removing the CSS process cache was required before the browser could actually pick up the new light-token set during reruns

2. Parameter sweep workflow
   - the debug expander opens correctly and the sweep controls render
   - browser automation did not yet observe the expected result sections:
     - `Full-Range Parameter Recommendations`
     - `Target-Date Parameter Recommendations`
   - no Streamlit exception was raised during the attempt
   - next pass should verify whether the trigger is not firing, is slow, or is rendering results outside the currently inspected viewport/state

## 14. Design decision: Metallic racing green input border system

### 14.1 Design intent

All user-editable controls (text inputs, number inputs, selectboxes, date pickers, text areas) now carry a two-tone **metallic racing green** border — a linear gradient blending the existing gold rim token `rgba(174, 143, 84)` with the racing green token `rgba(31, 106, 83)` at a 135° angle.

The visual language reads as: gold at the top-left highlight edge → racing green at the mid-body → gold at the bottom-right shadow edge. This creates the "metallic sheen" quality (金属感) the design calls for, where the green reads as a premium material rather than a flat UI tint.

On focus, both colours intensify and a soft green outer glow appears (`box-shadow: 0 0 14px rgba(31,106,83,0.14)`).

### 14.2 Feasibility assessment: HIGH (9/10)

**Why this is straightforward:**

- The design token system already owns both colour values (`--leo-racing-green`, `--leo-surface-rim`) — this adds two derived tokens, not new palette entries.
- The global reset block in `components.css` already enforces `border-radius: 0 !important` on all input controls. This removes the only real blocker for `border-image` gradient borders (spec incompatibility between `border-image` and `border-radius` does not apply here).
- `border-image: linear-gradient() 1` has **96.09% global browser support** (Chrome 7+, Firefox 29+, Safari 4+, Edge 12+, iOS Safari 3.2+). No polyfill needed.
- The change is purely additive CSS — no Python logic changes, no new Streamlit widgets, no session_state interaction.

**One genuine technical caveat:**

The `border` CSS shorthand implicitly resets `border-image` to `none`. Any rule block that uses the `border` shorthand and also wants `border-image` must declare `border-image` **after** `border` in the same declaration block. This ordering is already correct in the implementation (see `base.css` sidebar input rule with inline comment).

**What is explicitly NOT affected:**

- Rounded controls (`[role="switch"]`, `[data-baseweb="radio"] label`, `div[data-testid="stSegmentedControl"]`) keep `border-radius: 999px` and are excluded from the gradient border system. They continue to use `border-color` with green tints. Applying `border-image` to these would silently drop `border-radius`.
- The slider track and thumb (already styled with racing green fills in `components.css`) are also excluded — sliders are not border-framed controls.

### 14.3 CSS technique chosen: `border-image: linear-gradient() 1`

References:
- [Gradient Borders in CSS — CSS-Tricks](https://css-tricks.com/gradient-borders-in-css/) — primary technique reference; confirms `border-image` is the cleanest syntax for flat-cornered targets
- [border-image: `<gradient>` — Can I Use](https://caniuse.com/mdn-css_properties_border-image_gradient) — 96.09% global support confirmed
- [Border with gradient and radius — DEV Community](https://dev.to/afif/border-with-gradient-and-radius-387f) — pseudo-element fallback technique documented; not needed here given border-radius: 0

Three alternative techniques were considered and rejected:

| Technique | Why rejected |
|-----------|--------------|
| Pseudo-element (`::before` with z-index −1) | Adds layout complexity; Streamlit's Base Web input elements use Shadow DOM / stacking contexts that make z-index −1 unreliable |
| CSS mask approach (`background-clip + mask-composite`) | Modern but less readable; mask side effects can clip box-shadow and backdrop-filter already applied to the same elements |
| `outline` with green tint | Cannot produce a gradient; only solid colour; not metallic |

### 14.4 Token changes

Two new semantic tokens added to `tokens.css`:

| Token | Light value | Dark value |
|-------|-------------|------------|
| `--leo-metallic-gold` | `rgba(174, 143, 84, 0.68)` | `rgba(174, 143, 84, 0.78)` |
| `--leo-metallic-green` | `rgba(31, 106, 83, 0.82)` | `rgba(46, 128, 101, 0.92)` |

Dark-mode values are slightly more opaque and the green is shifted one stop brighter (`46, 128, 101`) to maintain visibility against the `#1A1D1F` page background. The gold remains at the same hue, only opacity increase.

The focused state uses hardcoded high-opacity values (`rgba(174,143,84,0.90)` gold, `rgba(31,106,83,0.96)` green) rather than additional tokens — focus intensity is a one-off state that does not need to propagate across the system.

### 14.5 CSS surface changes

**`base.css` — new global section (inserted before sidebar rules):**

```css
[data-baseweb="input"],
[data-baseweb="base-input"],
[data-baseweb="select"] > div[data-baseweb="control"],
[data-testid="stTextArea"] textarea {
  border: 1px solid transparent !important;
  border-image: linear-gradient(
    135deg,
    var(--leo-metallic-gold) 0%,
    var(--leo-metallic-green) 50%,
    var(--leo-metallic-gold) 100%
  ) 1 !important;
}
```

**`base.css` — sidebar input rule updated:** `border: 1px solid var(--leo-surface-rim)` replaced with `border: 1px solid transparent` + explicit `border-image` declaration.

**`base.css` — sidebar focus state updated:** `border-color` override replaced with `border-image` intensification + green glow `box-shadow`.

### 14.6 Impact and watch items

| Area | Impact | Note |
|------|--------|------|
| Light theme readability | Positive — gradient reads clearly on `#F5F1EB` cream background | Gold highlight at top-left is the most visible edge |
| Dark theme readability | Positive — dark token set bumps opacity; green is more saturated | Test in browser before sign-off |
| `border-image` + `box-shadow` coexistence | Compatible — they apply to different visual layers | Shadow still renders outside the border box |
| `border-image` + `backdrop-filter` | Compatible | backdrop-filter applies to the element's background area, not its border |
| Safari < 4 / IE < 11 | Not supported — these browsers are not in scope for this product | |
| Streamlit-injected Baseweb styles | Baseweb resets borders on inputs via its own CSS; `!important` overrides these | Monitor across Streamlit upgrades |
