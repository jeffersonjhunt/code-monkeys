#!/usr/bin/env python3
"""Lifecycle state and transitions for the sdlc skill.

You do the work; this holds the state and refuses invalid transitions, so a skipped phase is a
visible decision rather than a silent omission.

Exit 0 = ok, 1 = refused or user error, 2 = missing state.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sdlc_config as cfg  # noqa: E402

DEFAULT_STATE = ".sdlc-state.json"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state(path: Path) -> dict:
    if not path.is_file():
        print(
            f"lifecycle: no state at {path}. Run `lifecycle.py init` first.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return json.loads(path.read_text())


def save_state(path: Path, state: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    tmp.replace(path)  # atomic; a half-written state file would be worse than none


def cmd_init(args: argparse.Namespace) -> int:
    conf = cfg.load()
    tiers = conf["tiers"]
    if args.tier not in tiers:
        print(
            f"lifecycle: unknown tier {args.tier!r}; known: {', '.join(sorted(tiers))}",
            file=sys.stderr,
        )
        return 1
    # A tier is a claim about risk. An unjustified claim is what this skill exists to prevent, so the
    # reason is required rather than encouraged.
    if not args.why.strip():
        print("lifecycle: --why must not be empty", file=sys.stderr)
        return 1

    required = list(tiers[args.tier])
    if args.tier == "campaign" and cfg.CAMPAIGN_REQUIRES_SURVEY:
        required = ["survey"] + required

    state = {
        "task": args.task,
        "tier": args.tier,
        "why": args.why,
        "required_phases": required,
        "completed": [],
        "evidence": {},
        "started": now(),
        "config": {
            "claude_md": conf["claude_md"],
            "overrides": conf["overrides"],
            "override_problems": conf["override_problems"],
            "merge_by": conf["merge_by"],
            "require_negative": conf["require_negative"],
        },
    }
    save_state(Path(args.state), state)
    print(json.dumps({"initialized": True, **state}, indent=2))
    for p in conf["override_problems"]:
        print(f"lifecycle: override problem: {p}", file=sys.stderr)
    return 0


def cmd_advance(args: argparse.Namespace) -> int:
    path = Path(args.state)
    state = load_state(path)
    phase = args.phase
    required = state["required_phases"]

    if phase not in required:
        print(
            f"lifecycle: {phase!r} is not required for tier {state['tier']!r} "
            f"(required: {', '.join(required)})",
            file=sys.stderr,
        )
        return 1
    if phase in state["completed"]:
        print(f"lifecycle: {phase!r} already completed", file=sys.stderr)
        return 1

    # Ordering: everything required BEFORE this phase must be done. This is what refuses `land`
    # before `verify` — not a special case, just the ordering rule applied.
    idx = required.index(phase)
    missing = [p for p in required[:idx] if p not in state["completed"]]
    if missing:
        print(
            f"lifecycle: refusing {phase!r} — not done yet: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1

    if not args.evidence.strip():
        print("lifecycle: --evidence must not be empty", file=sys.stderr)
        return 1

    # The verify phase is the one that fails silently, so its evidence must at least CLAIM a negative
    # test. This checks that the claim was made and attributed, not that it is true — but an absent
    # claim is caught, and a false one is attributable.
    if phase == "verify" and state["config"].get("require_negative", True):
        words = args.evidence.lower()
        if not any(w in words for w in ("negative", "fails", "failed", "refuse", "control")):
            print(
                "lifecycle: refusing verify — evidence does not mention a negative test.\n"
                "  Prove the check CAN fail (break it deliberately), then record that here.\n"
                "  Override with verify.require_negative: false in CLAUDE.md if truly N/A.",
                file=sys.stderr,
            )
            return 1

    state["completed"].append(phase)
    state["evidence"][phase] = {"text": args.evidence, "at": now()}
    save_state(path, state)
    remaining = [p for p in required if p not in state["completed"]]
    print(
        json.dumps(
            {"advanced": phase, "completed": state["completed"], "remaining": remaining},
            indent=2,
        )
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    state = load_state(Path(args.state))
    required = state["required_phases"]
    remaining = [p for p in required if p not in state["completed"]]
    out = {
        "task": state["task"],
        "tier": state["tier"],
        "why": state["why"],
        "completed": state["completed"],
        "remaining": remaining,
        "done": not remaining,
        "merge_by": state["config"].get("merge_by", "host"),
        "overrides_from": state["config"].get("claude_md"),
        "overrides": state["config"].get("overrides", {}),
        "override_problems": state["config"].get("override_problems", []),
    }
    print(json.dumps(out, indent=2))
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    state = load_state(Path(args.state))
    required = state["required_phases"]
    remaining = [p for p in required if p not in state["completed"]]
    print(f"task:  {state['task']}")
    print(f"tier:  {state['tier']}  ({state['why']})")
    for p in required:
        done = p in state["completed"]
        mark = "x" if done else " "
        ev = state["evidence"].get(p, {}).get("text", "")
        print(f"  [{mark}] {p}{': ' + ev if ev else ''}")
    if remaining:
        print(f"INCOMPLETE — remaining: {', '.join(remaining)}")
        if state["config"].get("merge_by", "host") == "host":
            print("Do not merge. Push the branch and report.")
        return 1
    print("all required phases complete")
    if state["config"].get("merge_by", "host") == "host":
        print("Push the branch and report — the host merges.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state", default=DEFAULT_STATE, help=f"state file (default: {DEFAULT_STATE})")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="start a lifecycle")
    p.add_argument("--tier", required=True, help="trivial | standard | campaign")
    p.add_argument("--task", required=True, help="what you are doing")
    p.add_argument("--why", required=True, help="why that tier is the right one")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("advance", help="record a completed phase")
    p.add_argument("phase")
    p.add_argument("--evidence", required=True, help="what you actually did")
    p.set_defaults(func=cmd_advance)

    p = sub.add_parser("status", help="machine-readable state")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("summary", help="human-readable checklist; non-zero if incomplete")
    p.set_defaults(func=cmd_summary)

    args = ap.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
