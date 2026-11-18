# Roadmap

## Completed foundation and implementation batches

- [x] Repository purpose, scope, architecture, principles, and approval gates documented.
- [x] Python project skeleton, CLI, tests, and GitHub Actions CI established.
- [x] Static source inspector implemented and merged (PR #4).
- [x] Licence and third-party rights evidence scanner implemented and merged (PR #5).

## Phase 3 — Safe upstream synchronization specification and engine

- [ ] Record upstream source identity and last-imported baseline SHA.
- [ ] Define the three-way model: prior upstream baseline, selected upstream target, customized tree.
- [ ] Produce deterministic, read-only sync plans with path-level change classifications.
- [ ] Detect overlapping edits, conflicts, renames/deletions, missing baselines, and unsupported states.
- [ ] Integrate only in a disposable/recoverable working copy after rights and approval gates.
- [ ] Preserve the original customized ref and emit a complete sync/provenance report.
- [ ] Test clean upstream updates, local-only custom changes, overlapping conflicts, deletion/rename cases, and rollback safety.

## Phase 4 — Configuration and branding planning

- [ ] Define versioned project and branding JSON schemas.
- [ ] Validate names, colors, URLs, assets, and safe paths.
- [ ] Create adapter detection and deterministic dry-run plan interfaces.
- [ ] Test invalid and unsafe configuration.
- [ ] Confirm branding operations cannot modify upstream sync metadata or protected notices.

## Phase 5 — First web adapter

- [ ] Select a permissively licensed test fixture.
- [ ] Support only explicitly detected branding locations.
- [ ] Implement product name, logo/favicon, and theme changes where supported.
- [ ] Preserve attribution and upstream notices.
- [ ] Generate diff and change report.
- [ ] Test unrelated files remain unchanged.
- [ ] Test that later upstream updates preserve branding changes or stop on conflicts.

## Phase 6 — Isolated build and provenance

- [ ] Run fixture tests/builds in disposable environments.
- [ ] Capture tool versions, logs, and outcomes.
- [ ] Generate provenance manifest including upstream baseline and sync history.
- [ ] Produce artifacts without automatic public release.

## Phase 7 — Additional adapters

- [ ] Prioritize based on real project demand.
- [ ] Add one adapter at a time with fixtures and tests.
- [ ] Consider Android/Windows only after toolchains and rights requirements are validated.

A phase is complete only when its acceptance criteria are tested, documented, and reflected in GitHub Issues. Planned capabilities must not be described as implemented.
