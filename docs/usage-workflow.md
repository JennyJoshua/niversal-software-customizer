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

## Mandatory review gate

- The report is evidence, not legal advice or approval.
- Root project licence evidence is distinguished from nested component licences.
- Missing, unreadable, conflicting, or incomplete evidence blocks customization.
- Dependencies, assets, fonts, icons, datasets, documentation, and trademarks require separate review.
- Every report is emitted with `review_status=human_review_required`, `legal_approval=false`, and `customization_gate=blocked`. No command in this phase can mark a project approved.

## Safety and limitations

- Inspection and rights scanning are read-only and do not execute application code, scripts, installers, or builds.
- Common generated/dependency directories and symlinks are excluded.
- Evidence collection is bounded by file-count and file-size limits.
- A human reviewer must confirm the exact licence terms, intended use, obligations, compatibility, and third-party rights before customization or distribution.
