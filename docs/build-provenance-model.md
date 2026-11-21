# USC Build Provenance Manifest

## Purpose

A build provenance manifest is a detached, versioned record connecting one build-evidence report and its output artifacts to the exact source revision, upstream synchronization baseline, customization configuration, and approved execution profile.

The manifest is evidence metadata, not a security certification, a correctness guarantee, or permission to publish/release artifacts.

## Storage and lifecycle

- Generate the manifest as a separate JSON artifact in the caller-selected evidence/output area.
- Do not automatically write it into the source repository, .usc, the upstream baseline, or the accepted-sync provenance record.
- Do not publish or release artifacts automatically.
- Preserve the original build-evidence report and artifact inventory; the manifest references their SHA-256 digests.
- Any later operation that records the manifest into a repository requires a separate explicit review and approval.

## Required identity bindings

A valid manifest must identify:

1. **Source:** canonical repository URL when available, full commit SHA, exact Git tree SHA, USC staged-source snapshot SHA-256, and confirmation that the source worktree was clean at capture time.
2. **Upstream:** canonical upstream repository URL, last accepted upstream baseline SHA, selected upstream target SHA, accepted merge commit SHA, and the digest/path of the accepted sync provenance record. If the project has no upstream integration, this section is explicitly null.
3. **Customization:** project identifier and SHA-256 digests for the customization registry and any project/branding configuration actually used. Unused configuration references are null.
4. **Build evidence:** relative evidence reference, SHA-256 digest of the exact evidence document, status, command fingerprint, immutable image reference, inspected local image ID, and source snapshot fingerprint.
5. **Artifacts:** deterministic inventory digest and the per-file relative paths, sizes, and SHA-256 digests.

The source Git tree identity and staged snapshot digest are separate values. They must not be described as interchangeable. A future verifier must prove that the staged snapshot was derived from the identified Git tree after the documented exclusion policy; merely placing both hashes in one document does not prove that relationship.

## Verification rules

- Reject abbreviated or malformed Git commit/tree SHAs and malformed SHA-256 digests.
- Reject non-canonical or credential-bearing repository URLs.
- Reject absolute, parent-traversing, backslash-containing, or empty artifact/evidence paths.
- Recompute the evidence-document digest and artifact inventory digest; compare them with the manifest.
- Require the build evidence status, command fingerprint, image reference, and source snapshot fingerprint to match the manifest.
- When upstream context is present, verify the referenced accepted-sync provenance record and baseline identity; reject stale or mismatched baseline/merge references.
- Treat missing evidence, mismatched digests, dirty source state, or unresolved source-to-snapshot binding as a blocked verification.
- Never infer that a passing build grants release approval.

## Current implementation

- The versioned schema is in engine/customizer/schemas/build-provenance.schema.json.
- The runner records Git commit/tree identity only when the index and raw tracked files match HEAD, and verifies each included staged file against its Git blob.
- create_build_provenance_manifest reads the exact evidence file from a separate evidence directory, validates its schema, reconstructs and re-hashes the source snapshot, re-inventories artifacts, checks accepted upstream baseline/provenance, and hashes customization/project/branding configuration inputs.
- The function returns a manifest object only. It does not write to the source repository or publish artifacts.

## Remaining limitations

- The manifest is not digitally signed and does not prove who produced the build evidence. SHA-256 values provide integrity comparisons, not producer authenticity.
- The source-secret exclusion rules and log redaction remain best-effort controls, not a complete secret scanner.
- Actual in-image toolchain inventory is implemented on the Phase 6 toolchain branch and awaits CI review; a user-facing CLI and reviewed command-profile approval workflow remain outstanding.
- Use synthetic fixtures only until the remaining Phase 6 safeguards and reviewed command-profile workflow are complete.