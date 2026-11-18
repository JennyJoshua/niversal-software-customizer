# Security Model

## Threat assumptions

Upstream repositories may contain malicious scripts, compromised dependencies, unsafe build hooks, path traversal entries, symlinks, or instructions designed to expose credentials.

## Controls

- Static inspection must not execute upstream code.
- Clone/fetch only into disposable workspaces.
- Pin upstream revision and record its resolved SHA.
- Build with minimal permissions and no production secrets.
- Never expose tokens to pull-request code from untrusted forks.
- Validate paths and reject traversal, absolute paths, unexpected symlinks, and writes outside the workspace.
- Apply only reviewed adapter operations.
- Keep generated artifacts separate from upstream source.
- Do not publish or deploy automatically in the initial release.
- Log commands and results without recording secret values.

If detection is uncertain, licence evidence is missing, a path is unsafe, or a build requires privileged credentials, stop and report the reason.
