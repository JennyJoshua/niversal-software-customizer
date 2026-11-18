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

First fetch the relevant upstream history into the local Git repository using your normal Git client. Do not fetch untrusted submodules or run project scripts as part of this step. Identify:
- The exact upstream commit SHA last imported into the customized product (base).
- The exact newer upstream commit SHA to evaluate (target).
- The current customized commit (the checked-out HEAD).

Then run:

```bash
usc sync-plan --path ./customized-repository \
  --base-sha <last-imported-upstream-sha> \
  --target-sha <new-upstream-sha> \
  --output ../upstream-sync-plan.json
```

The output path must be outside the repository. The planner requires:
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

## Candidate acceptance (not yet implemented)

A later batch will add controlled verification and provenance acceptance. Until then, do not treat a clean candidate as a completed upstream update. The original customized ref remains the authoritative copy.

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

## Candidate acceptance (not yet implemented)

Even a `verification_passed` report does not change the original customized repository. Explicit acceptance, race-safe original-HEAD checks, baseline advancement, and complete provenance are still future work. Until then, keep the original customized ref authoritative.
