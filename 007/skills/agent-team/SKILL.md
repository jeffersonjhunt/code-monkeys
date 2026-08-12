---
name: agent-team
description: Orchestrate a multi-agent development team (PM, Architect, Developer, Designer, Tester, Reviewer) through structured phases with human-in-the-loop checkpoints. Use when asked to run a project with a team, coordinate multiple agents, or build something end-to-end with role separation.
license: Apache-2.0
metadata:
  author: ooe
  version: "1.0"
dependencies:
  - sdlc
  - review-adversarial
---

# agent-team

Multi-agent project orchestrator. Routes a project idea through structured phases, spawning
specialized agents for each and pausing for the Product Owner's (human's) approval at every
transition. You are the orchestrator — you coordinate, you do not implement.

The `sdlc` skill governs *how* each agent does their work (branch, commit, verify, land). This skill
governs *who* does what and *in what order*.

## When to Use

- User says "build this with the team", "start a project", "use the agent team"
- User provides a project idea and wants structured multi-agent development
- User asks to "plan and build" something end-to-end with role separation

## Prerequisites

Install agent configs before first use:

```bash
python scripts/agents.py install
```

## Orchestration Protocol

```
1. Initialize:    python scripts/orchestrator.py init --task "build X" [--skip-design]
2. Next:          python scripts/orchestrator.py next
                  → returns: phase, lead agent, context to feed, prompt template
3. Spawn the subagent with the returned prompt
4. Record:        python scripts/orchestrator.py advance <phase> --output <artifact-file>
5. Present output to human, ask for decision
6. Decision:      python scripts/orchestrator.py decide <phase> --action approve [--feedback "..."]
7. Repeat from step 2 until next returns {"phase": null, "status": "complete"}
8. Summary:       python scripts/orchestrator.py summary
```

### Phase Flow

```
Phase 1: INTAKE         → team-pm produces project brief
  ⏸️ Human approves brief

Phase 2: PLANNING       → team-pm (+ team-architect input) produces project plan
  ⏸️ Human approves plan

Phase 3: ARCHITECTURE   → team-architect produces system design
  ⏸️ Human approves architecture

Phase 4: DESIGN         → team-designer produces UI/UX specs (skippable)
  ⏸️ Human approves design

Phase 5: IMPLEMENTATION → team-developer writes code (follows sdlc internally)
  ⏸️ Human reviews implementation

Phase 6: TESTING        → team-tester validates implementation
  ⏸️ Human reviews test results

Phase 7: REVIEW         → team-reviewer audits quality & security
  ⏸️ Human decides: ship or rework
  (loops back to IMPLEMENTATION if NEEDS_CHANGES, max 2 loops)

Phase 8: DELIVERY       → team-pm packages final documentation
  ⏸️ Human accepts delivery
```

### Human Decisions

At each checkpoint the Product Owner may:

| Action | Effect |
|--------|--------|
| `approve` | Advance to next phase |
| `revise` | Re-run current phase with feedback |
| `skip` | Skip this phase (only design is skippable by default) |
| `abort` | Stop the project, save state |

### Subagent Spawning

For each phase, spawn the lead agent via the subagent tool. Feed them:
1. The task context from `next` (includes relevant prior artifacts)
2. Any human feedback from a previous `revise` decision

```json
{
  "task": "<context from orchestrator.py next>",
  "stages": [
    {
      "name": "<phase>",
      "role": "<lead agent from next>",
      "prompt_template": "<prompt from next>"
    }
  ]
}
```

For phases with supporting agents (e.g., planning needs architect input), spawn them in parallel:

```json
{
  "task": "...",
  "stages": [
    {"name": "planning", "role": "team-pm", "prompt_template": "..."},
    {"name": "arch-input", "role": "team-architect", "prompt_template": "..."}
  ]
}
```

### SDLC Integration

The `team-developer` agent MUST follow the `sdlc` skill during implementation:
- `preflight.py` before starting work
- `lifecycle.py init --tier <appropriate>` to track the implementation sub-lifecycle
- Proper branch isolation, commits, verification

The `team-reviewer` agent should chain to `review-adversarial` for the code review phase.

### Context Threading

Each phase's approved output becomes input for subsequent phases:

| Phase | Feeds into |
|-------|-----------|
| Brief | Planning, Architecture, Design, Testing |
| Plan | Architecture, Implementation, Delivery |
| Architecture | Design, Implementation, Testing, Review |
| Design | Implementation |
| Test Results | Review, Delivery |
| Review Report | Delivery (or back to Implementation) |

The `next` command handles this automatically — it reads completed artifacts and builds the context.

### Review Loop

If the reviewer's output contains `NEEDS_CHANGES`:
1. Present findings to the human
2. If human approves rework: set phase back to implementation with review feedback
3. Maximum 2 review loops before forcing a human decision on whether to ship anyway

### State File

State lives in `.agent-team-state.json` at the repo root. Add it to `.gitignore`.

## Scripts

### `orchestrator.py` — State Machine

```bash
python scripts/orchestrator.py init --task "build a REST API" [--skip-design]
python scripts/orchestrator.py next
python scripts/orchestrator.py advance implementation --output project-output/05-code.md
python scripts/orchestrator.py decide implementation --action approve
python scripts/orchestrator.py decide review --action revise --feedback "fix the SQL injection"
python scripts/orchestrator.py status
python scripts/orchestrator.py summary
```

Exit codes: 0 = ok, 1 = refused/user error, 2 = missing state.

### `agents.py` — Agent Config Management

```bash
python scripts/agents.py install              # Install agent configs to ~/.kiro/agents/
python scripts/agents.py install --local      # Install to .kiro/agents/ (project-local)
python scripts/agents.py list                 # Show installed team agents
python scripts/agents.py uninstall            # Remove team agent configs
```

## Important Rules

1. **Never do the work yourself.** Always spawn the appropriate agent.
2. **Always pause for human approval** between phases. Never auto-advance.
3. **Thread context forward** — use `next` to get the right context automatically.
4. **Respect skip decisions** — if human skips Design, don't feed a missing design spec to the Developer.
5. **On revision** — include the human's feedback in the re-run prompt.
6. **On abort** — save current state; the project can resume later via `next`.
7. **Developer follows sdlc** — the implementation phase is not freeform; it uses the sdlc skill internally.
