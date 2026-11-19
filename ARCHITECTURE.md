# Architecture

## Design

Use a small orchestration core plus technology-specific adapters. The core controls workflow order and safety gates; adapters understand project conventions. Fail closed when a safe customization or synchronization strategy cannot be identified.

## Pipeline

Source URL and pinned revision -> static inspection and rights evidence -> human rights review -> establish upstream baseline -> upstream update check and read-only three-way sync plan -> conflict/review gate -> isolated sync integration -> tests and provenance -> branding configuration -> adapter dry-run plan -> human approval -> isolated branding transformations -> tests/build -> final provenance and attribution output.

## Core modules

- Source intake: fetch a pinned upstream revision into a disposable workspace.
- Inspector: inventory files and extract metadata without executing project code.
- Technology detector: identify known families from explicit file signals.
- Licence evidence scanner: locate licence and notice files and dependency metadata; no legal conclusions.
- Policy gate: block unresolved rights, prohibited transformations, conflicts, and missing approvals.
- Upstream baseline manager: record upstream URL, imported baseline SHA, customized revision, and selected update target.
- Sync planner: compare the previous upstream baseline, new upstream target, and customized tree; emit a read-only path-level report.
- Sync integrator: integrate only an approved, conflict-free plan in a disposable/recoverable working copy; never auto-resolve conflicts.
- Configuration validator: validate versioned project and branding profiles.
- Planner: produce a read-only list of branding operations.
- Orchestrator: call the selected adapter and verification commands.
- Provenance writer: record source revisions, decisions, changes, tools, and results.

## Upstream synchronization model

Treat the upstream repository and the customized product as distinct histories. Keep the exact upstream commit last imported as the merge base; do not redefine the baseline merely because upstream has advanced. For an update, compare:
1. Base: last imported upstream commit.
2. Upstream: newly selected upstream commit.
3. Customized: current customized branch/tree.

The first implementation should use Git's three-way merge semantics in a disposable clone/worktree, with a read-only preflight report. Classify clean non-overlapping changes separately from overlapping/conflicting paths. Include additions, modifications, deletions, and renames in the report. A conflict, ambiguous rename, missing baseline, shallow/incomplete history, or unsupported Git state must stop the operation. Do not use blanket ours/theirs strategies, overwrite files, or silently drop local commits.

Only after a clean dry run, rights gate, and explicit integration approval may the candidate result be created. Keep the original customized ref recoverable and record the new imported upstream SHA. Re-run tests and compare the resulting diff against both upstream changes and the customization baseline. Failed checks leave the original customized ref unchanged.

## Adapter contract

Each adapter should implement detection, inspection, planning, application, and verification. Plans identify paths, operation types, reasons, and expected effects. Application rejects paths outside the adapter allowlist. Adapters must not own or bypass upstream synchronization safety.

## Initial technology choices

Python for orchestration and tests; JSON configuration initially; pytest for tests; GitHub Actions for CI with pinned action versions and least-privilege permissions.

## Security boundaries

Treat source code, manifests, scripts, and metadata as untrusted. Static inspection must not execute code. Sync and builds run only in disposable isolated workspaces with minimal permissions and no repository secrets. Validate paths against traversal and symlink escapes. Keep imported source and generated output separate. Do not automatically publish.

## Planned layout

- configuration/: example project and branding profiles
- engine/customizer/: orchestration and shared models
- adapters/web/: first technology adapter
- docs/: licensing, security, upstream sync, usage, and adapter guidance
- tests/: fixtures and automated checks
- .github/workflows/: CI

Do not add Windows, Android, Python-package, or Node-specific adapters until each has a real fixture, documented rules, and automated tests.


## Customization registry and selective synchronization — planned

Add a declarative customization registry as a policy input to the sync planner. The registry maps stable feature IDs to categories, implementation paths or supported structural selectors, protection modes, and targeted regression-test identifiers. It supplements Git's base/upstream/customized comparison; it does not replace that comparison or become a whole-file exclusion list.

The planner should correlate changed paths with registered custom features and report affected features, required tests, unknown mappings, and blocked conditions. A path shared by upstream and custom functionality must be treated as mixed ownership. If safe attribution is uncertain, stop for review rather than dropping upstream changes or overwriting local behaviour.

Only after registry enforcement and preservation tests are reliable should the architecture add structured merges. JSON is the first candidate format; YAML is deferred until a safe subset and source-fidelity guarantees are demonstrated. Structured merge adapters must be isolated, three-way, schema-validated, and subordinate to the same verification, rights, provenance, and approval gates as ordinary sync.
