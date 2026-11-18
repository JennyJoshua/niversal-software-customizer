# Licensing and Attribution

This guide is operational guidance, not legal advice. The automated report collects evidence only and must never be treated as legal approval.

## Run the evidence scanner

```bash
usc licences --path ./source-project --output rights-review.json
```

The report records root and nested licence, notice, authorship, copyright, and attribution files, including content hashes and SPDX identifiers where present. It extracts project licence declarations and dependency names/version constraints from supported npm, Composer, Python, Cargo, and Go manifests. It also flags likely asset, font, icon, image, dataset, logo, and trademark review areas.

The scanner does not resolve dependency licences, determine licence compatibility, inspect every binary asset's provenance, or make legal conclusions. Installed dependency directories are excluded from traversal; lockfiles and package registries are not resolved in this phase.

## Before adapting a project

1. Identify the exact upstream repository and pinned commit.
2. Find root and nested licence files. A nested licence may apply only to its own component and does not replace the root project's licence.
3. Inspect copyright, NOTICE, AUTHORS, and attribution files.
4. Review dependency manifests and lockfiles, then verify each dependency's exact version and licence independently.
5. Check whether assets, fonts, icons, datasets, documentation, and other materials have separate terms.
6. Check trademark restrictions independently of copyright licensing.
7. Record intended use: private modification, internal deployment, redistribution, or commercial distribution.
8. Obtain human review if evidence is missing, ambiguous, conflicting, or incomplete.

## Important distinctions

- A public GitHub repository is not automatically open source.
- A repository without a licence generally does not grant broad reuse, modification, or distribution permission.
- A main project licence may not cover every dependency, asset, font, logo, or dataset.
- Licence compatibility depends on the actual combination and distribution model.
- Trademark rights are separate from copyright licences.
- Some licences impose source disclosure, notice, attribution, or other distribution obligations.

## Non-negotiable rules

- Never delete or conceal copyright notices or required licence text.
- Never imply upstream authors endorse the customized product.
- Do not reuse upstream logos or trademarks as the new identity unless terms and permission allow it.
- Include required licence and attribution materials with output.
- Preserve source-offer or corresponding-source obligations when applicable.
- Stop if licence evidence is absent, unclear, or incompatible with intended use.

## Per-project review record

Record repository URL and commit; detected licence files; dependency and asset licence evidence; intended modification/distribution; obligations; unresolved questions; reviewer and date; and decision (approved, blocked, or needs legal advice).

The tool emits a pending human-review record and always sets `legal_approval=false` and `customization_gate=blocked`. It cannot approve a project. A human reviewer must confirm the exact licence terms, scope, third-party rights, intended use, and obligations before customization or distribution.
