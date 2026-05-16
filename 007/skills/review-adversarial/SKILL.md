---
name: review-adversarial
description: Adversarial code review with structured findings and a review loop. Use when asked to critically review code, diffs, or design docs with an adversarial mindset.
license: Apache-2.0
metadata:
  author: ooe
  version: "1.0"
---

# review-adversarial

Adversarial review skill with state-tracked review loops. You (the agent) perform
the review; the scripts manage findings state and loop convergence.

## When to Use

- User asks for a critical/adversarial review of code, a diff, or a design doc
- User wants iterative review passes until issues are resolved
- User asks you to "poke holes" or "find what's wrong"

## Review Loop Protocol

```
1. Initialize:  python scripts/loop.py init [--max-rounds N] [--state PATH]
2. You review the target artifact using an adversarial perspective
3. Record:      python scripts/review.py --state .review-state.json < findings.json
4. Present findings to the user
5. User fixes code or disputes findings
6. Respond:     python scripts/respond.py --state .review-state.json --resolve <id>=<disposition> ...
7. Check:       python scripts/loop.py next --state .review-state.json
   → "continue" — unresolved findings remain or you found new issues; go to step 2
   → "converged" — all findings resolved; done
   → "max_rounds" — hit the limit; produce summary
8. Summary:     python scripts/loop.py summary --state .review-state.json
```

## Scripts

### loop.py — Orchestration & State

```bash
# Initialize a new review session
python scripts/loop.py init --max-rounds 3 --state .review-state.json

# Advance to next round (returns: continue, converged, or max_rounds)
python scripts/loop.py next --state .review-state.json

# Show current status
python scripts/loop.py status --state .review-state.json

# Produce final summary
python scripts/loop.py summary --state .review-state.json
```

### review.py — Record Findings

```bash
# Pipe findings JSON into the state file
echo '[{"id":"F1","severity":"major","category":"security","location":"auth.py:42","description":"SQL injection via string interpolation","suggestion":"Use parameterized queries"}]' | python scripts/review.py --state .review-state.json

# Or pass a file
python scripts/review.py --state .review-state.json --file findings.json
```

Each finding is a JSON object with fields:
- `id` — unique within the round (e.g., "F1", "F2")
- `severity` — critical, major, minor, nit
- `category` — security, correctness, performance, clarity, maintainability, edge-case
- `location` — file:line or section reference
- `description` — what's wrong
- `suggestion` — how to fix it

### respond.py — Record Resolutions

```bash
# Mark findings as resolved
python scripts/respond.py --state .review-state.json --resolve F1=fixed F2=disputed F3=accepted

# Disputed findings require rationale (prompted interactively or via --rationale)
python scripts/respond.py --state .review-state.json --resolve F2=disputed --rationale "F2:Rate limiting is handled at the LB layer"
```

Dispositions: `fixed`, `disputed`, `accepted` (accept-risk)

## Adversarial Perspectives

Cycle through these when reviewing (use the prompt template in `assets/templates/review-prompt.md`):

| Perspective | Focus |
|---|---|
| Attacker | Injection, auth bypass, data exfiltration, privilege escalation |
| Skeptical User | Error handling, edge cases, misleading behavior, data loss |
| Future Maintainer | Readability, coupling, hidden assumptions, missing docs |
| Ops Engineer | Failure modes, resource leaks, observability, deployment risks |
| Pedantic Reviewer | Naming, consistency, dead code, style violations |

## Agent Instructions

When performing an adversarial review:

1. **Initialize** the loop state with `loop.py init`
2. **Read** the target artifact thoroughly
3. **Adopt** one or more adversarial perspectives from the table above
4. **Generate** findings as structured JSON (use the schema above)
5. **Record** findings with `review.py`
6. **Present** findings to the user in a readable format (table or list)
7. **Wait** for the user to respond (fix, dispute, or accept)
8. **Record** responses with `respond.py`
9. **Advance** with `loop.py next` — if "continue", re-review focusing on:
   - Disputed findings (re-evaluate with the user's rationale)
   - Fixed code (verify the fix, check for regressions)
   - New issues introduced by fixes
10. **Summarize** when converged or at max rounds

## Dependencies

Python 3.6+ (standard library only)
