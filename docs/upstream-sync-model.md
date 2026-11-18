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
- Requires full commit SHAs, complete local history, a clean working tree, and the base as the exact merge base of customized HEAD and upstream target.
- Rejects repository-local custom merge/filter drivers and external filesystem monitors.
- Reports upstream and local changed paths, path overlaps, and upstream rights/notice file changes.
- Uses `git merge-tree --write-tree` for a non-mutating three-way merge preflight.
- Marks a plan blocked when Git reports merge conflicts.
- Does not fetch, checkout, merge, write files, update refs, execute hooks, or run project scripts.

A `ready_for_review` status is not approval and not proof of semantic compatibility. It only means Git's preflight found no merge conflict. The planner is not an integration acceptance engine.

## Current implementation: isolated candidate creation

The command is:

```bash
usc sync-candidate --path ./customized-repository --base-sha <base-sha> --target-sha <target-sha> --workspace ../candidate --approve
```

Add `--rights-reviewed` when the plan flags changed licence/notice files, after a human has reviewed the evidence.

Candidate creation:
- Re-runs the read-only plan and blocks before cloning if conflicts are detected.
- Requires explicit approval and, when flagged, explicit rights-review acknowledgement.
- Requires target and customized commits to be reachable from local refs.
- Creates a full separate clone with copied objects (no hardlinks) and no submodules.
- Creates a dedicated candidate branch and performs a normal three-way merge without committing.
- Leaves any unexpected merge conflicts in the candidate for manual resolution; it never auto-resolves.
- Verifies the original customized HEAD and working-tree status remain unchanged.

The candidate is left uncommitted and is only `candidate_ready_for_review` when Git reports no merge conflicts. The command does not run tests/builds, update the source repository, advance the baseline, finalize provenance, or authorize distribution.

## Plan contents

A deterministic, read-only plan reports:
- Base, target, and customized revision identifiers.
- Changed upstream and local paths, including rename/copy records.
- Path classifications: upstream-only, local-only, and both changed.
- Merge conflict paths/details and blocked reasons.
- Changes to common licence/notice filenames requiring renewed rights review.
- Whether integration approval is still required and whether integration occurred.

## Integration acceptance rules for the next implementation batch

- Inspect the complete candidate diff against both the upstream target and original customized state.
- Re-check rights evidence when upstream changes affect licences, dependencies, assets, fonts, icons, datasets, or trademarks.
- Run approved tests/builds in an isolated environment; do not execute untrusted scripts with secrets or privileged access.
- Preserve the original ref until candidate verification succeeds and an explicit acceptance step is performed.
- Record old/new upstream SHAs, customized revision, changed paths, conflict decisions, test results, reviewer decision, and resulting commit SHA.
- Keep upstream synchronization separate from branding transformations.

## Failure behavior

Missing baseline, shallow/incomplete history, unsupported Git state, unsafe paths, merge conflicts, failed tests, or changed/unreviewed rights evidence must block acceptance. Failure must leave the original customized ref unchanged.

## Test matrix

1. Upstream-only change integrates into candidate while local custom-only files remain byte-for-byte unchanged.
2. Local-only custom change survives an upstream update.
3. Same-line/same-file overlapping edits produce a conflict and no automatic resolution.
4. Non-overlapping edits to the same file are identified as both-changed and preflighted by Git.
5. Upstream deletion of a locally customized file blocks or reports conflict; it never silently deletes the custom file.
6. Rename plus local edit is detected and safely blocked if mapping is ambiguous.
7. Missing baseline or shallow history blocks planning.
8. Failed candidate verification leaves the original customized ref unchanged.
9. Candidate creation requires explicit approval and rights-review acknowledgement when applicable.
10. Successful acceptance records the new upstream baseline and complete provenance.

## Delivery status

Read-only planning and isolated, uncommitted candidate creation are implemented. Candidate verification, acceptance, recovery automation, and final provenance remain future work. Do not describe the full upstream update workflow as complete until those capabilities pass their tests.


## Current implementation: candidate evidence validation

The command is:

```bash
usc sync-verify --candidate-report ../candidate-report.json \
  --evidence ../verification-evidence.json \
  --output ../verification-report.json
```

The candidate report is emitted by `sync-candidate --output ../candidate-report.json`. Before verification, review the full candidate diff and run approved tests/builds in a disposable, unprivileged environment without production secrets. The evidence JSON must identify:
- The exact candidate index tree SHA (from `git -C ../candidate write-tree`).
- A passed verification status and at least one passing test result with a log/report/CI evidence reference.
- Reviewer identity and an ISO-8601 timestamp with an explicit timezone.
- The rights-review acknowledgement matching the candidate report.

The verifier re-checks candidate branch, original customized HEAD, upstream MERGE_HEAD, unresolved conflicts, unstaged/untracked changes, and exact tree SHA. Stale or modified candidates and failed test evidence are blocked. It never runs source scripts or tests.

**Trust limitation:** evidence is reviewer-supplied JSON. The verifier checks its structure and binds it to the candidate tree, but does not independently authenticate the CI provider, log URLs, reviewer identity, or test execution. The report explicitly sets `evidence_authenticated=false`. A trusted CI evidence policy is still required before automatic acceptance.

## Acceptance remains outstanding

A `verification_passed` report does not change the original customized repository. The next batch must add explicit acceptance with compare-and-swap protection against an original HEAD change, ensure the candidate still matches the verified tree, commit the merge with the customized commit as first parent and upstream target as second parent, advance the upstream baseline only after success, and write complete provenance. Failure must leave the original customized ref and baseline unchanged.
