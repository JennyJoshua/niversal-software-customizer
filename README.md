# Universal Software Customizer

A framework for legally inspecting, rebranding, adapting, testing, and building eligible open-source software into independently branded products.

## Purpose

The workflow imports or references an upstream Git repository, inspects its technology and licence evidence, identifies supported customization points, prepares a dry-run plan, applies approved changes through technology-specific adapters, runs tests, and records provenance.

This is not a universal source-code converter, reverse-engineering tool, or method for removing another author's rights or attribution.

## Current status

Foundation stage. The repository currently defines the intended scope and initial project skeleton. A production customization engine is not yet implemented.

## Principles

- Respect upstream licences, notices, trademarks, and third-party rights.
- Public source code is not automatically free for every commercial use.
- Prefer documented configuration, themes, assets, plugins, and extension points over fragile source rewriting.
- Keep upstream source and customized output distinguishable.
- Make changes reproducible, reviewable, and reversible.
- Use free/open-source tools and GitHub Actions where practical.
- Never execute untrusted project scripts during static inspection.

## First milestone

A small Python command-line foundation and a web application adapter supporting only clearly identified branding surfaces. Unsupported or ambiguous projects must be rejected safely.

## Repository guide

- PROJECT_REQUIREMENTS.md — scope and functional requirements
- ARCHITECTURE.md — proposed system design
- DECISIONS.md — accepted project decisions
- ROADMAP.md — phased delivery plan
- docs/ — licensing, security, workflow, and adapter guidance
- configuration/ — example project and branding configuration
- engine/ — core orchestration package
- adapters/ — technology-specific adapters
- tests/ — automated tests
- .github/workflows/ — CI checks

## Legal notice

This project provides technical workflow support, not legal advice. A human must confirm that the upstream licence and all third-party rights permit the intended use, distribution, and branding. If terms are missing, conflicting, or unclear, stop and obtain qualified advice.
