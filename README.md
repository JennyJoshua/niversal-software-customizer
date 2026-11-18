# Universal Software Customizer

A framework for responsibly inspecting, rebranding, adapting, testing, and building eligible open-source software into independently branded products.

## Purpose

The workflow imports or references an upstream Git repository, inspects its technology and licence evidence, identifies supported customization points, prepares dry-run plans, applies approved changes through technology-specific adapters, runs tests, and records provenance.

This is not a universal source-code converter, reverse-engineering tool, or method for removing another author's rights or attribution.

## Current status

**Foundation + static inspection + rights-evidence reporting + read-only upstream sync planning.** The tool can inspect source repositories, collect project/dependency rights evidence, and compare a customized Git working copy with a newer upstream commit using a read-only three-way merge preflight. Candidate integration, branding transformations, and production adapters are not yet implemented.

## First capabilities

Install and run:

```bash
python -m pip install -e ".[dev]"
usc inspect --path ./source-project
usc inspect --repo-url https://github.com/OWNER/REPOSITORY --revision v1.2.3
usc licences --path ./source-project --output rights-review.json
usc sync-plan --path ./customized-repository --base-sha <last-imported-upstream-sha> --target-sha <new-upstream-sha>
```

Inspection, rights scanning, and sync planning do not execute project code. The sync planner requires a complete local Git history, a clean working tree, and a recorded base commit that is an ancestor of both the customized commit and selected upstream target. Fetching is a separate user-controlled step.

A clean sync plan is only **ready for review**; it is not an integration, approval, or guarantee that all semantic interactions are safe. Conflicts block the plan. The planner never changes the working tree or refs.

The rights report inventories root and nested evidence, extracts supported dependency declarations, and highlights asset and trademark review areas. It does not execute project code or determine legal permission. Every rights report remains human-review-required and blocks customization.

## Principles

- Respect upstream licences, notices, trademarks, and third-party rights.
- Public source code is not automatically free for every commercial use.
- Prefer documented configuration, themes, assets, plugins, and extension points over fragile source rewriting.
- Keep upstream source and customized output distinguishable.
- Make changes reproducible, reviewable, and reversible.
- Use free/open-source tools and GitHub Actions where practical.
- Never execute untrusted project scripts during static inspection or sync planning.
- Never silently overwrite custom work or automatically resolve merge conflicts.

## Repository guide

- PROJECT_REQUIREMENTS.md — scope and functional requirements
- ARCHITECTURE.md — proposed system design
- DECISIONS.md — accepted project decisions
- ROADMAP.md — phased delivery
- docs/ — licensing, security, workflow, upstream sync, and adapter guidance
- configuration/ — example project and branding configuration
- engine/ — core orchestration package
- tests/ — automated tests
- .github/workflows/ — CI checks

## Legal notice

This project provides technical workflow support, not legal advice. A human must confirm that the upstream licence and all third-party rights permit the intended use, distribution, and branding. If terms are missing, conflicting, or unclear, stop and obtain qualified advice.
