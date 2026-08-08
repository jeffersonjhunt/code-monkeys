#!/usr/bin/env python3
"""Shared defaults and project-override parsing for the sdlc skill.

Imported by lifecycle.py and preflight.py so there is exactly one definition of the lifecycle and one
parser for the override block. Two copies would eventually disagree, and the disagreement would be
invisible.
"""
from __future__ import annotations

import os
from pathlib import Path

PHASES = [
    "intake",
    "plan",
    "isolate",
    "implement",
    "verify",
    "review",
    "land",
    "deploy",
    "observe",
    "release",
]

# Tier -> the phases it requires, in order.
#
# Two independent questions pick the tier, not one ladder of "how big":
#   does it change behaviour?   no  -> trivial
#   does it ship to a runtime?  no  -> undeployed
#                               yes -> standard, or campaign if many units / hard to reverse
#
# `undeployed` exists because without it, substantive work that ships nothing — test-only changes,
# dev tooling, a spec — had to claim `standard` and then walk through `deploy` and `observe` that do
# not apply, or claim `trivial` and skip `verify`, which it does need. Both are wrong, and an agent
# forced to pick a wrong answer picks the cheap one.
DEFAULT_TIERS = {
    "trivial": ["isolate", "implement", "land", "release"],
    "undeployed": [p for p in PHASES if p not in ("deploy", "observe")],
    "standard": list(PHASES),
    "campaign": list(PHASES),
}

# `campaign` additionally must establish what the change actually does before doing it. Skipping this
# is how a "just add a label" rebuild turns out to also move the software underneath it.
CAMPAIGN_REQUIRES_SURVEY = True

SENTINEL_BEGIN = "<!-- sdlc:begin -->"
SENTINEL_END = "<!-- sdlc:end -->"

KNOWN_KEYS = {
    "release.merge_by": {"host", "agent"},
    # Accepted alias. `land` stopped meaning "merge" when release became its own phase; renaming the
    # key outright would have silently un-configured every project still using it, so the old name
    # keeps working and resolve() prefers the new one.
    "land.merge_by": {"host", "agent"},
    "verify.require_negative": {"true", "false"},
}


def find_claude_md(start: Path | None = None) -> Path | None:
    """Search upward for a CLAUDE.md. Upward, so a worktree finds its repo's file."""
    cur = (start or Path.cwd()).resolve()
    for d in [cur, *cur.parents]:
        candidate = d / "CLAUDE.md"
        if candidate.is_file():
            return candidate
    return None


def find_repo_root(start: Path | None = None) -> Path | None:
    """Search upward for the working-tree root (the directory holding `.git`).

    `.exists()`, not `.is_dir()`: in a git WORKTREE `.git` is a FILE pointing at the real git dir,
    and a worktree is exactly where this matters most.
    """
    cur = (start or Path.cwd()).resolve()
    for d in [cur, *cur.parents]:
        if (d / ".git").exists():
            return d
    return None


def default_state_path(start: Path | None = None) -> Path:
    """Where `.sdlc-state.json` lives: the repo root, not the current directory.

    Resolving it against cwd meant a lifecycle started at the repo root vanished the moment you
    stepped into a subdirectory — `advance` then reported "no state, run init first" while the state
    sat one level up. One task has one state file, so it belongs at a fixed point in the repo.

    Outside a repo there is no fixed point, so cwd remains the fallback.
    """
    root = find_repo_root(start)
    return (root or (start or Path.cwd())) / ".sdlc-state.json"


def parse_overrides(path: Path | None) -> tuple[dict[str, str], list[str]]:
    """Return (overrides, problems) from the sentinel block in `path`.

    Problems are RETURNED, not swallowed. An override that is silently ignored because of a typo is
    the same class of bug as a check that examines nothing and reports success.
    """
    if path is None or not path.is_file():
        return {}, []
    text = path.read_text(encoding="utf-8", errors="replace")
    if SENTINEL_BEGIN not in text or SENTINEL_END not in text:
        return {}, []
    block = text.split(SENTINEL_BEGIN, 1)[1].split(SENTINEL_END, 1)[0]

    out: dict[str, str] = {}
    problems: list[str] = []
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            problems.append(f"not a key: value pair: {line!r}")
            continue
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if not key:
            problems.append(f"empty key in {line!r}")
            continue
        if key in KNOWN_KEYS and value not in KNOWN_KEYS[key]:
            problems.append(
                f"{key}={value!r} is not one of {sorted(KNOWN_KEYS[key])}"
            )
            continue
        if not (
            key in KNOWN_KEYS
            or key.startswith("tiers.")
            or key.startswith("phases.")
        ):
            problems.append(f"unknown key {key!r}")
            continue
        out[key] = value
    return out, problems


def resolve_tiers(overrides: dict[str, str]) -> dict[str, list[str]]:
    """Apply overrides to the default tier -> phases mapping."""
    tiers = {k: list(v) for k, v in DEFAULT_TIERS.items()}

    for key, value in overrides.items():
        if key.startswith("tiers.") and key.endswith(".phases"):
            tier = key[len("tiers.") : -len(".phases")]
            tiers[tier] = [p.strip() for p in value.split(",") if p.strip()]

    # phases.<name> applies to every tier, and is applied AFTER the per-tier lists so a project can
    # say "deploy is required here" once instead of restating every tier.
    for key, value in overrides.items():
        if not key.startswith("phases."):
            continue
        phase = key[len("phases.") :]
        for tier, plist in tiers.items():
            if value == "required" and phase not in plist:
                plist.append(phase)
            elif value == "skip" and phase in plist:
                plist.remove(phase)
    for tier, plist in tiers.items():
        tiers[tier] = [p for p in PHASES if p in plist]
    return tiers


def load(start: Path | None = None) -> dict:
    """Everything a caller needs: tiers, overrides, where they came from, and any problems."""
    claude = find_claude_md(start)
    overrides, problems = parse_overrides(claude)
    return {
        "claude_md": str(claude) if claude else None,
        "overrides": overrides,
        "override_problems": problems,
        "tiers": resolve_tiers(overrides),
        "merge_by": overrides.get(
            "release.merge_by", overrides.get("land.merge_by", "host")
        ),
        "require_negative": overrides.get("verify.require_negative", "true") == "true",
    }


if __name__ == "__main__":  # pragma: no cover - convenience only
    import argparse
    import json

    # Real argparse rather than printing regardless of argv: without it `--help` "passed" the
    # library's smoke test by ignoring the flag and dumping JSON, which is a check succeeding for
    # the wrong reason — the thing this skill is about.
    ap = argparse.ArgumentParser(
        description="Show the resolved sdlc config (defaults + any CLAUDE.md overrides)."
    )
    ap.add_argument("--path", default=os.getcwd(), help="where to search upward from")
    a = ap.parse_args()
    print(json.dumps(load(Path(a.path)), indent=2))
