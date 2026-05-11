# LEOLRS0-3 Update and Fix Log

This English changelog is a translation of the Chinese source changelog. The Chinese file `docs/CHANGELOG.md` remains the source of truth; this file is shown when the UI language is English.

## v0.2.3 - 2026-05-11

### 1. Feature improvement: merged market and trade-mode timeline

The Daily Signal page now shows trading windows on a merged 24-hour timeline. NZX, ASX, and US market sessions are no longer shown as separate progress bars. They now share one market timeline:

- NZ is black.
- Australia / ASX is red.
- US is blue.
- Overlapping market windows use alternating thick diagonal stripes so overlaps are easy to spot.

The trade-mode timeline now runs in parallel beneath the market timeline and uses the same 24-hour scale.

### 2. Feature improvement: trade-mode switch on the Daily Signal page

The Daily Signal page now includes a trade timeline mode selector. The default mode is now `NZ close / US open`, and the trade-mode timeline only displays the currently selected mode instead of showing multiple execution styles at once.

For NZ close / US open mode, timeline markers now use short labels, while full action text is shown in a responsive list below the timeline. This prevents action text from overlapping when multiple deadlines are close together.

### 3. Feature: market and action countdowns

The merged timeline now includes a countdown area:

- If a market is currently open, it shows the current market close countdown.
- If the selected trade mode has an upcoming action, it shows the selected mode action countdown.
- Inside the final 3-hour window, the countdown card switches to white text on a red background.
- If there is no current market close and no selected-mode action, it shows the next market open countdown.

### 4. UI improvement: mobile layout and trade-mode markers

The merged timeline has been refined for mobile screens:

- The market timeline title sits above the market track.
- Trade-mode time labels and the trade-mode title sit below the trade track to avoid overlapping track content.
- The `Now` marker is shown only once, in the trade-mode time-label area.
- The three NZ close / US open action points now use distinct colors: orange for NZX close, blue for US open, and purple for US close.
- Next session mode uses the same design language with a green action marker.
- The 3-hour lead-in highlight before each action now fills the full track height, uses 50% opacity, and matches the action marker color.
- Action copy has been shortened to reduce crowding on mobile screens.

### 5. Verification

Verification commands:

```bash
uv run python -m py_compile trend_system/gui.py
uv run pytest tests/test_timezones.py tests/test_gui_helpers.py -q
uv run pytest -q
```

## v0.2.2 - 2026-05-10

### 1. Feature: debug parameter sweep upgraded to a 50% recommendation report

Following the latest discussion, "Debug mode: parameter sweep" was upgraded from the previous 20% sensitivity scan to a 50% scan. The default factors are now 50%, 75%, 100%, 125%, and 150%. The current full-range scan is preserved, and the current configuration remains the primary comparison baseline.

Scan results now also compare against the default configuration baseline. Each scan row shows both the delta versus the current configuration and the delta versus the default configuration.

### 2. Feature: target date, time window, and ranking objective

The parameter sweep section now includes:

- Target date: choose a key market date as the optimization anchor.
- Time window: set the number of months before and after the target date for local-window backtesting.
- Ranking objective: sort by strategy total return, CAGR, Sharpe, max drawdown, annual volatility, or rebalance count.
- Target-date parameter recommendation table: outputs local-window recommendations alongside the full-range recommendations.

This supports designing different trading modes for different objectives, such as defensive mode, rebound mode, trend continuation mode, and range-filter mode.

### 3. Feature: scan curves and PDF reporting

After a parameter sweep, the UI now outputs:

- Full-range comparison equity curves: current config, default config, best individual parameter, and best unified parameter.
- Target-window comparison equity curves: current config, default config, best individual parameter, and best unified parameter.
- Full-range individual parameter sweep lines.
- Target-window individual parameter sweep lines.

The historical backtest PDF now includes equity curves, exposure curves, parameter sweep recommendations, target-date recommendations, and the scan curves/lines above.

### 4. Feature: scan results show UI names for parameters

Parameter sweep output no longer shows only internal parameter paths. It also shows the corresponding UI name for each parameter, following the current language setting:

- Chinese mode uses Chinese UI names, such as "短期均线", "最大等效仓位", and "low 系数".
- English mode uses English UI names, such as "Short moving average", "Maximum equivalent exposure", and "low multiplier".

Recommendation tables, preferred range tables, individual test tables, unified test tables, PDF recommendations, and sweep line charts all use these UI names.

### 5. Feature: English changelog in English UI mode

Settings Overview still reads `docs/CHANGELOG.md` in Chinese mode. In English mode, it reads `docs/CHANGELOG.en.md`. The Chinese changelog remains the primary record, and the English file is the display translation.

### 6. UI fix: top action button alignment

The following buttons previously sat slightly higher than adjacent date inputs or controls. They now use one shared button alignment helper so their vertical position matches surrounding UI elements:

- Update market health
- Run backtest
- Update daily signal in the Daily Signal page
- Save current settings in Settings Overview
- Save as profile in Settings Overview

There is no separate button named "Fetch today's data" in the current code; the Daily Signal page fetches data and updates the signal through the "Update daily signal" button. The alignment change covers that location.

### 7. Fix: parameter sweeps respect strategy setting caps

Debug parameter sweeps now follow the UI and strategy caps so 50% scans cannot push parameters into invalid ranges. For example:

- Maximum equivalent exposure cannot exceed 300%.
- Trend exposure parameters cannot exceed the current strategy maximum equivalent exposure, and never exceed 300%.
- Minimum rebalance threshold cannot exceed the UI cap of 30%.
- VIX multipliers cannot exceed the UI cap of 5.0.
- Moving average windows and confirmation days cannot exceed their UI caps.

Unified scan notes now also show the clipped test values actually used by the backtest.

### 8. Verification

Verification commands:

```bash
python3 -m py_compile trend_system/gui.py
uv run pytest -q
```

Current result: 58 tests passed.

## v0.2.1 - 2026-05-10

### 1. Feature: historical backtests support weekly contributions

The historical backtest section now includes a "Weekly contribution" input next to initial capital. It can model recurring investment or ongoing deposits.

Calculation rules:

- The first visible backtest row uses initial capital only; no extra contribution is added on that same row.
- Starting from the second visible trading week, the contribution is added before the first trading row of each new week.
- Contributions are applied to the strategy equity curve and all benchmark curves.
- Contributions affect portfolio value and later position-cap checks.
- Return, CAGR, Sharpe, and related metrics are still calculated from daily return series, so cash flows are not counted as investment return.

The new config field is `backtest.weekly_contribution`, defaulting to `0.0`. The default config and all existing profile configs include it so saved TOML files can be read back cleanly.

### 2. Check: settings sidebar save behavior and stability

This version reviewed the settings sidebar structure and stability. The check confirmed that:

- Module settings are written into the in-memory config and can be saved from Settings Overview.
- VIX risk, drawdown risk, windowed no-new-high lock, and trend quality modules are collapsed by default when disabled and expandable when enabled.
- Windowed no-new-high parameters have clear bounds.
- Risk curve boundaries use increasing limits to avoid invalid rule order.
- Exposure inputs are clamped by the base minimum and maximum exposure values.
- All config files pass loading, field checks, and TOML serialization.
- The Streamlit app starts locally and returns HTTP 200 without runtime errors.

Future sidebar modules should also check default completeness, TOML round-tripping, stable widget keys or labels, and whether changing bounds can unexpectedly clamp existing widget values.

### 3. Verification

Verification commands:

```bash
uv run pytest
python3 -m py_compile trend_system/backtest.py trend_system/gui.py trend_system/signals.py trend_system/config.py
uv run streamlit run app.py --server.headless true --server.port 8521
curl -I http://localhost:8521
```

Result at the time: 53 tests passed; the local Streamlit server returned HTTP 200.

## v0.2.0 - 2026-05-10

### 1. Fix: backtest start-date truncation distorted signal state

Shorter backtest windows could produce more rebalances than longer windows using the same LEO config. The root cause was that price downloads and signal calculation started directly from the user-selected backtest start date, which removed warmup history needed by long moving averages, no-new-high counts, drawdown windows, trend quality windows, and 120/200-day MA health checks.

The system now calculates the required warmup length from the active strategy config and downloads enough earlier data internally. Visible output and statistics still start at the user-selected date; warmup data only supplies signal state and does not count toward equity, return, trades, or metrics.

### 2. Fix: first-day return leakage in default backtest benchmarks

Default benchmark curves also had a window-boundary issue. After dynamic warmup, they could still include the return from the last warmup day to the first visible backtest day.

All backtest curves now start from initial capital on the first visible row, and that row's daily return is set to 0. Warmup history only determines the entering state.

Affected curves:

- Strategy equity
- S&P 500 buy and hold
- 3x S&P 500 buy and hold
- S&P 500 120-day timing
- 3x Hold: Cash Below 120MA

### 3. Fix: daily signal and market health also use dynamic warmup

Daily Signal and Market Health previously used the selected data start date directly. If it was too recent, latest signals could miss context needed by long moving averages, trend quality, no-new-high, and drawdown modules.

Both pages now use the same dynamic warmup logic as backtests while preserving the selected date's display meaning.

### 4. Feature adjustment: no-new-high lock became a windowed no-new-high lock

The previous no-new-high module only checked how many consecutive days lacked a high and fixed the lock cap at 100%. It now separates the observation period from the new-high window.

New and retained adjustable parameters:

- Locked exposure cap: the maximum target exposure after the lock triggers.
- Observation days without high: how many recent trading days to inspect.
- New-high window: the high window, for example 200 means a 200-day closing high.

The LEO profile currently uses a 200-day observation period, 200-day high window, and 100% locked exposure cap.

### 5. UI improvement: risk modules are collapsible

Several optional strategy modules now live inside expandable sections to reduce the height of the settings page:

- VIX Risk Module
- Drawdown Risk Module
- Windowed No-New-High Lock Module
- Trend Quality Module

Modules open by default when enabled and stay collapsed when disabled.

### 6. Settings Overview: version and log display

The Settings Overview page now shows the system version and update/fix log at the end of the current settings view. The log is read from local documentation instead of being hard-coded in the UI. The log area has a fixed height and scroll bar so the settings page does not grow endlessly as history accumulates.

### 7. Verification

Automated tests cover:

- Dynamic warmup calculation.
- Windowed no-new-high behavior.
- Zero return on the first visible backtest row.
- Short-window trades matching the corresponding subset of long-window trades.
- System version matching project metadata.
- Settings Overview reading the local changelog.
- Risk modules using collapsible UI containers.

Verification command:

```bash
uv run pytest
```

Result at the time: 52 tests passed.
