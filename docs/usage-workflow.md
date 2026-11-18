# Usage Workflow

The initial static inspection command is available after installing the project.

## Install for development

```bash
python -m pip install -e ".[dev]"
```

## Inspect a local source directory

```bash
usc inspect --path ./path-to-source
```

## Inspect a public GitHub repository at a pinned revision

```bash
usc inspect --repo-url https://github.com/OWNER/REPOSITORY --revision v1.2.3
```

A branch name, tag, or full commit SHA may be supplied. The report records the resolved commit SHA. Remote inspection is limited to public HTTPS GitHub repositories.

## Save the report

```bash
usc inspect --path ./path-to-source --output inspection-report.json
```

## Safety and limitations

- Inspection inventories files and reads selected metadata only.
- It does not run package scripts, build commands, application code, or dependency installers.
- Common generated/dependency directories are excluded from the inventory.
- Symlinked directories and files are not followed.
- The first version detects technology signals and licence/notice filenames; it does not establish legal permission or dependency licence compatibility.
- A `supported_candidate` result means only that recognizable project metadata was found. It is not approval to customize or distribute the project.
