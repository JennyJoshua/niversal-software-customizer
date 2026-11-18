# Project Requirements

## Purpose

Build a reusable, configuration-driven framework that helps produce separately branded, responsibly adapted builds of existing open-source software where the upstream licence and technical architecture permit it.

## In scope

1. Reference or import an upstream Git repository at an exact branch, tag, or commit.
2. Inspect repository structure, manifests, dependencies, build scripts, tests, licence files, notices, and customization surfaces.
3. Detect supported project families using explainable evidence.
4. Accept versioned project and branding configuration.
5. Generate a dry-run plan before changing files.
6. Apply only adapter-defined transformations to allowlisted paths.
7. Run configured tests/builds in an isolated environment.
8. Produce a change manifest, attribution bundle, and provenance report.
9. Require human approval before material changes and distribution.

## Out of scope

- Reverse engineering closed-source software.
- Circumventing licence, access-control, DRM, or payment restrictions.
- Removing copyright notices, attribution, licence texts, or required source offers.
- Automatically declaring a project legally safe for commercial use.
- Blind find-and-replace across arbitrary source code.
- Major feature development without separate approval.
- Running untrusted build scripts on a privileged runner.
- Hosted SaaS, customer accounts, billing, or automatic public publishing in the first release.

## Functional requirements

- Source intake records the resolved upstream commit SHA.
- Static inspection does not execute upstream code.
- Licence evidence scanner locates licence/notice files and dependency metadata; it does not issue legal conclusions.
- Technology detection returns unsupported when confidence is insufficient.
- Branding configuration is schema-validated and rejects unsafe paths.
- Dry-run plan lists every proposed file change, reason, and risk.
- Application occurs only after approval and in a separate working copy.
- Verification reports actual command outcomes and logs.
- Provenance records upstream URL/revision, review status, config digest, changed files, tests, tool versions, and artifact metadata.

## Non-functional requirements

- Reproducible, transparent, secure, portable, low-cost, and maintainable.
- Least privilege and isolated builds; no secret exposure to untrusted code.
- Each adapter independently testable.
- Documentation readable on mobile.

## Initial release acceptance

- Inspect a repository without modifying it.
- Detect a supported web application family and safely reject unsupported projects.
- Validate a branding configuration.
- Produce a dry-run report.
- Block changes when licence status is unresolved or approval is absent.
- Prove through tests that an adapter changes only allowlisted files.
- CI passes and provenance is recorded.
