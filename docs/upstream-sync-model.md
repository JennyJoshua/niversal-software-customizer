# Upstream Synchronization Model

## Goal

Allow a customized product to receive selected upstream fixes and improvements without silently overwriting or discarding its custom-built changes.

## Required identities

For each customized project, persist:
- Canonical upstream repository URL.
- Exact upstream commit SHA last imported (the sync base).
- Selected upstream target commit SHA for the proposed update.
- Customized branch/ref and its current commit SHA.
- Tool and sync-model version.

A branch or tag name alone is not a stable baseline; resolve it to a commit SHA.

## Three-way model

Compare three states:
- **Base:** exact upstream commit last imported into the customized product.
- **Upstream:** newly selected upstream commit.
- **Customized:** current customized tree, including user changes since the base.

The base must remain unchanged during planning. Do not move it forward until a candidate integration is accepted.

## Plan contents

A deterministic, read-only plan must report:
- Base, target, and customized revision identifiers.
- Incoming upstream commits and changed paths.
- Local customized changes since the base.
- Path classifications: upstream-only, local-only, both changed, add/add, modify/delete, rename, and unresolved/ambiguous.
- Potential conflicts and protected paths (licence/notice files, sync metadata, generated outputs).
- Whether history is complete enough for a reliable three-way comparison.
- Explicit blocked/ready status and reasons.

## Integration rules

- Fetch and integrate in a disposable clone/worktree with no secrets and no privileged hooks.
- Require a complete common history and a valid base.
- Use normal three-way Git merge semantics; do not use blanket conflict preference flags.
- If a conflict or ambiguous rename occurs, stop and require explicit human resolution outside automatic sync.
- Never overwrite the existing customized ref during planning or candidate creation.
- Preserve the original ref until the candidate has passed review and configured tests.
- Re-check rights evidence when upstream changes affect licences, dependencies, assets, fonts, icons, datasets, or trademarks.
- Do not apply branding transformations as part of upstream sync; keep synchronization and branding as separate, auditable operations.

## Verification and provenance

Before acceptance, inspect the complete candidate diff against both the upstream target and the original customized state. Run configured tests/builds in an isolated environment. Record the revisions, path report, conflicts/resolutions, reviewer decision, test commands/results, and resulting commit SHA.

## Failure behavior

Missing baseline, shallow/incomplete history, unsupported Git state, unsafe paths, merge conflicts, failed tests, or changed/unreviewed rights evidence must block acceptance. Failure must leave the original customized ref unchanged.

## Test matrix

1. Upstream-only change integrates while local custom files remain byte-for-byte unchanged.
2. Local-only custom change survives an upstream update.
3. Same-line/same-file overlapping edits produce a conflict and no integration.
4. Upstream deletion of a locally customized file blocks or reports conflict; it never silently deletes the custom file.
5. Rename plus local edit is detected and safely blocked if mapping is ambiguous.
6. Missing baseline or shallow history blocks planning.
7. Failed verification leaves the original customized ref unchanged.
8. Successful candidate records the new upstream baseline and complete provenance.

## Delivery status

This document defines the required behavior. It does not mean an upstream synchronization engine exists yet. The engine will be implemented and verified in a dedicated batch before the first branding adapter is allowed to depend on it.
