# Security Model

## Threat assumptions

Upstream repositories may contain malicious scripts, compromised dependencies, unsafe build hooks, path traversal entries, symlinks, destructive Git hooks/configuration, or instructions designed to expose credentials. Customized branches may also contain valuable user-authored changes that must not be lost during upstream updates.

## Controls

- Static inspection must not execute upstream code.
- Clone/fetch only into disposable workspaces.
- Pin upstream revision and record its resolved SHA and last-imported baseline.
- Treat upstream and customized histories as separate inputs to a three-way sync.
- Produce a read-only sync plan before integration.
- Preserve the original customized ref; create candidate integrations in a separate worktree/branch.
- Stop on conflicts, ambiguous renames, missing/incomplete history, unsupported Git state, or failed verification.
- Never auto-resolve conflicts, use blanket ours/theirs strategies, or overwrite the customized working tree.
- Build with minimal permissions and no production secrets.
- Never expose tokens to pull-request code from untrusted forks.
- Validate paths and reject traversal, absolute paths, unexpected symlinks, and writes outside the workspace.
- Apply only reviewed adapter operations.
- Keep generated artifacts separate from upstream source.
- Do not publish or deploy automatically in the initial release.
- Log commands and results without recording secret values.

## Recovery and audit

Every candidate sync must identify the original customized ref and the candidate ref. A failed or rejected candidate is discarded without changing the original. Successful integration records the old and new upstream SHAs, local customization revision, changed paths, conflicts and human decisions, verification results, and final commit SHA.

If detection is uncertain, licence evidence is missing, a path is unsafe, a merge conflict exists, or a build requires privileged credentials, stop and report the reason.
