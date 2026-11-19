# Roadmap

## Completed foundation and implementation batches

- [x] Repository purpose, scope, architecture, principles, and approval gates documented.
- [x] Python project skeleton, CLI, tests, and GitHub Actions CI established.
- [x] Static source inspector implemented and merged (PR #4).
- [x] Licence and third-party rights evidence scanner implemented and merged (PR #5).
- [x] Safe upstream synchronization requirements and architecture specified (PR #7).
- [x] Read-only, baseline-aware upstream sync planner implemented and merged (PR #8).
- [x] Isolated, uncommitted candidate integration implemented and merged (PR #9).
- [x] Authenticate public GitHub Actions run metadata, jobs, workflow identity, and exact candidate tree against pinned trust anchors.
- [x] Create an isolated one-parent verification snapshot commit/ref with an exact candidate tree, without changing product/candidate HEAD or baseline.
- [ ] Verify the published snapshot end-to-end against a real GitHub Actions run and connect it to acceptance.

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
- [x] Authenticate CI run metadata and pin the workflow file to a trusted blob SHA.
- [x] Create an exact-tree verification snapshot locally without changing the original product branch or candidate merge state.
- [ ] Validate a real published snapshot run through verification and acceptance end-to-end; document safe cleanup of temporary verification refs.
- [x] Resolve the stored upstream baseline by default after validating committed baseline/provenance identity and ancestry; retain explicit SHA overrides.
- [x] Add explicit candidate acceptance with original-HEAD/branch/clean-tree rechecks and fast-forward-only update.
- [x] Advance the stored upstream baseline only with the accepted branch update.
- [x] Record sync provenance, reviewer/test evidence, rights acknowledgement, and resulting merge commit.
- [x] Add explicit recovery for interruption after candidate provenance/baseline commit and before original fast-forward, with committed-record integrity checks.
- [x] Add deletion and rename-with-local-edit conflict tests.
- [ ] Add recovery for interruption before provenance commit, candidate discard automation, and broader failure-injection tests.

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
