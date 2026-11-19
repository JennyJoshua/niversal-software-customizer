# Roadmap

## Completed foundation and implementation batches

- [x] Repository purpose, scope, architecture, principles, and approval gates documented.
- [x] Python project skeleton, CLI, tests, and GitHub Actions CI established.
- [x] Static source inspector implemented and merged (PR #4).
- [x] Licence and third-party rights evidence scanner implemented and merged (PR #5).
- [x] Safe upstream synchronization requirements and architecture specified (PR #7).
- [x] Read-only, baseline-aware upstream sync planner implemented and merged (PR #8).
- [x] Isolated, uncommitted candidate integration implemented and merged (PR #9).
- [ ] Trusted candidate verification and evidence authentication.

## Phase 3 — Safe upstream synchronization

- [x] Require full base and target commit SHAs.
- [x] Reject shallow history, dirty working trees, and invalid/stale baselines.
- [x] Produce deterministic path-level upstream/local change classifications.
- [x] Run a non-mutating Git three-way merge preflight and block conflicts.
- [x] Flag common licence/notice file changes for human rights review.
- [x] Require explicit approval and rights-review acknowledgement when relevant.
- [x] Create candidate integration in a separate full clone without hardlinks or submodules.
- [x] Preserve original customized HEAD and working-tree state during candidate creation.
- [x] Validate external test evidence against the candidate branch, merge state, and exact Git tree SHA.
- [x] Require timezone-aware verification timestamps, reviewer identity, passing test entries, and evidence references.
- [ ] Authenticate CI evidence independently and define a trusted verification policy.
- [x] Add explicit candidate acceptance with original-HEAD/branch/clean-tree rechecks and fast-forward-only update.
- [x] Advance the stored upstream baseline only with the accepted branch update.
- [x] Record sync provenance, reviewer/test evidence, rights acknowledgement, and resulting merge commit.
- [ ] Add automated candidate discard/recovery and interruption recovery tests.
- [ ] Test deletion/rename edge cases and end-to-end failed acceptance/recovery.

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
