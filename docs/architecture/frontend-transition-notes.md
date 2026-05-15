# Frontend Transition Notes

## Current Decision

Python remains the core language.

TypeScript is a future interface option, not a current rewrite target.

## What We Need Before A TypeScript Frontend

### Stable use-case services

The frontend must call stable operations such as:

- load daily signal
- run backtest
- run health check
- save configuration
- read notification/workflow status

### Serializable contracts

Service requests and results should be easy to serialize to JSON.

Current dataclasses are acceptable as an intermediate step. If an HTTP API is added later, these can evolve into API schemas with minimal reshaping.

### Adapter isolation

External integrations must be isolated so the future frontend does not need to know:

- how Yahoo Finance is queried
- how GitHub content is updated
- how Telegram messages are sent

## Suggested Transition Path

1. Keep Streamlit running against Python services.
2. Extract service contracts and adapter seams.
3. Add a lightweight API interface if the frontend move becomes worthwhile.
4. Build the TypeScript frontend against that API.

## Why Not Rewrite Now

- The current bottleneck is coupling, not Python performance.
- A rewrite would delay urgent fixes.
- A service-first migration preserves working strategy logic while lowering future migration cost.
