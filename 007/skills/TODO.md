# TODO

## Infrastructure
- [x] Add skill scaffolding script (`make new SKILL=<name>`)
- [x] Add skill dependency resolution between skills
- [x] Add versioning/changelog tooling

## Skills to Add
- [x] math-primes — Prime number generation and sieve algorithms
- [x] text-summarize — Text summarization utilities
- [x] data-csv — CSV parsing and transformation
- [x] review-adversarial — Adversarial code review with state-tracked review loops
- [x] althingi — Roundtable discussion orchestrator (subagent + solo mode)

## Improvements
- [x] Add tests for math-fibonacci
- [x] Add `--format` flag to fibonacci-generator (json, csv, plain)
- [x] Add tests for roll-dice
- [x] Add multi-dice support to roll-dice (e.g., `2d6`, `3d8+2`)
- [x] Add tests for img-sixel
- [x] Add `--output` flag to img-sixel for saving SIXEL output to file
- [x] Add tests for test-playwright
- [x] Add `playwright.sh update` command to update browsers
- [x] Document skill authoring guidelines

## Parking Lot

### CI Pipeline (`.github/workflows/ci.yml`)
- Trigger on push/PR to main
- Set up Python + uv
- `make validate` — validate all SKILL.md files
- `make deps` — check dependency graph (no missing, no cycles)
- `uv run pytest tests/` — run the full test suite
- `make test` — smoke test all scripts accept `--help`
