# UI Expansion Notes

## Purpose

Prepare the Streamlit interface for a larger redesign without forcing that redesign now.

The current goal is to leave clear extension seams for:

- a future page-based UI refresh
- optional migration to a TypeScript frontend later
- additional modules that should not require editing the entire UI shell

## Current Direction

The Streamlit UI should move toward a page registry model.

That means:

- each page has a stable page key
- each page has a title resolver
- each page has a dedicated render entrypoint
- the shell decides navigation
- page internals decide page rendering

## Future Module Slot

The project now reserves a `future_module` page slot.

This slot is intentionally a placeholder:

- it is not exposed in the current navigation
- it has a stable key for future activation
- it documents where a new module should plug in

When the future module is ready, the intended activation path is:

1. implement its service contract
2. add its page renderer
3. enable the page in the registry
4. wire any sidebar inputs it needs through shared context

## Shared UI Contract

New pages should depend on shared context rather than directly assuming the entire global Streamlit shell.

The shared context should carry:

- resolved config path
- mutable working settings
- current UI language

This keeps page migration incremental and avoids another monolithic UI file.

## Why This Matters

Without a page contract, every new module forces more edits into `gui.py`.

With the contract in place, new modules can be added by:

- implementing a service
- adding a page renderer
- registering the page

That leaves much more room for the future UI optimization pass.
