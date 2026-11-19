# Universal Software Customizer

A framework for responsibly inspecting, rebranding, adapting, testing, and building eligible open-source software into independently branded products.

## Purpose

The workflow imports or references an upstream Git repository, inspects its technology and licence evidence, identifies supported customization points, prepares dry-run plans, applies approved changes through technology-specific adapters, runs tests, and records provenance.

This is not a universal source-code converter, reverse-engineering tool, or method for removing another author's rights or attribution.

## Current status

**Foundation + static inspection + rights-evidence reporting + upstream sync planning, isolated candidate integration, explicit acceptance, provenance, recovery, GitHub Actions evidence authentication, customization registry v1 validation, and registry-aware upstream change impact reporting.** A synthetic public-GitHub snapshot-to-authenticated-verification-to-acceptance lifecycle has passed. Snapshot publication remains a separate manual push in normal user workflows. Registry-aware planning identifies affected customizations and required regression test IDs. Verification and acceptance now require passing evidence for every declared test ID, bound to the exact candidate tree; USC validates supplied evidence but does not execute project tests. Branding transformations and production adapters are not yet implemented.

## First capabilities

Install and run:

```bash
python -m pip install -e ".[dev]"
usc inspect --path ./source-project
usc inspect --repo-url https://github.com/OWNER/REPOSITORY --revision v1.2.3
usc licences --path ./source-project --output rights-review.json
usc customization-check --path ./customized-repository
usc sync-plan --path ./customized-repository --base-sha <last-imported-upstream-sha> --target-sha <new-upstream-sha>
usc sync-candidate --path ./customized-repository --base-sha <last-imported-upstream-sha> --target-sha <new-upstream-sha> --workspace ../upstream-candidate --approve --output ../candidate-report.json
usc sync-snapshot --path ./customized-repository --candidate-report ../candidate-report.json --push-url https://github.com/OWNER/FORK.git --output ../snapshot-report.json
usc sync-verify --candidate-report ../candidate-report.json --evidence ../verification-evidence.json --output ../verification-report.json
usc sync-accept --path ./customized-repository --candidate-report ../candidate-report.json --verification-report ../verification-report.json --upstream-url https://github.com/OWNER/REPOSITORY --evidence-reviewed --approve
```

Inspection, rights scanning, and sync planning do not execute project code. The sync planner requires a complete local Git history, a clean working tree, and a recorded base commit that is the exact merge base of the customized branch and selected upstream target. Fetching is a separate user-controlled step.

A clean sync plan is only **ready for review**; it is not an integration approval or guarantee that all semantic interactions are safe. Conflicts block the plan. The planner never changes the working tree or refs.

Candidate creation requires explicit `--approve`, and `--rights-reviewed` when common licence/notice files changed. It creates a full, separate clone and leaves the merge uncommitted for review. The original customized repository is not changed. If preflight detects conflicts, candidate creation is blocked before a clone is made. If an unexpected conflict occurs during candidate merge, the candidate remains unresolved for manual review or discard.

The new `sync-verify` command validates evidence against the exact candidate tree, including branch/commit identity, merge state, absence of unresolved conflicts and unstaged changes, tree SHA, timezone-aware reviewer timestamp, and successful test-result references. In authenticated mode it independently checks the completed public GitHub Actions run, exact snapshot commit/tree/parent, trusted workflow identity, and successful jobs. It does not execute project tests. Acceptance is a separate explicit command that requires approval and a clean, unchanged original branch.

The rights report inventories root and nested evidence, extracts supported dependency declarations, and highlights asset and trademark review areas. It does not execute project code or determine legal permission. Every rights report remains human-review-required and blocks customization.

The `customization-check` command validates `.usc/customizations.json` against registry v1 rules, checks exact referenced files and symlink safety, and reports stale or ambiguous declarations. A missing registry is reported as `not_configured` so existing projects continue unchanged. Registry validation is read-only. Sync planning correlates upstream changes with registered customization paths, reports affected features and required regression test IDs, and blocks invalid registries, custom-only upstream edits, protected deletions, and unmapped overlapping changes. `sync-verify` requires a passing result for each required test ID and binds the report to the exact candidate tree SHA. `sync-accept` recomputes the sync plan and refuses acceptance if required IDs are missing, failed, stale, or mismatched. USC validates the evidence supplied by the reviewer; it does not execute the project tests.

## Repository identity

The canonical GitHub repository is [JennyJoshua/universal-software-customizer](https://github.com/JennyJoshua/universal-software-customizer). The former `niversal-software-customizer` name is historical only; use the canonical name in all new links, documents, and handovers. See [repository identity](docs/repository-identity.md).

## Registry-aware synchronization

`usc sync-plan` now includes a `customization_impact` section when a valid `.usc/customizations.json` exists. It identifies affected registry entries, mapped changed paths, protection modes, and required test IDs. Invalid registries and unsafe protected-path changes block the plan. Required tests are enforced as a verification and acceptance gate: each required ID must have a passing result tied to the exact candidate tree. USC checks supplied evidence but does not execute project tests. Projects without a registry retain the previous planning behaviour.

## Principles

- Respect upstream licences, notices, trademarks, and third-party rights.
- Public source code is not automatically free for every commercial use.
- Prefer documented configuration, themes, assets, plugins, and extension points over fragile source rewriting.
- Keep upstream source and customized output distinguishable.
- Make changes reproducible, reviewable, and reversible.
- Use free/open-source tools and GitHub Actions where practical.
- Never execute untrusted project scripts during static inspection or sync planning.
- Never silently overwrite custom work or automatically resolve merge conflicts.
- Apply the [Custom Feature Protection Policy](docs/custom-feature-protection-policy.md) to every adapter and upstream synchronization workflow.

## Repository guide

- PROJECT_REQUIREMENTS.md — scope and functional requirements
- ARCHITECTURE.md — proposed system design
- DECISIONS.md — accepted project decisions
- ROADMAP.md — phased delivery
- docs/ — licensing, security, workflow, upstream sync, custom feature protection, and adapter guidance
- configuration/ — example project and branding configuration
- engine/ — core orchestration package
- tests/ — automated tests
- .github/workflows/ — CI checks

## Legal notice

This project provides technical workflow support, not legal advice. A human must confirm that the upstream licence and all third-party rights permit the intended use, distribution, and branding. If terms are missing, conflicting, or unclear, stop and obtain qualified advice.
