# Module Boundaries

## Allowed Dependencies

### Core

Core modules may depend on:

- standard library
- `pandas`
- other core modules

Core modules must not depend on:

- `streamlit`
- GitHub API helpers
- Telegram helpers
- CLI argument parsing
- filesystem layout assumptions outside config loading

### Services

Services may depend on:

- core modules
- request/result models
- adapters through narrow interfaces

Services should avoid direct UI imports.

### Adapters

Adapters may depend on:

- external SDKs
- HTTP clients
- filesystem
- environment secrets

Adapters must not depend on Streamlit session state.

### Interfaces

Interfaces may depend on:

- services
- adapters only when wiring dependencies
- presentation helpers

Interfaces must not embed business rules that belong in services or core.

## Immediate Refactor Seams

### From `trend_system.gui`

Move out first:

- GitHub content update helpers
- workflow configuration read/write helpers
- daily signal orchestration
- market health orchestration
- backtest orchestration

Keep in Streamlit for now:

- layout
- widget declarations
- charts
- PDF button rendering

## Stable Service Contracts

The following service entrypoints should remain stable:

- `run_daily_signal(...)`
- `run_backtest_use_case(...)`
- `run_healthcheck(...)`
- `prepare_future_module(...)`

Future interfaces should only need these contracts plus config loading.

## Future TypeScript Integration Boundary

When the frontend changes later, TypeScript should call an interface boundary that maps 1:1 to service requests/results.

That means request and result shapes must remain:

- serializable
- explicit
- UI-agnostic

## Anti-Patterns To Avoid

- Adding new business logic directly inside Streamlit callbacks
- Adding new GitHub or workflow mutation logic directly in `gui.py`
- Returning raw widget state from services
- Mixing report formatting with data retrieval and core calculations in one function
