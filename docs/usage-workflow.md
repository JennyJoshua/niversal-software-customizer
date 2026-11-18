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
- The base commit to be an ancestor of both the customized HEAD and upstream target.
- A clean customized working tree, including no untracked files.

The plan classifies upstream-only, local-only, and overlapping changed paths; performs Git's non-mutating three-way merge preflight; reports conflicts; and flags changes to common licence/notice filenames for renewed human rights review.

A result of `ready_for_review` means only that Git's merge preflight found no conflicts. It does not merge, write source files, update refs, approve rights, run tests, or authorize distribution. `blocked` means do not integrate automatically. The original working tree and refs remain unchanged by planning.

## Candidate integration (not yet implemented)

After a clean plan, rights review, and explicit approval, a future command will create a candidate integration in a disposable/recoverable workspace. It must preserve the original customized ref, stop on conflicts, run approved verification in isolation, and record provenance. Do not treat the current sync planner as an integration tool.

## Safety and limitations

- Inspection, rights scanning, and sync planning are read-only and do not execute application code, scripts, installers, hooks, or builds.
- The sync planner uses local Git objects; it does not fetch remote updates itself.
- A human reviewer must confirm exact licence terms, intended use, obligations, compatibility, and third-party rights before customization or distribution.
- Upstream synchronization must never silently discard custom work.
