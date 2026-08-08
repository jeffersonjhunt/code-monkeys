# Project-level overrides

The lifecycle ships with defaults. A project changes them from **its own `CLAUDE.md`** — the file
agents already read first — inside a sentinel block, so the same text is both the human-readable
policy and the machine-readable configuration. One location, so the rule and its enforcement cannot
drift apart.

```markdown
## SDLC

<!-- sdlc:begin -->
tiers.trivial.phases: isolate, implement, land
tiers.standard.phases: intake, plan, isolate, implement, verify, review, land, deploy, observe
phases.deploy: required
release.merge_by: host
<!-- sdlc:end -->
```

The block is found by the markers, not by heading, so it can live anywhere in the file. Lines are
`key: value`; `#` comments and blank lines are ignored. Unknown keys are reported by
`lifecycle.py status` rather than silently dropped — a typo in a policy file that quietly does nothing
is the same class of bug as a check that examines nothing.

## Keys

| key | values | meaning |
|---|---|---|
| `tiers.<tier>.phases` | comma-separated phase names | exactly which phases that tier requires |
| `phases.<phase>` | `required` / `optional` / `skip` | force a phase on or off for every tier |
| `release.merge_by` | `host` / `agent` | who merges, in the final `release` phase. Defaults to `host`. `land.merge_by` is still accepted as an alias — `land` stopped meaning "merge" when release became its own phase, and renaming outright would have silently un-configured projects using the old name |
| `verify.require_negative` | `true` / `false` | whether `verify` evidence must mention a negative test |

## Resolution order

1. Skill defaults.
2. The `<!-- sdlc:begin -->` block in the project's `CLAUDE.md` (searched upward from the working
   directory, so a worktree finds the repo's file).
3. Explicit flags on the command line.

Later wins. `lifecycle.py status` prints which overrides were found and from which file, so an
override that is not being applied is visible rather than mysterious.

## Deliberately not overridable

`release.merge_by: agent` is honoured, but **never `main` as a working branch**, **never a deployment
artifact as a workspace**, and **never merging before the candidate has been deployed and observed**
where those phases apply. Those are not policy knobs; a project that needs to violate them has a
different problem to solve.
