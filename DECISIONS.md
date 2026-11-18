# Project Decisions

| ID | Decision | Status | Reason |
|---|---|---|---|
| D-001 | Build a reusable framework, not a one-off product fork. | Accepted | Reuse the workflow across eligible projects. |
| D-002 | Preserve upstream source and record exact source revision. | Accepted | Traceability and updateability. |
| D-003 | Use technology-specific adapters behind a common core. | Accepted | Avoid unsafe universal source rewriting. |
| D-004 | Start with public Git repositories and a web adapter. | Accepted | Narrow first milestone. |
| D-005 | Use Python for initial orchestration. | Proposed | Simple CLI and test support. |
| D-006 | Prefer free/open-source tools and GitHub Actions. | Accepted | Keep costs low. |
| D-007 | Licence evidence is a mandatory human-review gate, not automated clearance. | Accepted | Public availability does not grant unrestricted reuse. |
| D-008 | Preserve notices and attribution. | Accepted | Respect upstream and third-party rights. |
| D-009 | Generate a dry-run plan before applying changes. | Accepted | Make transformations reviewable. |
| D-010 | Require approval before material changes and distribution. | Accepted | Avoid unintended scope and publishing. |
| D-011 | No hosted SaaS or customer portal in the first release. | Accepted | Prove core workflow first. |
| D-012 | Retain current repository name: niversal-software-customizer. | Recorded | Match the repository the user created; renaming can be considered separately. |

Material scope, architecture, hosting, cost, and distribution changes must be recorded here. Per-project licence decisions must not be generalized to all upstream projects.
