#!/usr/bin/env python3
"""Orchestrator state machine for the agent-team skill.

Manages phase transitions, context threading, and HITL decisions for a multi-agent
development team. The orchestrating agent calls this to know what to do next; the
scripts hold state and refuse invalid transitions.

Exit 0 = ok, 1 = refused or user error, 2 = missing state.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ─── Constants ───────────────────────────────────────────────────────────────

PHASES = [
    "intake",
    "planning",
    "architecture",
    "design",
    "implementation",
    "testing",
    "review",
    "delivery",
]

PHASE_CONFIG = {
    "intake": {
        "name": "Project Intake",
        "lead": "team-pm",
        "supporting": [],
        "inputs": [],
        "outputs": ["brief"],
        "skippable": False,
    },
    "planning": {
        "name": "Project Planning",
        "lead": "team-pm",
        "supporting": ["team-architect"],
        "inputs": ["brief"],
        "outputs": ["plan"],
        "skippable": False,
    },
    "architecture": {
        "name": "Architecture & Technical Design",
        "lead": "team-architect",
        "supporting": [],
        "inputs": ["brief", "plan"],
        "outputs": ["architecture"],
        "skippable": False,
    },
    "design": {
        "name": "UI/UX Design",
        "lead": "team-designer",
        "supporting": [],
        "inputs": ["brief", "architecture"],
        "outputs": ["design"],
        "skippable": True,
    },
    "implementation": {
        "name": "Implementation",
        "lead": "team-developer",
        "supporting": [],
        "inputs": ["architecture", "design", "plan"],
        "outputs": ["code"],
        "skippable": False,
    },
    "testing": {
        "name": "Testing & QA",
        "lead": "team-tester",
        "supporting": [],
        "inputs": ["brief", "architecture", "code"],
        "outputs": ["test_results"],
        "skippable": False,
    },
    "review": {
        "name": "Code Review & Security",
        "lead": "team-reviewer",
        "supporting": [],
        "inputs": ["architecture", "code", "test_results"],
        "outputs": ["review_report"],
        "skippable": False,
    },
    "delivery": {
        "name": "Delivery & Handoff",
        "lead": "team-pm",
        "supporting": [],
        "inputs": ["plan", "test_results", "review_report"],
        "outputs": ["delivery"],
        "skippable": False,
    },
}

PROMPT_TEMPLATES = {
    "intake": (
        "The Product Owner has this project idea:\n\n{task}\n\n"
        "Produce a structured project brief covering: problem statement, goals, target users, "
        "constraints, success criteria, and open questions for the Product Owner."
    ),
    "planning": (
        "Based on the approved project brief below, create a detailed project plan with phases, "
        "milestones, task breakdown, dependencies, and risk register.\n\n"
        "## Project Brief\n\n{brief}"
    ),
    "planning:supporting:team-architect": (
        "Review this project brief and provide initial technical feasibility notes, technology "
        "suggestions, and potential architectural risks for the PM to incorporate.\n\n"
        "## Project Brief\n\n{brief}"
    ),
    "architecture": (
        "Design the system architecture based on the approved brief and plan. Include: component "
        "diagram (mermaid/ASCII), technology choices with justification, API contracts, data model, "
        "and non-functional requirements.\n\n"
        "## Project Brief\n\n{brief}\n\n## Project Plan\n\n{plan}"
    ),
    "design": (
        "Design the user interface and interaction flows. Include: user flows (mermaid/ASCII), "
        "wireframe descriptions, component specs with states (loading/error/empty), accessibility "
        "requirements (WCAG 2.1 AA minimum).\n\n"
        "## Project Brief\n\n{brief}\n\n## Architecture\n\n{architecture}"
    ),
    "implementation": (
        "Implement the project following the architecture and design specs. Use the sdlc skill: "
        "run preflight, init a lifecycle with appropriate tier, work on a branch, write tests. "
        "Report what you built and any decisions made.\n\n"
        "## Architecture\n\n{architecture}\n\n## Design\n\n{design}\n\n## Project Plan\n\n{plan}"
    ),
    "testing": (
        "Design and execute tests for the implementation. Cover: happy paths, edge cases, error "
        "handling, boundary values. Report: test plan, test results (pass/fail), bugs found, "
        "coverage gaps.\n\n"
        "## Project Brief\n\n{brief}\n\n## Architecture\n\n{architecture}"
    ),
    "review": (
        "Review the implementation using the review-adversarial skill. Evaluate: correctness, "
        "security, architecture compliance, code quality, maintainability. Categorize findings as "
        "Critical/Major/Minor/Suggestion. End with verdict: APPROVE or NEEDS_CHANGES.\n\n"
        "## Architecture\n\n{architecture}\n\n## Test Results\n\n{test_results}"
    ),
    "delivery": (
        "Package the project for delivery. Produce: README with setup instructions, summary of "
        "what was built, known limitations, suggested next steps.\n\n"
        "## Project Plan\n\n{plan}\n\n## Test Results\n\n{test_results}\n\n"
        "## Review Report\n\n{review_report}"
    ),
}

VALID_ACTIONS = ("approve", "revise", "skip", "abort")
MAX_REVIEW_LOOPS = 2


# ─── Helpers ─────────────────────────────────────────────────────────────────


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def find_state_path() -> Path:
    """Walk up to find repo root (contains .git), return state file there."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".git").exists():
            return parent / ".agent-team-state.json"
    return cwd / ".agent-team-state.json"


def load_state(path: Path) -> dict:
    if not path.is_file():
        print(
            f"orchestrator: no state at {path}. Run `orchestrator.py init` first.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return json.loads(path.read_text())


def save_state(path: Path, state: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    tmp.replace(path)


def get_current_phase(state: dict) -> str | None:
    """Return the next phase that hasn't been completed or skipped."""
    phases = state.get("phases", PHASES)
    for phase in phases:
        phase_state = state["phase_states"].get(phase, {})
        if phase_state.get("status") not in ("completed", "skipped"):
            return phase
    return None


def get_artifact(state: dict, artifact_type: str) -> str:
    """Get the content of a completed artifact, or empty string if not available."""
    return state.get("artifacts", {}).get(artifact_type, "")


def build_context(state: dict, phase: str) -> str:
    """Build the context string for a phase by gathering required input artifacts."""
    config = PHASE_CONFIG[phase]
    template_key = phase
    template = PROMPT_TEMPLATES.get(template_key, "")

    # Gather available artifacts for template substitution
    subs = {"task": state.get("task", "")}
    for input_type in config["inputs"]:
        content = get_artifact(state, input_type)
        if content:
            subs[input_type] = content
        else:
            subs[input_type] = "(not available — phase was skipped)"

    # Add any revision feedback
    phase_state = state["phase_states"].get(phase, {})
    feedback = phase_state.get("feedback")
    if feedback:
        subs["revision_feedback"] = feedback

    # Format the template
    try:
        prompt = template.format(**subs)
    except KeyError:
        prompt = template

    # Append revision feedback if present
    if feedback:
        prompt += f"\n\n## Revision Feedback from Product Owner\n\n{feedback}"

    return prompt


# ─── Commands ────────────────────────────────────────────────────────────────


def cmd_init(args: argparse.Namespace) -> int:
    if not args.task.strip():
        print("orchestrator: --task must not be empty", file=sys.stderr)
        return 1

    phases = list(PHASES)
    if args.skip_design:
        # Design is still in the list but pre-marked as skipped
        pass

    state = {
        "task": args.task,
        "phases": phases,
        "phase_states": {},
        "artifacts": {},
        "decisions": [],
        "review_loops": 0,
        "started": now(),
        "updated": now(),
    }

    # Pre-skip design if requested
    if args.skip_design:
        state["phase_states"]["design"] = {
            "status": "skipped",
            "decided_at": now(),
        }

    save_state(Path(args.state), state)
    result = {
        "status": "initialized",
        "task": args.task,
        "phases": phases,
        "skipped": ["design"] if args.skip_design else [],
        "next_phase": "intake",
        "next_agent": PHASE_CONFIG["intake"]["lead"],
    }
    print(json.dumps(result, indent=2))
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    state = load_state(Path(args.state))
    phase = get_current_phase(state)

    if phase is None:
        print(json.dumps({"phase": None, "status": "complete"}, indent=2))
        return 0

    config = PHASE_CONFIG[phase]
    context = build_context(state, phase)

    result = {
        "phase": phase,
        "name": config["name"],
        "lead_agent": config["lead"],
        "supporting_agents": config["supporting"],
        "prompt": context,
        "skippable": config["skippable"],
    }

    # Include supporting agent prompts if any
    if config["supporting"]:
        result["supporting_prompts"] = {}
        for agent in config["supporting"]:
            key = f"{phase}:supporting:{agent}"
            if key in PROMPT_TEMPLATES:
                subs = {"task": state.get("task", "")}
                for input_type in config["inputs"]:
                    subs[input_type] = get_artifact(state, input_type) or "(not available)"
                try:
                    result["supporting_prompts"][agent] = PROMPT_TEMPLATES[key].format(**subs)
                except KeyError:
                    result["supporting_prompts"][agent] = PROMPT_TEMPLATES[key]

    print(json.dumps(result, indent=2))
    return 0


def cmd_advance(args: argparse.Namespace) -> int:
    state = load_state(Path(args.state))
    phase = args.phase

    if phase not in PHASES:
        print(f"orchestrator: unknown phase {phase!r}", file=sys.stderr)
        return 1

    current = get_current_phase(state)
    if current != phase:
        print(
            f"orchestrator: cannot advance {phase!r} — current phase is {current!r}",
            file=sys.stderr,
        )
        return 1

    # Read the artifact output
    if args.output:
        output_path = Path(args.output)
        if output_path.is_file():
            content = output_path.read_text()
        else:
            content = args.output  # treat as inline content
    else:
        content = sys.stdin.read() if not sys.stdin.isatty() else ""

    if not content.strip():
        print("orchestrator: no output provided (use --output <file> or pipe stdin)", file=sys.stderr)
        return 1

    # Store the artifact
    config = PHASE_CONFIG[phase]
    for output_type in config["outputs"]:
        state["artifacts"][output_type] = content

    # Mark phase as awaiting decision
    state["phase_states"][phase] = state["phase_states"].get(phase, {})
    state["phase_states"][phase]["status"] = "awaiting_decision"
    state["phase_states"][phase]["completed_at"] = now()
    state["phase_states"][phase]["lead_agent"] = config["lead"]
    state["updated"] = now()

    save_state(Path(args.state), state)
    print(json.dumps({"status": "awaiting_decision", "phase": phase}, indent=2))
    return 0


def cmd_decide(args: argparse.Namespace) -> int:
    state = load_state(Path(args.state))
    phase = args.phase

    if phase not in PHASES:
        print(f"orchestrator: unknown phase {phase!r}", file=sys.stderr)
        return 1

    phase_state = state["phase_states"].get(phase, {})
    if phase_state.get("status") != "awaiting_decision":
        print(
            f"orchestrator: phase {phase!r} is not awaiting a decision (status: {phase_state.get('status', 'not started')})",
            file=sys.stderr,
        )
        return 1

    action = args.action
    if action not in VALID_ACTIONS:
        print(f"orchestrator: invalid action {action!r}; valid: {', '.join(VALID_ACTIONS)}", file=sys.stderr)
        return 1

    if action == "skip" and not PHASE_CONFIG[phase]["skippable"]:
        print(f"orchestrator: phase {phase!r} cannot be skipped", file=sys.stderr)
        return 1

    # Record decision
    decision = {
        "phase": phase,
        "action": action,
        "feedback": args.feedback or None,
        "decided_at": now(),
    }
    state["decisions"].append(decision)

    if action == "approve":
        state["phase_states"][phase]["status"] = "completed"
        state["phase_states"][phase]["decided_at"] = now()

    elif action == "revise":
        # Reset phase to allow re-running with feedback
        state["phase_states"][phase]["status"] = "revision_requested"
        state["phase_states"][phase]["feedback"] = args.feedback or ""
        state["phase_states"][phase]["decided_at"] = now()
        # Remove the artifact so the phase re-runs
        config = PHASE_CONFIG[phase]
        for output_type in config["outputs"]:
            state["artifacts"].pop(output_type, None)

        # Track review loops
        if phase == "review":
            state["review_loops"] = state.get("review_loops", 0) + 1
            if state["review_loops"] >= MAX_REVIEW_LOOPS:
                decision["note"] = f"max review loops ({MAX_REVIEW_LOOPS}) reached — human must decide"

    elif action == "skip":
        state["phase_states"][phase]["status"] = "skipped"
        state["phase_states"][phase]["decided_at"] = now()

    elif action == "abort":
        state["phase_states"][phase]["status"] = "aborted"
        state["phase_states"][phase]["decided_at"] = now()
        state["aborted_at"] = now()
        save_state(Path(args.state), state)
        print(json.dumps({"status": "aborted", "phase": phase}, indent=2))
        return 0

    state["updated"] = now()
    save_state(Path(args.state), state)

    # Return next state
    next_phase = get_current_phase(state)
    result = {
        "status": action,
        "phase": phase,
        "next_phase": next_phase,
        "next_agent": PHASE_CONFIG[next_phase]["lead"] if next_phase else None,
    }
    if action == "revise" and phase == "review" and state.get("review_loops", 0) >= MAX_REVIEW_LOOPS:
        result["warning"] = "max review loops reached"

    print(json.dumps(result, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    state = load_state(Path(args.state))
    current = get_current_phase(state)

    phases_summary = []
    for phase in state["phases"]:
        ps = state["phase_states"].get(phase, {})
        status = ps.get("status", "pending")
        phases_summary.append({"phase": phase, "status": status})

    result = {
        "task": state["task"],
        "current_phase": current,
        "started": state["started"],
        "updated": state["updated"],
        "review_loops": state.get("review_loops", 0),
        "phases": phases_summary,
        "artifacts": list(state.get("artifacts", {}).keys()),
        "decisions": len(state.get("decisions", [])),
    }

    if state.get("aborted_at"):
        result["aborted_at"] = state["aborted_at"]

    print(json.dumps(result, indent=2))
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    state = load_state(Path(args.state))

    completed = [p for p in state["phases"] if state["phase_states"].get(p, {}).get("status") == "completed"]
    skipped = [p for p in state["phases"] if state["phase_states"].get(p, {}).get("status") == "skipped"]
    revisions = [d for d in state.get("decisions", []) if d["action"] == "revise"]

    result = {
        "task": state["task"],
        "completed_phases": completed,
        "skipped_phases": skipped,
        "total_decisions": len(state.get("decisions", [])),
        "revisions": len(revisions),
        "review_loops": state.get("review_loops", 0),
        "artifacts_produced": list(state.get("artifacts", {}).keys()),
        "started": state["started"],
        "finished": state.get("updated"),
    }
    print(json.dumps(result, indent=2))
    return 0


# ─── CLI ─────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="orchestrator.py",
        description="Multi-agent team orchestrator state machine",
    )
    parser.add_argument(
        "--state",
        default=None,
        help="Path to state file (default: .agent-team-state.json at repo root)",
    )

    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="Initialize a new project")
    p_init.add_argument("--task", required=True, help="Project description")
    p_init.add_argument("--skip-design", action="store_true", help="Skip the design phase")

    # next
    sub.add_parser("next", help="Get the next phase, agent, and context")

    # advance
    p_advance = sub.add_parser("advance", help="Record phase output")
    p_advance.add_argument("phase", help="Phase that produced output")
    p_advance.add_argument("--output", help="Path to artifact file or inline content")

    # decide
    p_decide = sub.add_parser("decide", help="Record human decision on a phase")
    p_decide.add_argument("phase", help="Phase to decide on")
    p_decide.add_argument("--action", required=True, choices=VALID_ACTIONS, help="Decision")
    p_decide.add_argument("--feedback", help="Feedback for revise/reject")

    # status
    sub.add_parser("status", help="Show current project status")

    # summary
    sub.add_parser("summary", help="Show project summary")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # Resolve state path
    if args.state is None:
        args.state = str(find_state_path())

    commands = {
        "init": cmd_init,
        "next": cmd_next,
        "advance": cmd_advance,
        "decide": cmd_decide,
        "status": cmd_status,
        "summary": cmd_summary,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
