# Architecture

## Design

Use a small orchestration core plus technology-specific adapters. The core controls workflow order and safety gates; adapters understand project conventions. Fail closed when a safe customization point cannot be identified.

## Pipeline

Source URL and pinned revision -> static inspection -> technology detection and licence evidence -> human review -> branding configuration -> adapter dry-run plan -> human approval -> isolated working copy -> approved transformations -> tests/build -> provenance and attribution output.

## Core modules

- Source intake: fetch a pinned upstream revision into a disposable workspace.
- Inspector: inventory files and extract metadata without executing project code.
- Technology detector: identify known families from explicit file signals.
- Licence evidence scanner: locate licence and notice files and dependency metadata; no legal conclusions.
- Policy gate: block unresolved rights, prohibited transformations, and missing approvals.
- Configuration validator: validate versioned project and branding profiles.
- Planner: produce a read-only list of proposed operations.
- Orchestrator: call the selected adapter and verification commands.
- Provenance writer: record source revision, decisions, changes, tools, and results.

## Adapter contract

Each adapter should implement detection, inspection, planning, application, and verification. Plans identify paths, operation types, reasons, and expected effects. Application rejects paths outside the adapter allowlist.

## Initial technology choices

Python for orchestration and tests; JSON configuration initially; pytest for tests; GitHub Actions for CI with pinned action versions and least-privilege permissions.

## Security boundaries

Treat source code, manifests, scripts, and metadata as untrusted. Static inspection must not execute code. Builds run only in disposable isolated runners with minimal permissions and no repository secrets. Validate paths against traversal and symlink escapes. Keep imported source and generated output separate. Do not automatically publish.

## Planned layout

- configuration/: example project and branding profiles
- engine/customizer/: orchestration and shared models
- adapters/web/: first technology adapter
- docs/: licensing, security, usage, and adapter guidance
- tests/: fixtures and automated checks
- .github/workflows/: CI

Do not add Windows, Android, Python-package, or Node-specific adapters until each has a real fixture, documented rules, and automated tests.
