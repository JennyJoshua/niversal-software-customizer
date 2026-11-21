# Isolated build execution model

## Purpose and boundary

USC build verification is a separate, explicit operation. Inspection, licence scanning, adapter detection, configuration validation, and dry-run planning must never execute project code. A build result applies only to the exact source tree, approved command, pinned image, and execution profile that produced it.

The first runner is deliberately Docker-only. If the Docker CLI or daemon is unavailable, USC blocks execution; it must not fall back to a host shell, subprocess execution, or another weaker environment.

## Required controls

The runner requires all of the following:

- Explicit approval of the command and image before execution.
- An image reference pinned by sha256 digest and already present locally (--pull=never); USC does not pull images during a build.
- Direct argv execution; shell interpreters and shell command strings are rejected.
- A disposable container with --network=none, read-only root filesystem, read-only source mount, and one dedicated writable output mount.
- Non-root UID/GID, all Linux capabilities dropped, no-new-privileges, a PID limit, memory and CPU limits, and a small non-executable temporary filesystem.
- A sanitized environment containing only fixed HOME, TMPDIR, and PATH values. Host environment variables, credentials, sockets, and additional mounts are not forwarded.
- A hard timeout and bounded captured logs.
- A unique container label and a post-run cleanup check. If cleanup cannot be confirmed, the result is blocked_cleanup_failed.

The output directory must be separate from and must not contain or enclose the source directory. This prevents the writable output mount from making source files writable.

## Invocation contract

The Python API is customizer.build_runner.run_isolated_build. It accepts a source directory, an existing output directory, a digest-pinned image, an argv list, and approved=True. The caller must obtain that approval through a separate human-reviewed workflow; the boolean is not a substitute for a user-facing approval gate.

Example (illustrative only; replace the placeholder with a verified, locally provisioned 64-character digest):

~~~python
from customizer.build_runner import run_isolated_build

report = run_isolated_build(
    "./candidate",
    "./build-output",
    image="python:3.12-slim@sha256:<verified-64-character-digest>",
    command=["python", "-m", "pytest", "-q"],
    approved=True,
    timeout_seconds=300,
)
~~~

Do not pass secrets in command arguments or source files. A mounted source tree is readable to the build process; the runner does not make arbitrary source contents confidential. Keep secrets out of fixture and candidate trees.

## Result states

- blocked_approval_required: no execution occurred because approval was absent.
- blocked_invalid_request: unsafe or invalid request; no execution occurred.
- blocked_isolation_unavailable: Docker was unavailable; no host fallback occurred.
- passed / failed: container command exited with status zero / non-zero.
- timed_out: execution exceeded its time limit and the container was stopped.
- output_limit_exceeded: captured output exceeded the configured bound and the container was stopped.
- blocked_cleanup_failed: USC could not confirm removal of all containers bearing the run's unique label.

## Current limitations

This is an initial local Docker runner, not yet a complete CI orchestration or provenance system. It does not yet stage a secret-filtered source snapshot, compute/bind a Git tree SHA, capture a complete toolchain inventory, hash artifacts, validate a provenance manifest, or provide a CLI command. Those are subsequent Phase 6 batches. Use synthetic fixtures only until those controls and failure tests are complete.

The runner is not a guarantee against container-runtime vulnerabilities or malicious build code. Use a patched Docker daemon and trusted, digest-pinned images. Never expose Docker socket or credentials inside the build container.
