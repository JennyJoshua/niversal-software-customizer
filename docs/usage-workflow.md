# Usage Workflow

## Install for development

```bash
python -m pip install -e ".[dev]"
```

## Inspect a local source directory

```bash
usc inspect --path ./path-to-source
```

## Inspect a public GitHub repository at a pinned revision

```bash
usc inspect --repo-url https://github.com/OWNER/REPOSITORY --revision v1.2.3
```

A branch name, tag, or full commit SHA may be supplied. The report records the resolved commit SHA. Remote inspection is limited to public HTTPS GitHub repositories.

## Collect licence and third-party rights evidence

```bash
usc licences --path ./path-to-source
usc licences --path ./path-to-source --output rights-review.json
```

The report locates root and nested licence, notice, authorship, copyright, and attribution files; extracts project licence declarations and common dependency declarations from supported manifests; and flags assets, fonts, icons, datasets, logos, and trademark review areas.

Supported dependency metadata currently includes npm `package.json`, Composer `composer.json`, Python `pyproject.toml` and `requirements.txt`, Rust `Cargo.toml`, and Go `go.mod`. Dependency licence resolution is not inferred from package names or version constraints.

## Mandatory rights review gate

- The report is evidence, not legal advice or approval.
- Root project licence evidence is distinguished from nested component licences.
- Missing, unreadable, conflicting, or incomplete evidence blocks customization.
- Dependencies, assets, fonts, icons, datasets, documentation, and trademarks require separate review.
- Every report is emitted with `review_status=human_review_required`, `legal_approval=false`, and `customization_gate=blocked`. No command in this phase can mark a project approved.

## Create a read-only upstream sync plan

First fetch the relevant upstream history into the local Git repository using your normal Git client. Do not fetch untrusted submodules or run project scripts as part of this step. Identify the exact newer upstream commit SHA to evaluate (target) and the current customized commit (the checked-out HEAD).

For the first sync, or when deliberately overriding the recorded baseline, supply `--base-sha`. After a sync has been accepted, USC records `.usc/upstream-baseline.json` and a matching provenance record. Subsequent runs can omit `--base-sha` and supply `--upstream-url`; USC validates the repository identity, committed baseline/provenance contents, and history ancestry before using the stored SHA.

Then run:

```bash
usc sync-plan --path ./customized-repository \
  --base-sha <last-imported-upstream-sha> \
  --target-sha <new-upstream-sha> \
  --output ../upstream-sync-plan.json
```

To override the stored baseline explicitly, add `--base-sha <full-sha>`; explicit SHA overrides do not read the baseline file. The output path must be outside the repository. The planner requires:
- A non-bare Git working repository with complete (not shallow) history.
- Full 40- or 64-character commit SHAs.
- The base commit to be the exact merge base of the customized HEAD and upstream target.
- A clean customized working tree, including no untracked files.
- No repository-local custom merge/filter drivers or external filesystem monitor.

The plan classifies upstream-only, local-only, and overlapping changed paths; performs Git's non-mutating three-way merge preflight; reports conflicts; and flags changes to common licence/notice filenames for renewed human rights review.

A result of `ready_for_review` means only that Git's merge preflight found no conflicts. It does not merge, write source files, update refs, approve rights, run tests, or authorize distribution. `blocked` means do not integrate automatically. The original working tree and refs remain unchanged by planning.

## Create an isolated candidate integration

Only after reviewing a clean plan, rights evidence, and the proposed upstream changes, create a candidate:

```bash
usc sync-candidate --path ./customized-repository \
  --base-sha <last-imported-upstream-sha> \
  --target-sha <new-upstream-sha> \
  --workspace ../upstream-candidate \
  --approve \\
  --output ../candidate-report.json
```

If the plan flags changed licence/notice files, complete the human review first and also pass `--rights-reviewed`. This flag records the user's acknowledgement; it is not legal advice or automated licence clearance.

The command requires the customized HEAD and target commit to be reachable from local refs. It creates a separate full clone without hardlinks or submodules, creates a candidate branch, and performs a normal three-way merge without committing. The original customized repository remains untouched.

Possible outcomes:
- `candidate_ready_for_review`: Git completed the merge without conflicts. Inspect the candidate diff and run only approved tests in an isolated environment.
- `blocked`: the sync plan found conflicts and candidate creation stops before creating a clone. Resolve the conflicts manually on a separate copy, then generate a fresh plan.
- An unexpected conflict during candidate merge is left unresolved in the candidate workspace and must be handled manually or discarded.

The candidate is deliberately left uncommitted. This command does not run source scripts, tests, builds, update the original repository, advance the imported baseline, or publish anything. The candidate folder is yours to inspect, retain, or delete.

## Safety and limitations

- Inspection, rights scanning, and sync planning are read-only and do not execute application code, scripts, installers, hooks, or builds.
- Candidate integration runs only Git's built-in merge in a separate clone; repository-local custom Git drivers are rejected before planning.
- The sync planner uses local Git objects; it does not fetch remote updates itself.
- A human reviewer must confirm exact licence terms, intended use, obligations, compatibility, and third-party rights before customization or distribution.
- Upstream synchronization must never silently discard custom work.


## Verify an isolated candidate (evidence validation only)

After reviewing the complete candidate diff, run the approved test/build process in a disposable, unprivileged environment with no production secrets. Do not run untrusted upstream scripts on a personal device or with privileged credentials. Record the candidate's Git index tree SHA:

```bash
git -C ../upstream-candidate write-tree
```

Prepare a reviewer evidence file, for example:

```json
{
  "schema_version": "1.0",
  "verification_status": "passed",
  "reviewer": "Reviewer or team",
  "verified_at": "2026-11-19T10:30:00+10:00",
  "verification_source": "https://github.com/OWNER/REPOSITORY/actions/runs/RUN_ID",
  "candidate_tree_sha": "FULL_TREE_SHA_FROM_GIT_WRITE_TREE",
  "rights_reviewed": false,
  "test_results": [
    {
      "name": "unit and regression tests",
      "passed": true,
      "evidence_ref": "https://github.com/OWNER/REPOSITORY/actions/runs/RUN_ID"
    }
  ]
}
```

Use `rights_reviewed: true` only when the candidate report records that the relevant licence/notice review acknowledgement was given. Every test result must pass and include a reference to its logs or report. The timestamp must include a timezone.

Validate the evidence against the exact candidate:

```bash
usc sync-verify --candidate-report ../candidate-report.json \
  --evidence ../verification-evidence.json \
  --output ../verification-report.json
```

The verifier checks the candidate branch, original customized HEAD, upstream MERGE_HEAD, unresolved conflicts, unstaged/untracked changes, tree SHA, timezone-aware reviewer timestamp, and successful test-evidence structure. It does not execute tests or independently authenticate external CI evidence. The resulting report is not legal approval and does not accept the candidate or update the original repository.

## Explicitly accept a verified candidate

Acceptance is a separate, mutating step. Before running it, inspect the candidate diff, verify the CI/test evidence yourself, and confirm that the candidate report and verification report belong to the same candidate. The original customized repository must still be on the exact branch and commit recorded when the candidate was created, with a clean working tree.

Run:

```bash
usc sync-accept --path ./customized-repository \
  --candidate-report ../candidate-report.json \
  --verification-report ../verification-report.json \
  --upstream-url https://github.com/OWNER/UPSTREAM-REPOSITORY \
  --evidence-reviewed \
  --approve \
  --output ../acceptance-report.json
```

Both flags are deliberate gates: `--evidence-reviewed` acknowledges that supplied test evidence is not independently authenticated; `--approve` authorizes updating the original customized branch. The command rechecks the source HEAD/branch/clean state, rechecks the candidate merge and verified tree SHA, creates the merge and provenance commits in the candidate clone, then fast-forwards the original branch only if its recorded starting point is still unchanged.

On success, the original branch contains the upstream merge plus `.usc/upstream-baseline.json` and a detailed `.usc/provenance/` record. The baseline advances to the selected upstream target only as part of this successful fast-forward. If any pre-update check fails, the original branch remains unchanged. Candidate acceptance never runs project tests or scripts; tests must already have been run in an isolated environment.


## Recover an interrupted acceptance

If acceptance prepared and committed the candidate merge/provenance but stopped before the original branch fast-forward, use the recovery command:

\`\`\`bash
usc sync-recover --path ./customized-repository \\
  --candidate-report ../candidate-report.json \\
  --approve \\
  --output ../recovery-report.json
\`\`\`

Recovery validates the candidate's merge parents, committed provenance, and baseline before fast-forwarding. It refuses a changed or dirty original branch. If interruption occurred before provenance/baseline were committed, recovery deliberately refuses; use the guarded discard command below, then create a fresh candidate. The original branch remains unchanged. Recovery is idempotent after a successful fast-forward.


## Discard an unaccepted or interrupted candidate

Use this command when a candidate is blocked, cannot be accepted, or acceptance stopped before provenance/baseline were committed:

```bash
usc sync-discard --path ./customized-repository \\
  --candidate-report ../candidate-report.json \\
  --approve \\
  --output ../discard-report.json
```

Discard requires explicit `--approve`. It accepts the original uncommitted merge state or the exact two-parent merge commit created immediately before provenance writing. For the committed state, USC checks the parent order, recomputes the expected merge tree, requires a clean candidate, verifies no new target provenance was written, and confirms the baseline still matches the customized parent. It refuses altered or dirty committed candidates. Only the recorded candidate workspace is removed; the original customized repository and its branch are not changed, and remote verification refs are not deleted.


## Independently authenticate GitHub Actions evidence

The optional authenticated mode of sync verification checks a public GitHub Actions run through the GitHub REST API. It requires all of the following:
- The run belongs to the exact trusted OWNER/REPOSITORY.
- It is a completed, successful push run on the exact isolated verification branch recorded in the snapshot report.
- The run uses the expected workflow ID and path.
- Every reported job completed successfully.
- The run's head commit SHA, parent SHA, and tree SHA match the published snapshot and exact candidate tree.
- The workflow file at that commit has the independently pinned trusted blob SHA.

A run URL alone is not evidence. Do not copy a green run from another branch, repository, workflow, or candidate.

The candidate merge is currently uncommitted. Create a verification-only snapshot commit and branch without changing the candidate branch or product branch:

Run this command. It creates a one-parent snapshot commit whose tree exactly matches the candidate and prints a push command; it does not push automatically:

```bash
usc sync-snapshot --path ./customized-repository \
  --candidate-report ../candidate-report.json \
  --push-url https://github.com/OWNER/FORK.git \
  --output ../snapshot-report.json
```

Run the reported push command using your normal GitHub authentication. CI runs on branches under usc-verify/**. This temporary branch is for verification only and must not be merged into the product branch. After the run completes, use its URL with the snapshot report:

```bash
usc sync-verify --candidate-report ../candidate-report.json \
  --evidence ../verification-evidence.json \
  --snapshot-report ../snapshot-report.json \
  --github-run-url https://github.com/OWNER/FORK/actions/runs/RUN_ID \
  --github-repo OWNER/FORK \
  --workflow-id TRUSTED_WORKFLOW_ID \
  --workflow-path .github/workflows/ci.yml \
  --workflow-blob-sha TRUSTED_WORKFLOW_FILE_BLOB_SHA \
  --output ../verification-report.json
```

The workflow ID and workflow-file blob SHA are trust anchors and must be obtained from a trusted repository revision and maintained deliberately. The current CI workflow ID is 422317206 and the trusted workflow-file blob SHA on main is `0752aaa0aea0d75a300ed9782761bc3012f6a594`. If the workflow file changes, authentication fails until a human reviews the change and deliberately updates the pinned blob SHA. The authenticated mode currently supports public GitHub repositories; private-repository token handling is not included.

Even authenticated CI does not authenticate the human reviewer or legal/rights acknowledgement. Explicit candidate approval remains mandatory.


## Maintainer-only live synchronization fixture

The dedicated fixture under `tests/fixtures/live-upstream-sync/` is used to exercise the full lifecycle against real public GitHub Actions evidence. The fixture is activated only when a published `usc-verify/**` snapshot contains its `trigger.json` marker.

The regular `CI` workflow runs first on the exact snapshot commit. After that push run completes successfully, the separate `USC Live Sync Acceptance` workflow:
1. Checks out the exact snapshot commit and reads the fixture's pinned base/upstream/customized refs.
2. Creates a fresh local customized clone and runs `usc sync-candidate`.
3. Confirms the candidate tree is byte-for-byte identical to the published snapshot tree and that the snapshot has the customized commit as its sole parent.
4. Runs `usc sync-verify` against the already-completed CI push run, using the pinned CI workflow ID, path, and blob SHA.
5. Runs `usc sync-accept` only inside the temporary local clone, then asserts both the upstream-only improvement and custom-only feature remain present and the baseline/provenance advance correctly.

The workflow has read-only repository permissions and does not push an accepted product branch. Its acceptance is a disposable integration test, not approval to update a real customized product. The marker is deliberately absent from ordinary project snapshots, so this maintainer test does not run for normal verification branches.


## Validate a product customization registry

Create `.usc/customizations.json` in the customized project, then run:

```bash
usc customization-check --path ./customized-repository
```

Registry v1 uses `schema_version: "1.0"` and a non-empty `customizations` array. Each entry declares a stable kebab-case `id`, `name`, `purpose`, a category, a protection mode, and one or more exact file paths with ownership set to `custom_only` or `mixed`.

Protection modes:
- `preserve`: only for custom-only files; it is not proof of semantic preservation.
- `require_regression_tests`: requires one or more stable `test_ids`; v1 records these identifiers but does not execute the tests.
- `block_for_review`: requires a human-readable `review_note`.

Optional `evidence_refs` must be credential-free HTTPS URLs without query strings or fragments. Exact file paths must exist, be regular files, use POSIX separators, and must not traverse symlinks. Globs, absolute paths, `.git`, and `.usc` metadata paths are rejected. See `configuration/customizations.schema.json` for the editor-facing JSON Schema.

A missing registry returns `not_configured` and does not change existing sync behaviour. A valid registry report explicitly sets `feature_protection_enforced: false`: v1 validates declarations only. Registry-aware change classification, regression-test selection, and acceptance enforcement are later implementation steps.
