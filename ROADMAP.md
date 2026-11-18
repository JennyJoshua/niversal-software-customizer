# Roadmap

## Phase 0 — Foundation
- [x] Define purpose, scope, principles, and architecture.
- [x] Define licence, security, and approval gates.
- [ ] Add project skeleton and CI checks.
- [ ] Create issue-based implementation backlog.

## Phase 1 — Static source inspection
- [ ] Accept a public Git URL and pinned revision.
- [ ] Inspect repository tree without executing source code.
- [ ] Detect common web manifests and build metadata.
- [ ] Produce a structured inspection report.
- [ ] Add fixture repositories and tests.

## Phase 2 — Licence and dependency evidence
- [ ] Detect common licence and notice files.
- [ ] Extract dependency names and declared licence metadata where available.
- [ ] Flag missing or conflicting evidence.
- [ ] Produce human-review checklist and provenance record.
- [ ] Block workflow when review is unresolved.

## Phase 3 — Configuration and planning
- [ ] Define versioned project and branding JSON schemas.
- [ ] Validate names, colors, URLs, assets, and safe paths.
- [ ] Create adapter detection and dry-run plan interfaces.
- [ ] Test invalid and unsafe configuration.

## Phase 4 — First web adapter
- [ ] Select a permissively licensed test fixture.
- [ ] Support only explicitly detected branding locations.
- [ ] Implement product name, logo/favicon, and theme changes where supported.
- [ ] Preserve attribution and upstream notices.
- [ ] Generate diff and change report.
- [ ] Test unrelated files remain unchanged.

## Phase 5 — Isolated build and provenance
- [ ] Run fixture tests/builds in disposable environment.
- [ ] Capture tool versions, logs, and outcomes.
- [ ] Generate provenance manifest.
- [ ] Produce artifacts without automatic public release.

## Phase 6 — Additional adapters
- [ ] Prioritize based on real project demand.
- [ ] Add one adapter at a time with fixtures and tests.
- [ ] Consider Android/Windows only after toolchains and rights requirements are validated.

A phase is complete only when its acceptance criteria are tested, documented, and reflected in GitHub Issues. Planned capabilities must not be described as implemented.
