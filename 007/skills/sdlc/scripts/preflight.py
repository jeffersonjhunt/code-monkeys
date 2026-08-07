#!/usr/bin/env python3
"""Is this a safe place to do work at all?

Answers the questions nobody asks until after the damage: am I on main, is this tree someone else's,
is this a deployment artifact rather than a workspace.

Exit 0 = safe, 1 = not safe (each failure says what to do instead), 2 = cannot tell (not a git repo).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROTECTED_BRANCHES = {"main", "master", "trunk"}

# A deployment artifact is a clone that exists to RUN code, not to host its authoring. Editing there
# leaves a host running something no commit describes.
ARTIFACT_MARKERS = ("/home/gdeceiver/", "/srv/deploy/", "/opt/deploy/")


def git(*args: str, cwd: Path | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return 127, "git not found"
    return p.returncode, (p.stdout or p.stderr).strip()


def check(cwd: Path) -> dict:
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str, fix: str = "") -> None:
        checks.append({"check": name, "ok": ok, "detail": detail, "fix": fix})

    rc, top = git("rev-parse", "--show-toplevel", cwd=cwd)
    if rc != 0:
        return {
            "safe": False,
            "fatal": "not a git repository",
            "checks": [],
            "exit": 2,
        }
    add("git_repo", True, top)

    rc, branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)
    if rc != 0:
        branch = "?"
    if branch == "HEAD":
        add(
            "on_branch",
            False,
            "detached HEAD",
            "git switch -c <branch> — a detached HEAD means commits belong to nothing",
        )
    elif branch in PROTECTED_BRANCHES:
        add(
            "not_protected_branch",
            False,
            f"on {branch}",
            f"git switch -c <branch> — never author on {branch}; push a branch and let the host merge",
        )
    else:
        add("not_protected_branch", True, f"on {branch}")

    rc, dirty = git("status", "--porcelain", cwd=cwd)
    # Untracked worktree scaffolding is noise, not uncommitted work.
    real = [
        ln
        for ln in dirty.splitlines()
        if ln.strip() and ".claude/worktrees" not in ln
    ]
    add(
        "clean_tree",
        not real,
        f"{len(real)} uncommitted change(s)",
        "commit or stash before starting new work" if real else "",
    )

    resolved = str(cwd.resolve())
    artifact = [m for m in ARTIFACT_MARKERS if resolved.startswith(m)]
    add(
        "not_deployment_artifact",
        not artifact,
        f"under {artifact[0]}" if artifact else resolved,
        "edit on the dev machine, push, and let the host fetch the ref" if artifact else "",
    )

    failed = [c for c in checks if not c["ok"]]
    return {
        "safe": not failed,
        "branch": branch,
        "checks": checks,
        "failed": [c["check"] for c in failed],
        "exit": 1 if failed else 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--path", default=".", help="directory to check (default: cwd)")
    ap.add_argument("--format", choices=["json", "plain"], default="json")
    args = ap.parse_args()

    result = check(Path(args.path))

    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        if result.get("fatal"):
            print(f"UNSAFE: {result['fatal']}", file=sys.stderr)
        for c in result.get("checks", []):
            mark = "ok  " if c["ok"] else "FAIL"
            print(f"{mark} {c['check']}: {c['detail']}")
            if not c["ok"] and c["fix"]:
                print(f"     -> {c['fix']}")
        print("safe" if result["safe"] else "NOT SAFE TO WORK HERE")

    if not result["safe"] and args.format == "json":
        print("preflight: not safe to work here", file=sys.stderr)
    return int(result["exit"])


if __name__ == "__main__":
    sys.exit(main())
