# Custom Feature Protection Policy

## Purpose

This policy defines how Universal Software Customizer (USC) must protect work added to a customized product while importing eligible upstream updates. The objective is to receive upstream improvements without silently replacing, deleting, or weakening the product's independent identity and functionality.

This policy is a technical preservation rule, not a guarantee that every customization will remain compatible with every upstream release. Git can detect many textual conflicts; it cannot prove that a clean merge preserves behaviour.

## Protected areas

Every project adapter and synchronization workflow must identify and protect these areas where they exist:

1. **Product identity and branding**
   - Product name, logo, favicon, icons, colour palette, typography, themes, layout, and brand assets.
   - Product-specific descriptions, contact details, domain references, and branded documents.
2. **Custom functionality**
   - Features, modules, components, pages, workflows, business rules, calculations, and user journeys added for the customized product.
   - Custom API endpoints, integrations, notifications, and automation.
3. **Product configuration**
   - Product-specific settings, environment templates, feature flags, role/permission mappings, and deployment configuration.
   - Payment, pricing, subscription, and access rules where the product uses them.
4. **Data and integration contracts**
   - Custom database schemas, migrations, data mappings, API contracts, and integration configuration.
   - Existing customer/user data must never be treated as disposable source files or overwritten by an upstream source sync.
5. **Project-owned engineering assets**
   - Custom tests, fixtures, documentation, operational instructions, and build/deployment workflows.
   - Local patches and custom-only files, including files not yet covered by an adapter.
6. **Synchronization integrity**
   - The recorded upstream baseline, .usc/upstream-baseline.json, provenance records under .usc/provenance/, and the history needed to explain accepted updates.
   - Branding adapters must not rewrite or delete synchronization metadata.

## Upstream material that must also be preserved

Customization must not remove or overwrite upstream copyright notices, licence texts, attribution, third-party notices, trademark statements, or other obligations. A changed or removed rights file triggers renewed human review. This protection is independent of whether a file is upstream-owned or locally customized.

## Required synchronization behaviour

| Change detected | Required behaviour |
|---|---|
| New upstream file with no local counterpart | May be included in the isolated candidate |
| Upstream-only edit to an uncustomized file | May be included after candidate review and verification |
| Local-only custom file or change | Preserve it |
| Non-overlapping edits in the same file | A three-way merge may combine them; behavioural tests are still required |
| Overlapping edits | Block and require human resolution |
| Upstream deletion of a locally modified/custom file | Block; never silently delete it |
| Ambiguous rename, rename/delete, or uncertain path mapping | Block for human review |
| Change to branding, configuration, custom feature, data contract, or adapter-owned path | Require targeted regression checks before acceptance |
| Change to licence, notice, attribution, or trademark evidence | Require renewed human rights review |
| Change to USC baseline/provenance metadata outside the acceptance workflow | Reject |

No blanket ours/theirs merge strategy, automatic conflict resolution, or silent overwrite is permitted.

## Adapter requirements

Each adapter must declare:
- Its supported project family and version assumptions.
- Explicit allowlisted paths and transformation types.
- Paths and files it must never modify, including rights and USC synchronization metadata.
- A dry-run plan showing every proposed change and its reason.
- Preservation tests proving unrelated files remain byte-for-byte unchanged.
- Regression tests for the custom behaviour it touches.
- A clear blocked/unsupported result when a path, structure, or version is ambiguous.

Adapters must not perform unrestricted repository-wide search-and-replace. A path is not safe to modify merely because its filename looks like a branding file.

## Verification and acceptance

A clean Git merge is only a candidate, not proof of feature preservation. Before accepting an upstream update:
1. Review the upstream commit range and complete candidate diff.
2. Check every protected area changed by the update.
3. Run project and adapter tests in a disposable, unprivileged environment.
4. Run targeted regression tests for affected custom features, branding, configuration, data contracts, and integrations.
5. Re-review rights evidence if relevant files or dependencies changed.
6. Accept only the exact verified candidate tree, with provenance and baseline advancement recorded.

If the required test evidence is missing, stale, failed, or not bound to the exact candidate, acceptance must be blocked. Human approval does not override a detected conflict or failed verification.

## Limits and honest status reporting

USC protects changes through isolated candidates, three-way Git integration, explicit gates, provenance, and tests. It cannot promise that all custom features are semantically unaffected by upstream changes. Where automated tests do not cover a custom behaviour, the result must be described as unverified rather than protected by assumption.

The policy is considered implemented for an adapter only when its allowlist, preservation tests, regression tests, and failure behaviour are present and passing. The existence of this policy document alone does not mean every listed area is already automatically detected or protected.


## Machine-readable customization registry — planned capability

The policy above defines what must be protected. It does not yet provide automatic feature-level detection. The next protection capability must introduce a versioned, project-owned registry (proposed location: `.usc/customizations.json`) that maps each meaningful customization to its implementation surfaces and verification evidence.

A registry entry should include:
- A stable customization ID and human-readable purpose.
- A category: branding, feature/workflow, business rule, configuration, data/API contract, integration, or engineering asset.
- Explicit file/path references, with exact paths preferred over broad globs.
- A protection mode: preserve, require targeted regression tests, or block for human review.
- Test identifiers and evidence references that demonstrate the behaviour.
- An overlap policy and a human-readable reason for any exception.

Registry rules:
- One feature may span multiple files, and one file may contain both upstream and custom behaviour. File ownership alone is therefore insufficient.
- Do not use line numbers as durable protected-region identifiers. Where a mixed file needs finer-grained protection, support only stable, explicitly declared structural selectors or markers in formats the adapter can parse safely.
- Unknown paths, stale selectors, unsupported formats, missing tests, and ambiguous ownership must be reported as unverified or blocked; never infer that a feature is safe because Git merged cleanly.
- A registry entry is a protection declaration, not proof that behaviour is preserved. Only passing, relevant regression tests against the exact candidate can provide that evidence.
- Registry edits are themselves protected project changes. Record their diff in provenance and require explicit review before changing or removing existing protection.
- Never store credentials, secrets, customer records, or live production data in the registry.

The first registry release should be declarative and read-only: it may classify candidate changes and require tests, but must not rewrite source code or resolve conflicts. Registry enforcement must be implemented and tested before any adapter may claim feature-level protection.
