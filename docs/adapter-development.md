# Adapter Development

Adapters translate common branding intent into safe changes for a specific project family.

## Requirements

- Detection uses explainable repository evidence.
- Unsupported or ambiguous projects return an explicit unsupported result.
- Planning is read-only and deterministic.
- Every operation identifies path, operation, reason, and expected result.
- Application enforces allowlists and rejects path traversal or symlink escapes.
- Tests use fixtures and verify intended and unintended file changes.
- Preserve upstream notices, licences, and attribution.
- Do not run project scripts during detection or planning.

## Lifecycle

1. Add a minimal fixture representing a real project layout.
2. Document supported branding surfaces.
3. Implement detection and inspection.
4. Implement dry-run planning.
5. Implement safe application to a disposable copy.
6. Add normal, missing, ambiguous, and malicious-input tests.
7. Document limitations and build commands.

An adapter is not complete merely because it can edit a file. It must prove the change suits the project's conventions and does not break unrelated behavior.
