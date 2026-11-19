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

The planner requires full commit SHAs, complete local history, a clean working tree, and the base as the exact merge base of customized HEAD and upstream target. It rejects repository-local custom merge/filter drivers and external filesystem monitors, reports upstream/local path changes and rights/notice changes, and runs a non-mutating Git three-way merge preflight.

When `.usc/customizations.json` is present, the planner also validates the registry and reports affected customizations, path ownership, protection modes, and required regression-test IDs. It blocks invalid registries, upstream edits to registered custom-only paths, protected mixed-ownership deletions, affected `block_for_review` entries, and unmapped overlapping changes. A missing registry remains backward-compatible (`not_configured`).

Planning does not fetch, checkout, merge, write files, update refs, execute hooks, or run project scripts. A `ready_for_review` status is not approval or proof of semantic compatibility.

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

## Integration acceptance rules

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

The verifier re-checks candidate branch, original customized HEAD, upstream MERGE_HEAD, unresolved conflicts, unstaged/untracked changes, and exact tree SHA. It also requires a passing result with a non-empty evidence reference for every registry-required test ID and records the required/verified ID sets. Stale or modified candidates and failed or incomplete test evidence are blocked. It never runs source scripts or tests.

**Trust limitation:** evidence is reviewer-supplied JSON. The verifier checks its structure and binds it to the candidate tree, but does not independently authenticate the CI provider, log URLs, reviewer identity, or test execution. The report explicitly sets `evidence_authenticated=false`. A trusted CI evidence policy is still required before automatic acceptance.

## Current implementation: explicit acceptance and baseline advancement

After successful evidence validation and a human review of the evidence source, run:

```bash
usc sync-accept --path ./customized-repository \
  --candidate-report ../candidate-report.json \
  --verification-report ../verification-report.json \
  --upstream-url https://github.com/OWNER/UPSTREAM-REPOSITORY \
  --evidence-reviewed --approve
```

Acceptance:
- Requires explicit `--approve` and `--evidence-reviewed`; evidence is not independently authenticated by the current verifier.
- Re-runs the read-only sync plan and confirms the original branch, original HEAD, and clean worktree still match the candidate's starting point.
- Confirms the candidate is still in the expected uncommitted merge state and its tree SHA matches the verification report.
- Creates a two-parent upstream merge commit and a separate provenance commit in the isolated candidate clone.
- Records the canonical upstream URL, base/target/customized SHAs, changed paths, rights acknowledgement, reviewer, verification/test references, merge SHA, and tool version.
- Writes `.usc/upstream-baseline.json` with the newly imported upstream SHA.
- Fetches the prepared candidate tip into the original repository and fast-forwards the original branch only after another clean-HEAD/branch check.

If a pre-update gate fails, the original branch and baseline remain unchanged. Acceptance does not run project scripts or tests. The baseline and provenance become part of the original branch only when the fast-forward succeeds.

The verifier supports independently authenticated GitHub Actions evidence when supplied with the trusted repository, workflow ID/path/blob SHA, and exact-tree snapshot report. Reviewer-supplied evidence remains explicitly unauthenticated when authenticated mode is not used. Automated candidate discard and recovery before provenance/baseline commits remain outstanding.


## Recovery after an interrupted acceptance

If the candidate's merge commit, provenance commit, and baseline file were committed but the original branch was not advanced, use:

\`\`\`bash
usc sync-recover --path ./customized-repository \\
  --candidate-report ../candidate-report.json --approve
\`\`\`

Recovery checks that the candidate worktree is clean, the committed provenance/baseline files exactly match their checked-out contents, the baseline and provenance reference the same merge commit, and the customized/upstream merge parent order is correct. It then fast-forwards only if the original branch is still at the recorded customized SHA and clean. Repeating recovery after success returns \`already_applied\`.

If interruption happened before provenance and baseline were committed, recovery deliberately refuses; discard the candidate and create a fresh one. The original customized branch remains the authoritative copy.


## Selective synchronization and structured-file merge — future specification

The current implementation classifies Git paths and uses Git's three-way merge. It does not yet understand feature ownership inside a file or perform format-aware merges. These are separate future capabilities and must not be described as implemented.

### Selective synchronization

Use the machine-readable customization registry defined in `docs/custom-feature-protection-policy.md` to add context to path-level planning. The registry must not replace Git history or the three-way merge base. It should identify:
- Which custom features/configurations/contracts are touched by each changed path.
- Whether the changed area requires preservation checks, targeted regression tests, or human resolution.
- Cases where upstream and custom code share a file and therefore cannot safely be handled by whole-file exclusion or replacement.

Do not introduce blanket ignore/exclude rules as the primary protection mechanism. Excluding an entire mixed-ownership file can prevent upstream security fixes; replacing it wholesale can erase custom behaviour. If the registry cannot confidently map a change, mark it unknown and block acceptance pending review.

### Structured merge

A later adapter may support format-aware three-way merges for structured configuration files. Implement JSON first, then a deliberately limited YAML subset only after parser and round-trip behaviour is proven. Each merge must:
- Parse base, upstream, and customized versions independently and reject invalid or ambiguous input.
- Merge only explicitly supported object/key structures using the three-way base.
- Treat conflicting scalar edits, delete-versus-edit, duplicate keys, unsupported YAML features, and ambiguous list edits as conflicts.
- Preserve custom-only keys and upstream-only keys where the merge is unambiguous.
- Avoid silently changing comments, ordering, formatting, unknown fields, or semantics; if the chosen parser cannot preserve required source fidelity, emit a reviewable conflict/diff instead of rewriting.
- Validate the merged result against the relevant schema and project-specific tests.
- Run only in the isolated candidate and retain the existing explicit verification and acceptance gates.

No format-aware merge may bypass protected-feature checks, rights review, candidate verification, provenance, or human approval. Dependency declarations and package manifests must not receive special merge rules until their ecosystem-specific semantics and scripts/side effects are covered by tests.


## Maintainer live end-to-end validation fixture

A dedicated, marker-gated GitHub Actions fixture exercises the complete remote evidence path. A push to a `usc-verify/**` branch first runs the trusted `CI` workflow. When that run has completed successfully, the separate `USC Live Sync Acceptance` workflow checks out the exact snapshot commit, creates a fresh local customized clone from fixture refs, recreates the candidate, and requires its index tree to equal the published snapshot tree.

The second workflow then invokes the normal authenticated `sync-verify` implementation against the completed CI push run and invokes `sync-accept` only in its disposable local clone. It asserts that the custom-only feature and upstream-only change both survive and that baseline/provenance point to the accepted upstream target. It never pushes the accepted product branch. This is a maintainer smoke test using synthetic fixtures; it does not replace real customer-project testing or semantic regression coverage.


## Live validation record — 20 November 2026

The synthetic public-GitHub end-to-end fixture completed successfully:

- Snapshot commit: `04f4f14b01be8be97bf361490c7167bc3ec0722c`
- Snapshot tree: `6510cfc50e811eef6e7ca6fbae0176e488391b19`
- Customized fixture commit: `7dfc827e516fc5dbcc207f3871460581623f88f0`
- Upstream target: `bf5199c67ec6797baa54ba8a3b12671f1ff25ff5`
- Authenticated CI push run: https://github.com/JennyJoshua/universal-software-customizer/actions/runs/44633531926
- Follow-on acceptance workflow: https://github.com/JennyJoshua/niversal-software-customizer/actions/runs/44633580230

The test recreated the candidate from the fixture's public GitHub refs, confirmed its tree exactly matched the published snapshot, authenticated the completed CI run, and accepted the candidate only in a disposable local clone. It verified that the custom-only feature remained intact, the upstream-only improvement was included, and baseline/provenance advanced to the selected upstream target.

This validates the tested remote workflow mechanics. It is not a substitute for application-specific regression tests or proof of semantic preservation across arbitrary customized software. The remote verification branch is intentionally retained for now because the available GitHub integration does not expose a safe delete-ref operation.
