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

## Current implementation: read-only sync planner

The CLI command is:

```bash
usc sync-plan --path ./customized-repository --base-sha <base-sha> --target-sha <target-sha>
```

The planner:
- Requires full commit SHAs, complete local history, a clean working tree, and the base as an ancestor of both sides.
- Reports upstream and local changed paths, path overlaps, and upstream rights/notice file changes.
- Uses `git merge-tree --write-tree` for a non-mutating three-way merge preflight.
- Marks a plan blocked when Git reports merge conflicts.
- Does not fetch, checkout, merge, write files, update refs, execute hooks, or run project scripts.

A `ready_for_review` status is not approval and not proof of semantic compatibility. It only means Git's preflight found no merge conflict. The planner is not yet a candidate integration engine.

## Plan contents

A deterministic, read-only plan reports:
- Base, target, and customized revision identifiers.
- Changed upstream and local paths, including rename/copy records.
- Path classifications: upstream-only, local-only, and both changed.
- Merge conflict paths/details and blocked reasons.
- Changes to common licence/notice filenames requiring renewed rights review.
- Whether integration approval is still required and whether integration occurred.

## Integration rules for the next implementation batch

- Fetch and integrate in a disposable clone/worktree with no secrets and no privileged hooks.
- Require a complete common history and a valid base.
- Use normal three-way Git merge semantics; do not use blanket ours/theirs strategies.
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
4. Non-overlapping edits to the same file are identified as both-changed and preflighted by Git.
5. Upstream deletion of a locally customized file blocks or reports conflict; it never silently deletes the custom file.
6. Rename plus local edit is detected and safely blocked if mapping is ambiguous.
7. Missing baseline or shallow history blocks planning.
8. Failed verification leaves the original customized ref unchanged.
9. Successful candidate records the new upstream baseline and complete provenance.

## Delivery status

The read-only planner is implemented. Candidate integration, automated test/build verification, and provenance acceptance remain future work. Do not describe the full upstream update workflow as complete until those capabilities pass their tests.
