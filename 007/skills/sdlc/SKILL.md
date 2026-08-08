---
name: sdlc
description: The default software development lifecycle every agent follows — intake, plan, isolate, implement, verify, review, land, deploy, observe. Use at the start of any coding task, and whenever deciding whether work is ready to land or deploy.
license: Apache-2.0
metadata:
  author: ooe
  version: "1.2.0"
dependencies:
  - review-adversarial
---

# sdlc

The lifecycle every instance follows unless a project overrides it. Ten phases; the merge is the
LAST act, not an early one. You do the work; the scripts hold
state and refuse invalid transitions, so a skipped phase is a visible decision rather than a silent
omission.

Projects override it in their own `CLAUDE.md` — see [`references/overrides.md`](references/overrides.md).

## Start here

```bash
python scripts/preflight.py                          # is this a safe place to work at all?
python scripts/lifecycle.py init --tier standard --task "add X" --why "one service, reversible"
python scripts/lifecycle.py status
```

`--why` is required. A tier is a claim about the risk of the work, and an unjustified claim is the
thing this skill exists to prevent.

## Tiers

Pick with two questions, not one "how big is it" judgement:

```
does it change behaviour? ── no ──> trivial
         │ yes
does it ship to a runtime? ── no ──> undeployed
         │ yes
one unit, reversible? ── yes ──> standard
         │ no
                        campaign
```

| tier | when | phases |
|---|---|---|
| `trivial` | docs, comments, formatting — **no behaviour change** | isolate, implement, land, release |
| `undeployed` | real change that **ships nothing**: tests, dev tooling, specs, CI | all except deploy, observe |
| `standard` | a feature or bug fix in one place, reversible, deployed | all ten |
| `campaign` | multi-host, multi-artifact, or hard to reverse | all ten **+ survey**, per-unit verification, declared stop/resume point |

`undeployed` is not a discount tier — it keeps `verify` and `review`, which is the whole point.
Without it, work that ships nothing had to either claim `standard` and walk through `deploy` and
`observe` that do not apply, or claim `trivial` and skip the verification it genuinely needs. Every
tier still ends in `release`: everything gets merged eventually, the question is only what has to be
true first.

If unsure between two, take the one with more phases. Choosing `trivial` for something that changes
behaviour is the failure mode, not choosing `standard` for a typo.

## The phases

**1 Intake** — restate the ask in your own words. Declare the tier and why. Name the **unit of work**
(the smallest thing that can be built, verified and reverted on its own). State what "done" means.

**2 Plan** — every tier except `trivial`: write the plan, get it approved, *then* write code. If the
ask is ambiguous in a way that changes the work, ask before planning, not after building.

**3 Isolate** — a branch, in a worktree. **Never `main`.** Never a deployment artifact (a clone that
exists to run code, not host it). A shared checkout has one HEAD: if someone else switches it, your
commits land on their branch and nothing errors.

**4 Implement** — small commits. The message says *why*; the diff already says what.

**5 Verify** — the phase that fails silently, so it has its own rules below.

**6 Review** — read your own diff as an adversary before anyone else does. For anything non-trivial,
chain to the `review-adversarial` skill.

**7 Land** — push the **branch**, and stop there. This is *not* the merge. Report what is ready and
what you did not do. Pushing a branch commit onward to main after every commit is developing on main
with extra steps.

**8 Deploy** — deploy **the branch's sha**, not main. Deploy tooling takes any ref; the point of
pinned artifacts and a proven rollback is that a candidate can go on real hardware and come off again
cheaply. The artifact is pinned (a digest, a sha — never a mutable tag), there is a health gate, and
the rollback path has been *run*, not just written. A rollback that has never executed is not a
rollback path.

**9 Observe** — verify in situ, not just that the deploy command exited 0. Record state. Re-check the
specific failure the change was supposed to prevent.

**10 Release** — *now* merge, on the evidence from 8 and 9. **The host merges.** If observation went
badly the alternative is redeploying the previous digest and fixing the branch — no merge to unwind.

> Merging before deploying inverts this: it makes main a promise rather than a record, and throws
> away the cheap way out. While a candidate is under test the repo *will* show declared-vs-running
> drift on that host — that is the expected state, not a reason to merge early.

## Verify: the rules that keep being learned the hard way

Every one of these comes from a check that passed while being wrong.

- **Zero examined is a failure, not a pass.** `all([])` is `True`. If a check enumerated nothing, it
  must say so and fail — never report success on an empty set.
- **Prove the check can fail.** Run the negative case: break the thing deliberately and confirm the
  check catches it. A gate never seen to fail is an assumption.
- **A precondition must test what the work needs.** Probing for the wrong thing silently disables the
  check everywhere — e.g. testing for a binary that is only ever run containerized.
- **Cover both sides of an environment fork.** If one host, platform or path differs, testing the
  convenient one covers half the code and looks like full coverage.
- **Distinguish "failed" from "found nothing".** They are different answers; collapsing them into one
  empty string turns an error into a clean result.
- **A worktree is a different environment.** It omits every gitignored file, so tests gated on local
  config *silently skip* there — a green run in a worktree can be hiding failures that only appear in
  the main checkout. Check the skipped count, not just the passed count, and confirm it in both.
- **Prefer a fixture to ambient config.** A test that reads the maintainer's local file runs on one
  machine and skips everywhere else, which is how five stale assertions survived unnoticed in
  `spark-build`. Give the script a seam and feed it a fixture; then every test runs everywhere.
- **On any test failure: stop.** Write down what failed and the proposed fix, and check with the host
  before changing code or tests. Never chase green.

## Scripts

### `preflight.py` — is this a safe place to work?

```bash
python scripts/preflight.py                  # JSON verdict, exit 1 if unsafe
python scripts/preflight.py --format plain
```

Checks: on a branch and not `main`/`master`; working tree clean; inside a git repo; not inside a
directory that looks like a deployment artifact. Exit non-zero names what to do instead.

### `lifecycle.py` — state and transitions

```bash
python scripts/lifecycle.py init --tier campaign --task "stamp all config images" --why "24 artifacts, 5 hosts"
python scripts/lifecycle.py advance implement --evidence "3 commits on branch"
python scripts/lifecycle.py advance verify --evidence "negative test: gate fails on main, passes on branch"
python scripts/lifecycle.py advance land --evidence "pushed branch feat/x, not merged"
python scripts/lifecycle.py advance release --evidence "observed healthy on minerva; merged"
python scripts/lifecycle.py status
python scripts/lifecycle.py summary
```

`advance` refuses a phase whose prerequisites are unmet — `land` before `verify` has evidence, and
`release` before `deploy` and `observe` have theirs. `--evidence` is a free-text claim about what was actually done; it is recorded, not
validated — the point is that the claim exists and is attributable.

State lives in `.sdlc-state.json` **at the repo root**, so it is found from any subdirectory;
`status` prints its resolved path. Override with `--state`, which is taken exactly as given.
Add it to `.gitignore`.

## Overrides

A project changes any of this from its own `CLAUDE.md`. See
[`references/overrides.md`](references/overrides.md).
