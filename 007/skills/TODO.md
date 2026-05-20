# TODO

## Infrastructure
- [x] Add skill scaffolding script (`make new SKILL=<name>`)
- [x] Add skill dependency resolution between skills
- [x] Add versioning/changelog tooling

## Skills to Add
- [x] review-adversarial — Adversarial code review with state-tracked review loops
- [x] althingi — Roundtable discussion orchestrator (subagent + solo mode)
- [x] docs-issues — Markdown-based issue tracking with export to GitHub/GitLab/todo.md (paired with review-adversarial promote.py)

## Improvements
- [x] Add tests for math-fibonacci
- [x] Add `--format` flag to fibonacci-generator (json, csv, plain)
- [x] Add tests for img-sixel
- [x] Add `--output` flag to img-sixel for saving SIXEL output to file
- [x] Document skill authoring guidelines

## Removed (redundant with agent abilities)

These skills were pruned because their functionality is already provided
natively by the host agent (Claude / Kiro). Kept here as a record:
- math-primes (prime generation/factorization — trivial to compute natively)
- roll-dice (random — trivial to compute natively)
- text-summarize (extractive summarizer — agent summarizes better)
- data-csv (CSV operations — agent reads/transforms directly)
- test-playwright (thin wrapper over `npx playwright`)

`math-fibonacci` is intentionally kept as a reference template for new
skill authoring, even though Fibonacci itself is also trivial to compute.

## Parking Lot

### CI Pipeline (`.github/workflows/ci.yml`)
- Trigger on push/PR to main
- Set up Python + uv
- `make validate` — validate all SKILL.md files
- `make deps` — check dependency graph (no missing, no cycles)
- `uv run pytest tests/` — run the full test suite
- `make test` — smoke test all scripts accept `--help`
