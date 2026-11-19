# Review of upstream synchronization reference projects

**Reviewed:** 19 November 2026  
**Purpose:** Extract reusable design ideas for Universal Software Customizer (USC). These repositories are technical references, not replacement architectures. This review is based on their public GitHub repository metadata, current README files, root licence files where available, and recent commit history. It is not a complete security audit or a legal opinion.

## Findings matrix

| Reference | Useful pattern | Important limitation or risk | Licence and recent activity | USC decision |
|---|---|---|---|---|
| [actions-template-sync](https://github.com/AndreasAugustin/actions-template-sync) | Selective ignore rules, scheduled/manual runs, and update pull requests rather than silently changing a product branch. | Its README advertises lifecycle hooks that inject custom code into the workflow, and its sync model copies the source repository except ignored paths. USC must not execute untrusted upstream hooks or rely on broad file exclusions for mixed-ownership files. | Root LICENSE is MIT. Recent repository commits include 6 September 2026 updates and release 2.6.0. | Adopt the PR-based delivery and monitoring concepts later; keep USC's isolated candidate, exact-tree verification, rights gates, and explicit acceptance. |
| [template-sync](https://github.com/template-tools/template-sync) | Format-aware merging for JSON, YAML, TOML, INI, line-set files, and selected package metadata; creates pull requests for review. | Format-specific merge rules can alter formatting or semantics. Package scripts/dependency declarations are especially sensitive. The README badge says 0BSD and the checked-in LICENSE text is also the 0BSD-style grant, despite earlier secondary descriptions that called it BSD-2-Clause. | Checked-in LICENSE text grants 0BSD-style permission. Recent commits on 17 November 2026 show active maintenance. | Strongest technical reference for a future structured-merge adapter. Start with JSON; defer YAML and ecosystem manifests until fidelity and conflict behaviour are tested. |
| [ForkSync](https://github.com/loongxjin/forksync) | Upstream status monitoring, sync history, desktop workflow visibility, and AI-assisted explanations of conflicts. | README describes AI agents resolving conflicts and options that can auto-commit. That is too much authority for USC's preservation model. Its README displays an MIT badge linking to LICENSE, but the repository's root LICENSE fetch returned 404 during this review; do not reuse code until a valid licence is confirmed. Desktop Wails/React architecture is not a fit for USC's current Python core. | Latest commits returned by GitHub API were 12–13 July 2026. Licence remains unverified because the referenced root file was unavailable. | Use AI only to explain conflicts and suggest review questions. It must never select/apply resolutions, waive rules, or approve acceptance. Monitoring/history ideas may be revisited. |
| [upstream-sync-bot](https://github.com/RavelloH/upstream-sync-bot) | Scheduled upstream monitoring and review-PR fan-out using scoped, short-lived GitHub App installation tokens. | Requires a GitHub App, private-key secrets, write permissions for Contents and Pull Requests, and also Workflows. It is designed for upstream maintainers distributing updates to many downstream repositories, not as USC's core local merge engine. | Root LICENSE is MIT. Latest commits returned were 13–23 May 2026. | Defer GitHub App distribution. If later adopted, use least-privilege installation scopes and PR-only delivery; never grant broad write access by default. |
| [fork-template](https://github.com/Le-Fork/fork-template) | Simple scheduled/manual upstream check workflow. | Its documented flow merges and pushes directly to the fork's default branch and asks users to create a PAT with repo and workflow scopes. This bypasses USC's candidate review/verification gates and creates a broad credential risk. | Root LICENSE is MIT. Latest commits returned were 8–9 November 2025. | Do not adopt its direct-push workflow or PAT model. A scheduled trigger may be considered only if it opens a review PR and does not mutate the product branch. |

## Cross-project conclusions

1. **Protect behaviour, not only files.** A file may contain both upstream and custom logic. Whole-file exclusion can block important upstream fixes; whole-file replacement can destroy custom functionality. USC needs a feature-level registry linked to regression tests.
2. **Prefer review pull requests.** Scheduled monitoring should notify and prepare candidates, not automatically merge or advance the imported baseline.
3. **Treat structured merges as adapters.** JSON/YAML/TOML/package-manifest merging needs format-specific semantics, validation, and conservative conflict handling. It must remain subordinate to USC's three-way candidate workflow.
4. **Keep AI advisory.** AI may summarize changes, explain conflict context, identify likely affected registry entries, and suggest tests. It must not edit conflict resolutions, run acceptance, or waive human approval.
5. **Keep credentials out of untrusted upstream execution.** Do not execute upstream lifecycle hooks, project scripts, or AI-generated commands with repository secrets or privileged permissions.
6. **Verify licensing per file before reuse.** A repository-level licence does not automatically clear dependencies, assets, fonts, icons, datasets, or trademarks. ForkSync's missing root licence file is a specific unresolved reuse blocker.

## Implementation priority

- First finish USC's existing Phase 3 live remote snapshot-to-verification-to-acceptance test and remaining failure cases.
- Next specify and implement the declarative customization registry and feature-level regression mapping.
- Then add registry-aware selective reporting and mixed-ownership fixtures.
- Only then prototype JSON structured merging; consider restricted YAML later.
- Add scheduled monitoring that opens review PRs after the core lifecycle is proven.
- Defer GitHub App fan-out and AI-assisted resolution. AI conflict explanation may be added as non-authoritative reporting.

## Reuse and attribution status

No source code has been copied from any of these projects as part of this review. This document records design observations only. Any future code reuse requires a separate review of the exact source files, licence notices, dependencies, provenance, and compatibility with USC's security model. A root licence alone is not a complete rights clearance.
