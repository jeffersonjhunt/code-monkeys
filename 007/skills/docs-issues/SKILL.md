---
name: docs-issues
description: Manage markdown-based issues (bugs, features, debt, questions) in docs/reviews/ and export to GitHub, GitLab, or a todo.md index. Use when asked to track, list, create, or push issues from a docs/reviews tree.
license: Apache-2.0
metadata:
  author: ooe
  version: "1.0"
---

# docs-issues

Manage issues as markdown files committed to the repo. Each issue is a single
`.md` file with YAML frontmatter, organized under `docs/reviews/{kind}/`.
Export to GitHub, GitLab, a managed `docs/todo.md`, or stdout.

## When to Use

- User wants to track bugs/features/debt as files in the repo
- User wants to push markdown issues to GitHub or GitLab
- User wants a generated `docs/todo.md` index of open work
- User wants to author RFC-style issues alongside the code

## Directory Layout

```
docs/
├── todo.md                       # auto-managed (between sentinel markers)
└── reviews/
    ├── bugs/
    │   └── 2026-05-19-sql-injection-auth.md
    ├── features/
    ├── debts/
    └── questions/
```

## Issue File Schema

```yaml
---
id: bug-001                  # auto-allocated, format: {kind}-{NNN}
kind: bug                    # bug | feature | debt | question
title: SQL injection in auth.py
severity: major              # critical | major | minor | nit
category: security
location: auth.py:42
status: open                 # open | closed | wontfix
created: 2026-05-19
source: review-adversarial:F1   # optional provenance
labels: [security, auth]
target:
  github: null               # set after export to that platform
  gitlab: null
---

## Description
...

## Suggested Fix
...
```

## Commands

### list / show

```bash
# List all open issues
python scripts/issues.py list

# Filter by kind and status
python scripts/issues.py list --kind bug --status open
python scripts/issues.py list --format json

# Show one issue
python scripts/issues.py show bug-001
```

### new

```bash
# Create a new issue (interactive author)
python scripts/issues.py new \
  --kind bug \
  --title "SQL injection in auth.py" \
  --severity major \
  --category security \
  --location "auth.py:42" \
  --labels "security,auth" \
  --description "Optional one-paragraph description"
```

ID is auto-allocated as `{kind}-{NNN}` (next sequential per kind). Filename is
`{YYYY-MM-DD}-{slug}.md` under `docs/reviews/{kind}s/`.

### status

```bash
python scripts/issues.py status bug-001 --set closed
python scripts/issues.py status feature-003 --set wontfix
```

### export

```bash
# Generate/refresh docs/todo.md (managed section between markers)
python scripts/issues.py export --target todo
python scripts/issues.py export --target todo --output path/to/TODO.md

# Print all open issues to stdout (for manual paste into a tracker)
python scripts/issues.py export --target stdout --status open

# Push to GitHub via gh CLI (requires `gh auth login`)
python scripts/issues.py export --target github
python scripts/issues.py export --target github --label-prefix triage/
python scripts/issues.py export --target github --force   # re-push already-exported

# Push to GitLab via glab CLI (requires `glab auth login`)
python scripts/issues.py export --target gitlab
```

## Idempotency

- `todo` target: rewrites only the section between `<!-- BEGIN: docs-issues -->`
  and `<!-- END: docs-issues -->` markers; user content elsewhere is preserved.
- `github`/`gitlab` targets: write the returned issue URL/number into
  `target.github` / `target.gitlab` in the markdown file. Subsequent exports
  skip already-pushed issues unless `--force` is set.

## Auto-detect Root

If `--root` is not given, the scripts walk up from the current directory looking
for a `docs/reviews/` directory and use it. Falls back to `./docs/reviews/`.

## Agent Instructions

When the user asks to track or export issues:

1. **Author** — Use `issues.py new` with the kind/title/severity/category. Don't
   write markdown files by hand unless extending an existing one with body content.
2. **Update body** — After `new`, you may edit the markdown file to flesh out
   the body sections. Don't touch the frontmatter directly except via `status`.
3. **List** — Use `issues.py list` to show the user what's tracked. Default to
   the table format unless they want JSON.
4. **Export** — Pick the target the user asked for; default to `todo` if they
   just want a summary in the repo.
5. **After tracker push** — Tell the user the issue URLs/numbers from the
   exporter output; they're also persisted in the markdown frontmatter.

## Dependencies

Python 3.6+ (standard library only). For tracker exports:
- `gh` CLI for GitHub (`brew install gh` or equivalent)
- `glab` CLI for GitLab (`brew install glab` or equivalent)
