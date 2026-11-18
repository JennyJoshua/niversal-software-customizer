# Project Requirements

## Purpose

Build a reusable, configuration-driven framework that helps produce separately branded, responsibly adapted builds of existing open-source software where the upstream licence and technical architecture permit it.

## In scope

1. Reference or import an upstream Git repository at an exact branch, tag, or commit.
2. Inspect repository structure, manifests, dependencies, build scripts, tests, licence files, notices, and customization surfaces.
3. Detect supported project families using explainable evidence.
4. Track the exact upstream baseline from which local customizations were derived.
5. Safely evaluate and integrate upstream updates into a customized working copy without silently overwriting custom changes.
6. Accept versioned project and branding configuration.
7. Generate dry-run plans before synchronizing upstream or changing branding files.
8. Apply adapter-defined transformations only to allowlisted paths.
9. Run configured tests/builds in an isolated environment.
10. Produce change manifests, attribution bundles, and provenance reports.
11. Require human review for rights, unresolved conflicts, and material changes before integration or distribution.

## Out of scope

- Reverse engineering closed-source software.
- Circumventing licence, access-control, DRM, or payment restrictions.
- Removing copyright notices, attribution, licence texts, or required source offers.
- Automatically declaring a project legally safe for commercial use.
- Blind find-and-replace across arbitrary source code.
- Silently resolving upstream/custom conflicts or overwriting customized files.
- Major feature development without separate approval.
- Running untrusted build scripts on a privileged runner.
- Hosted SaaS, customer accounts, billing, or automatic public publishing in the first release.

## Functional requirements

- Source intake records the resolved upstream commit SHA.
- Every customized project records its upstream URL, imported baseline SHA, current upstream target SHA, and local customization revision.
- Static inspection does not execute upstream code.
- Licence evidence scanner locates licence/notice files and dependency metadata; it does not issue legal conclusions.
- Technology detection returns unsupported when confidence is insufficient.
- Upstream synchronization uses a three-way comparison of the previous imported baseline, the selected new upstream revision, and the customized working tree.
- Sync planning is read-only and reports incoming changes, local changes, overlapping paths, renames/deletions, and likely conflicts.
- A conflict or uncertain mapping blocks automatic integration; no conflict is auto-resolved.
- Sync runs in a disposable/recoverable working copy. The existing customized working copy remains untouched until a reviewed integration is accepted.
- The sync report records before/after revisions, changed paths, conflicts, decisions, and test outcomes.
- Branding configuration is schema-validated and rejects unsafe paths.
- Branding dry-run plans list every proposed file change, reason, and risk.
- Application occurs only after approval and in a separate working copy.
- Verification reports actual command outcomes and logs.
- Provenance records upstream URL/revisions, review status, config digest, changed files, tests, tool versions, and artifact metadata.

## Non-functional requirements

- Reproducible, transparent, secure, portable, low-cost, and maintainable.
- Least privilege and isolated builds; no secret exposure to untrusted code.
- Each adapter independently testable.
- Documentation readable on mobile.
- No operation may silently discard user-authored/customized content.

## Initial release acceptance

- Inspect a repository without modifying it.
- Detect a supported web application family and safely reject unsupported projects.
- Record a stable upstream baseline and produce a read-only upstream sync plan.
- Demonstrate a clean upstream update, a non-overlapping local customization, and an overlapping conflict in automated fixtures.
- Prove that conflicts block integration and that the original customized working copy remains unchanged.
- Validate a branding configuration and produce a dry-run report.
- Block changes when licence status is unresolved or approval is absent.
- Prove through tests that an adapter changes only allowlisted files.
- CI passes and provenance is recorded.
