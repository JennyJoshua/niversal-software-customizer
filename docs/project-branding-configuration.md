# Project and Branding Configuration

USC accepts two separate, versioned JSON documents:

- `project.json` describes the upstream source identity, selected adapter, and licence-review state.
- `branding.json` describes the requested product identity, visual tokens, asset locations, and optional text overrides.

The JSON Schema files in this directory are the authoritative structural contracts:

- `project.schema.json`
- `branding.schema.json`

Examples are provided as `project.example.json` and `branding.example.json`. Both currently use schema version `1`.

## Safety boundaries

- Configuration is declarative input; reading or validating it must not execute project code.
- Asset paths are repository-relative POSIX paths. Absolute paths, traversal segments, globs, backslashes, and USC/Git metadata paths are not valid branding targets.
- A schema-valid path is not proof that the target exists or is safe at runtime. The validator must also resolve each path inside the selected repository, reject symlinks, and check protected-path policy.
- HTTPS URL shape validation is not a licence or security approval.
- An adapter may apply only explicitly supported fields and allowlisted files. Unsupported fields must be reported, not guessed or applied.
- Licence and attribution notices remain protected regardless of branding configuration.

The schemas define input shape. Runtime validation and adapter-specific planning remain separate, read-only operations and are implemented/tested in the engine.
