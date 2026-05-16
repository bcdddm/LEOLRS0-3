# Sidebar Loading And Reference Plan

## Purpose

This note plans four connected problems:

- how the strategy sidebar should be structured
- whether the sidebar should use a full flip-panel presentation
- how empty pages should behave when data is not ready
- how loading and “preparing” states should look and feel

It also expands the design reference set so the UI direction is organized before implementation.

## Current System Findings

### Sidebar ownership today

The strategy configurator currently lives in the sidebar form in [trend_system/gui.py](/Users/leolinum/Documents/LEOLRS0-3/trend_system/gui.py:185).

This is good for persistence and fast access, but the current form has three issues:

- too many controls exist in one long uninterrupted column
- the hierarchy is parameter-first rather than decision-first
- the controls visually feel detached from the page results they influence

### Current empty-page behavior

Several pages currently stop and display “not loaded yet” states instead of guiding the user straight into usable data.

Current examples:

- Daily page: [trend_system/interfaces/streamlit/pages/daily_page.py](/Users/leolinum/Documents/LEOLRS0-3/trend_system/interfaces/streamlit/pages/daily_page.py:57)
- Market Health page: [trend_system/interfaces/streamlit/pages/market_health_page.py](/Users/leolinum/Documents/LEOLRS0-3/trend_system/interfaces/streamlit/pages/market_health_page.py:56)
- Backtest page: [trend_system/interfaces/streamlit/pages/backtest_page.py](/Users/leolinum/Documents/LEOLRS0-3/trend_system/interfaces/streamlit/pages/backtest_page.py:106)
- Chart empty state: [trend_system/interfaces/streamlit/shared/tradingview_chart.py](/Users/leolinum/Documents/LEOLRS0-3/trend_system/interfaces/streamlit/shared/tradingview_chart.py:40)

This does not match the intended premium experience. The user should arrive at a prepared view, not a blank operational prompt.

## Design Reference Set

### Primary dashboard direction

- [Jack R. Dribbble profile](https://dribbble.com/jack-ux-ui-design)
- [XLR Dashboard - Robot Control Interface](https://dribbble.com/shots/27106044-XLR-Dashboard-Robot-Control-Interface)
- [AI Car Inspection SaaS Dashboard](https://dribbble.com/shots/25251171-AI-Car-Inspection-SaaS-Dashboard)
- [PicGen SaaS Image Generator Dashboard](https://dribbble.com/shots/26824576-PicGen-SaaS-Image-Generator-Dashboard)

### Control panel and precision-surface references

- [Control Panel UI tag](https://dribbble.com/tags/control-panel-ui)
- [Control Panel tag](https://dribbble.com/tags/control-panel)
- [Car Control Panel Dashboard](https://dribbble.com/search/control-panel-dashboard)
- [Sidebar Navigation by Widelab](https://widelab.dribbble.com/)

### Jewelry / premium material references

- [Jewellery UI tag](https://dribbble.com/search/jewellery-ui)
- [Jewelry Ecommerce UI](https://dribbble.com/shots/20517105-Jewelry-Ecommerce-UI)
- [Jewelry Shop Website UI](https://dribbble.com/shots/20765809-Jewelry-Shop-Website-UI)

### Microinteraction and loading references

- [Notification Slider - Microinteraction](https://dribbble.com/shots/12215679-Notification-Slider-Microinteraction)
- [On/Off Toggle Switch Animation](https://dribbble.com/shots/26387857-On-Off-Toggle-Switch-Animation)
- [UI - Language Switch](https://dribbble.com/shots/360605-UI-Language-Switch)
- [Loading animation dots inspiration](https://dribbble.com/search/loading%20animation%20dots)
- [Dot loading animation inspiration](https://dribbble.com/search/dot%20loading%20animation)

## Sidebar Strategy Configurator

## Core decision

The sidebar should remain the system’s live control deck, but it should no longer read like a raw long-form settings file.

It should become a **staged strategy console**:

- compact
- sculpted
- grouped by intent
- visually bonded to the currently active page

## Recommended information architecture

The sidebar should be reorganized into five decision groups.

### 1. Session and market context

Purpose:

- things that affect interpretation of all downstream signals

Contents:

- execution market
- timeline mode or execution timing shortcut
- home region
- base currency
- language fallback access

Why first:

- these settings define the viewing lens for the rest of the app

### 2. Core position engine

Purpose:

- the central strategy posture

Contents:

- minimum equivalent exposure
- maximum equivalent exposure
- rebalance threshold
- composite module enabled
- simple module enabled

Why second:

- this is the “main dial cluster” of the system

### 3. Leverage and safety gate

Purpose:

- aggressive behavior permissions

Contents:

- allow leveraged ETF
- leverage allowed below VIX
- clear leverage at or above VIX
- foreign asset cap toggles and limits

Why third:

- this cluster reads like a guarded subsystem, almost like an arming panel

### 4. Signal construction

Purpose:

- how the system decides trend and health

Contents:

- short / medium / long MA
- confirmation days
- VIX tier boundaries and multipliers

Why fourth:

- these are more advanced, slower-changing strategy internals

### 5. Advanced caps and exception modules

Purpose:

- specialty throttles and contingency logic

Contents:

- drawdown cap
- no new high cap
- period rise cap
- trend quality cap
- extreme risk cap
- fixed exposure tiers

Why fifth:

- these should read like optional overlays, not baseline setup

## Presentation model for the sidebar

### Recommendation: do not use a full “entire system flips over” interaction

A full panel-flip is visually interesting, but it is not the right primary interaction for this product.

Reasons:

- the sidebar is frequently adjusted, so hidden-back-surface logic adds friction
- Streamlit is not ideal for rich persistent 3D transform states
- a flip interaction is better for reveal moments than for dense operational controls
- flipping the whole panel risks feeling theatrical rather than precise

### Better alternative: hinged reveal and layered deck behavior

Use a **layered deck** model instead:

- the sidebar remains front-facing
- each section can expand like a mechanical drawer or hinged instrument cover
- a focused group can visually “lift” from the surface
- advanced groups can open from beneath a clipped header plate

This preserves the premium interaction feeling without harming efficiency.

### Where a flip effect is still appropriate

Use flip-like behavior only for small, local moments:

- strategy summary plate flips to show “current values” vs “default values”
- one compact profile tile flips to show metadata
- a metric chip flips between interpreted label and raw numeric basis

That keeps the flourish controlled and meaningful.

## Recommended sidebar visual model

### Overall structure

The sidebar should feel like a jewel-lined instrument cabinet:

- no rounded rectangles except pills
- clipped section plates
- pearl-rim dividers
- capsule sliders embedded within faceted frames
- section headers that look engraved, not boxed

### Section anatomy

Each section should have:

- a title plate
- a one-line strategic summary
- a compact set of controls
- a tiny “impact” note

Example:

`Core Position Engine`

`150% -> 300% range · rebalance when delta exceeds 30%`

This lets the user scan the system before opening every knob.

### System coupling

The sidebar should know which page is active and slightly re-prioritize itself.

Examples:

- on `Daily Signal`, emphasize session context and core position engine
- on `Backtest`, emphasize signal construction and execution timing
- on `Market Health`, emphasize leverage and safety gate

This does not require changing the settings model. It only requires adaptive ordering, expanded state, or highlight state in the UI.

## Empty-State And Auto-Refresh Strategy

## Core principle

If a page requires data to be meaningful, entering that page should trigger preparation automatically.

Do not show a blank page that asks the user to manually produce the first useful state unless the operation is genuinely destructive, expensive, or ambiguous.

### Recommended behavior by page

#### Daily page

Current state:

- shows “not loaded yet” when there is no session data

Target state:

- auto-run using the current date and current settings on first entry
- show a compact `Preparing` animation
- render the page only after data is ready

Reference point:

- [trend_system/interfaces/streamlit/pages/daily_page.py](/Users/leolinum/Documents/LEOLRS0-3/trend_system/interfaces/streamlit/pages/daily_page.py:57)

#### Market Health page

Current state:

- shows “not loaded yet” if there is no cached health data

Target state:

- auto-run on first entry with the current default start date
- if the user later changes the date, allow explicit refresh

Reference point:

- [trend_system/interfaces/streamlit/pages/market_health_page.py](/Users/leolinum/Documents/LEOLRS0-3/trend_system/interfaces/streamlit/pages/market_health_page.py:56)

#### Backtest page

Current state:

- shows “backtest has not been run yet”

Target state:

- auto-run on first entry using the selected preset default
- retain manual control for changed dates and advanced options

Reference point:

- [trend_system/interfaces/streamlit/pages/backtest_page.py](/Users/leolinum/Documents/LEOLRS0-3/trend_system/interfaces/streamlit/pages/backtest_page.py:106)

#### Chart empty state

Current state:

- shows `No chart data available.`

Target state:

- this message should be rare
- when the parent page can still recover automatically, the page should refresh upstream first
- only show a chart-level absence state when data truly exists but that specific series is unavailable

Reference point:

- [trend_system/interfaces/streamlit/shared/tradingview_chart.py](/Users/leolinum/Documents/LEOLRS0-3/trend_system/interfaces/streamlit/shared/tradingview_chart.py:40)

## Autoload interaction model

### Page entry flow

On first navigation to a data page:

1. detect that required data is missing for the current fingerprint
2. enter `preparing` state immediately
3. run the page’s default load action
4. write session state
5. render the real page body

### Fingerprint behavior

The current code already uses page fingerprints for stale detection.

This is good groundwork:

- daily fingerprint exists
- backtest fingerprint exists

The next step is to distinguish:

- `missing`
- `preparing`
- `ready`
- `stale`

Instead of only:

- data present
- data absent

## “Preparing” Animation

## Goal

The loading state should feel deliberate, light, and premium.

It should not look like a generic spinner.

## Recommended animation concept

Use a **three-dot pearl drift** animation:

- three small dots
- one in Prussian Blue
- one in Racing Green
- one in Palace Wall Red
- all softened by semi-transparent pearl bloom

Material character by dot:

- Prussian Blue dot: mineral, with a lapis-like depth and subtle cool marbling
- Racing Green dot: metallic, with a narrow reflective sweep
- Palace Wall Red dot: matte, softly diffused, like a finely sanded lacquer surface

Behavior:

- dots drift horizontally in a short capsule path
- each dot subtly expands and contracts
- one dot leads, one follows, one trails faintly
- total loop around `1.2s to 1.6s`

Optional layer:

- faint dust dots disperse behind the active dot in very low opacity

### Copy treatment

Primary label:

- `Preparing`
- `準備中`

Secondary line examples:

- `Collecting market data`
- `Calibrating strategy view`
- `Rendering signal surface`

The copy should change with the stage, similar to the current backtest status flow, but with more polished visual treatment.

## Recommended loading orchestration

### Daily page

- `Preparing`
- `Collecting market data`
- `Reading signal structure`
- `Rendering allocation view`

### Market Health page

- `Preparing`
- `Collecting price history`
- `Checking MA120 / MA200 structure`
- `Rendering health surface`

### Backtest page

There is already a useful staged status pattern in [trend_system/interfaces/streamlit/pages/backtest_page.py](/Users/leolinum/Documents/LEOLRS0-3/trend_system/interfaces/streamlit/pages/backtest_page.py:116).

This should become the design benchmark for the other pages, but restyled with the new motion and shell language.

## Design Recommendation Summary

### Best answer for the sidebar

Do this:

- keep the sidebar as the live strategy console
- restructure it by decision groups
- make sections feel like lifted plates or instrument drawers
- allow local hinge / reveal behavior
- adapt emphasis by active page

Do not do this:

- full 3D flip of the entire strategy panel as the default interaction

### Best answer for empty pages

Do this:

- auto-load page data on first entry
- show `Preparing` instead of “not loaded”
- reveal real content only after data is ready

Do not do this:

- show “no data” or “not loaded” as the first experience for a page that can prepare itself

## Implementation Roadmap

### Phase 1

- create a shared `preparing` presentation component
- standardize page data states: `missing`, `preparing`, `ready`, `stale`

### Phase 2

- apply auto-prepare behavior to Daily, Market Health, and Backtest
- remove first-load “not loaded yet” copy from those pages

### Phase 3

- regroup sidebar sections
- add section summaries and adaptive emphasis by current page

### Phase 4

- add premium shell styling, pearl edges, clipped section plates, and capsule controls
- optionally add small flip behavior to summary tiles only

## Practical next step

The most valuable next implementation step is:

1. define a shared page-preparation helper
2. convert Daily and Market Health to auto-prepare on first entry
3. then redesign the sidebar sections around the five-group model

That sequence improves behavior first, then upgrades the shell around it.
