# Skill Authoring Guidelines

## Directory Structure

Every skill must follow this layout:

```
<skill-name>/
├── SKILL.md          # Required: metadata and usage docs
├── scripts/          # Required: executable scripts
├── assets/           # Optional: static assets, templates
└── references/       # Optional: reference material
```

Use `make new SKILL=<name>` to scaffold a new skill.

## SKILL.md Format

The file must start with YAML frontmatter:

```yaml
---
name: my-skill
description: One-line description of what the skill does and when to use it.
license: Apache-2.0
metadata:
  author: your-name
  version: "1.0"
dependencies:
  - other-skill
  - another-skill
---
```

The `dependencies` field is optional. List other skill names that must be installed
before this skill. Run `make deps` to validate the dependency graph.

Follow the frontmatter with a markdown body containing:
- A heading with the skill name
- Usage examples with code blocks
- Dependency list (if any)

## Script Conventions

- Use `#!/usr/bin/env python3` or `#!/usr/bin/env bash` shebangs
- Python scripts: standard library only — **unless the skill declares a runtime** (see below)
- Bash scripts: use `set -euo pipefail`
- Output JSON by default for machine-readable results
- Support `--help` for usage information
- Exit non-zero on errors with a message to stderr
- Validate inputs and provide clear error messages

## Naming

- Skill directories: lowercase with hyphens (e.g., `math-fibonacci`, `docs-issues`)
- Scripts: lowercase with hyphens or underscores
- Use a category prefix when appropriate: `math-`, `text-`, `data-`, `img-`, `docs-`

## Testing

- Place tests in `tests/test_<skill_name>.py` at the project root
- Use pytest with subprocess calls to test scripts as black boxes
- Use absolute paths via `Path(__file__).resolve().parent.parent`
- Test: default behavior, flag variations, error cases, and `--help`
- Run tests: `cd skills-ref && uv run pytest ../tests/ -v`

## Error Handling

- Print errors to stderr: `print("Error: ...", file=sys.stderr)` or `echo "Error: ..." >&2`
- Use exit code 1 for user errors, 2 for missing dependencies
- Provide actionable messages (what went wrong and how to fix it)

## Output Format

- Default to JSON for structured output
- Support `--format` flag when multiple formats make sense (json, csv, plain)
- Keep output minimal and parseable

## Dependencies

- Prefer no external dependencies (standard library only)
- If external tools are needed (e.g., `libsixel`), document install instructions for macOS, Debian, and Fedora
- Check for dependencies at runtime and fail with install instructions

### Skills whose scripts only run somewhere else

Some skills are wrappers around a harness that lives in a container or on a specific host — their
scripts genuinely cannot run where `make test` runs, and `spark-bench` is the worked example: it needs
`openai`, `datasets`, a LiveCodeBench clone and the `sweagent` binary, all resident in the
`spark-bench` primate.

Declare it, so the smoke test skips rather than fails:

```yaml
metadata:
  runtime: container:spark-bench
```

`make test` then prints `SKIP: needs container:spark-bench — not runnable on this host` and moves on.

This is not an exemption from testing, it is a **classification**. Before it existed, those five
scripts were permanent `FAIL:` lines — indistinguishable from a genuinely broken script, so a real
breakage would have been invisible among them. Declare the runtime only when the scripts truly cannot
execute here; do not use it to quiet a script that is merely broken.

## Versioning & Changelog

Skills use semver-style versions in their `metadata.version` field.

```bash
# Show all skill versions
make changelog

# Bump a skill version
make bump SKILL=docs-issues TYPE=minor

# Add a changelog entry
python scripts/changelog.py add --skill docs-issues --message "Added new feature"

# Show a skill's changelog
python scripts/changelog.py show --skill docs-issues
```

When making changes to a skill, bump the version and add a changelog entry describing what changed.
