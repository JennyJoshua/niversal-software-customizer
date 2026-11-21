# Adapter Development

Adapters translate common branding intent into safe changes for a specific project family.

## Requirements

- Detection uses explainable repository evidence.
- Unsupported or ambiguous projects return an explicit unsupported result.
- Planning is read-only and deterministic.
- Every operation identifies path, operation, reason, and expected result.
- Application enforces exact allowlists and rejects path traversal or symlink escapes.
- Existing user-owned target assets are never overwritten.
- Tests use fixtures and verify intended and unintended file changes.
- Preserve upstream notices, licences, and attribution.
- Do not run project scripts during detection, planning, or application.

## First adapter: Next.js App Router

The initial `web-nextjs` adapter is intentionally narrow. It supports only one of `app/` or `src/app/`, with `layout.tsx`, `globals.css`, and `page.tsx`, plus an existing `public/` directory. Each supported source file must contain exactly one pair of the documented USC markers:

- `/* USC:branding:metadata:start */` / `/* USC:branding:metadata:end */`
- `/* USC:branding:theme:start */` / `/* USC:branding:theme:end */`
- `{/* USC:branding:logo:start */}` / `{/* USC:branding:logo:end */}`

The adapter updates only the contents between markers. It supports product name/tagline metadata, both theme colours, an SVG logo, and an ICO favicon. Asset outputs use the USC-owned paths `public/usc-brand-logo.svg` and `public/usc-brand-favicon.ico`; an existing different file at either path blocks the operation.

The logo SVG is parsed and rejected if it contains script/foreign-object elements, event-handler attributes, or external references. The favicon must have an ICO header. Paths are rechecked for traversal and symlinks. The adapter does not modify licence/notice files, `.git`, `.usc`, or paths outside its fixed allowlist.

Run the read-only plan:

```bash
usc customize-plan --path ./project --project-config ./project.json --branding-config ./branding.json
```

Apply only after a human has completed the rights review, set `licence_review.status` to `approved` with a review record, and deliberately approves the local change:

```bash
usc customize-apply --path ./project --project-config ./project.json --branding-config ./branding.json --plan-report ./reviewed-plan.json --approve
```

The review record is a user-supplied gate, not an automated legal opinion. The command does not run Next.js scripts, install dependencies, build the app, or publish anything. Application writes are limited to the five allowlisted paths above; unrelated files and upstream notices are preserved by tests.

## Lifecycle for future adapters

1. Add a minimal fixture representing a real project layout.
2. Document supported branding surfaces.
3. Implement detection and inspection.
4. Implement dry-run planning.
5. Implement safe application to a disposable copy.
6. Add normal, missing, ambiguous, and malicious-input tests.
7. Document limitations and build commands.

An adapter is not complete merely because it can edit a file. It must prove the change suits the project's conventions and does not break unrelated behavior.
