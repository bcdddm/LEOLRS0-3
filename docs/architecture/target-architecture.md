# Target Architecture

## Goal

Restructure the system so strategy logic remains in Python, while user interfaces become replaceable.

This design keeps room for a future TypeScript interface layer without forcing an immediate rewrite.

## Design Principles

- Keep strategy, backtest, and health-check logic independent from Streamlit widgets.
- Route user-facing entrypoints through stable service contracts.
- Isolate external dependencies such as Yahoo Finance, GitHub, and Telegram behind adapters.
- Treat Streamlit, CLI, and any future API as thin interface layers.
- Prefer additive migration over a big-bang rewrite.

## Layer Model

### Core

Pure business logic and calculations.

- `trend_system.signals`
- `trend_system.backtest`
- `trend_system.portfolio`
- `trend_system.exposure_rules`
- `trend_system.timezones`
- `trend_system.trade_timeline`

Core code should not know about Streamlit, GitHub, Telegram, or widget state.

### Services

Use-case orchestration built on top of core modules.

- `daily_signal_service`
- `backtest_service`
- `healthcheck_service`

Services accept explicit request objects and return explicit result objects.

### Adapters

Wrappers around external systems.

- market data provider
- notification provider
- GitHub repository content updates
- workflow configuration updates

Adapters are where side effects belong.

### Interfaces

Human or machine entrypoints.

- Streamlit UI
- CLI
- future HTTP or RPC API
- future TypeScript frontend

Interfaces should only gather input, call services, and render output.

## Extraction Targets

The first extraction targets are:

1. Backtesting
2. Health check
3. Daily signal

Each target should become a standalone service that can later be exposed through:

- Streamlit
- CLI
- Python API
- TypeScript frontend through an HTTP boundary

## Migration Strategy

### Phase 1

Add service and adapter seams without changing user-visible behavior.

### Phase 2

Move CLI to services first.

### Phase 3

Move Streamlit pages to services one page at a time.

### Phase 4

Extract GitHub and workflow mutation logic out of `gui.py`.

### Phase 5

If needed later, add a separate API interface for a TypeScript frontend.

## Non-Goals For Now

- No immediate full UI rewrite
- No immediate change from TOML config to another format
- No immediate HTTP server
- No immediate replacement of Python core logic
