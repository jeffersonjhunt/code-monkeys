#!/usr/bin/env python3
"""Agent config management for the agent-team skill.

Installs, lists, and uninstalls Kiro agent configurations for the team roles.

Exit 0 = ok, 1 = error.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = SKILL_DIR / "assets"
PROMPTS_DIR = SKILL_DIR / "references" / "prompts"

KIRO_GLOBAL = Path.home() / ".kiro" / "agents"
TEAM_AGENTS = [
    "team-lead",
    "team-pm",
    "team-architect",
    "team-developer",
    "team-designer",
    "team-tester",
    "team-reviewer",
]


def resolve_prompt_path(agent_name: str, local: bool, local_dir: Path | None) -> str:
    """Return the prompt path to embed in the agent config.

    If installing locally, use a relative path from the project's .kiro/agents/.
    If installing globally, use the absolute path to the skill's references/prompts/.
    """
    role = agent_name.replace("team-", "")
    if role == "lead":
        return ""  # team-lead uses an inline prompt
    prompt_file = PROMPTS_DIR / f"{role}.md"
    if not prompt_file.exists():
        return ""
    return f"file://{prompt_file}"


def install_agents(local: bool = False) -> int:
    """Install agent configs from assets/ to the target directory."""
    if local:
        target = Path.cwd() / ".kiro" / "agents"
    else:
        target = KIRO_GLOBAL

    target.mkdir(parents=True, exist_ok=True)

    installed = []
    for agent_name in TEAM_AGENTS:
        src = ASSETS_DIR / f"{agent_name}.json"
        if not src.exists():
            print(f"  WARN: missing asset {src}", file=sys.stderr)
            continue

        # Read the template and fix up prompt paths
        config = json.loads(src.read_text())

        # Update prompt file:// reference to use the actual path on this system
        prompt_path = resolve_prompt_path(agent_name, local, target)
        if prompt_path:
            config["prompt"] = prompt_path

        dest = target / f"{agent_name}.json"
        dest.write_text(json.dumps(config, indent=2) + "\n")
        installed.append(agent_name)

    print(json.dumps({
        "action": "install",
        "target": str(target),
        "installed": installed,
        "count": len(installed),
    }, indent=2))
    return 0


def list_agents() -> int:
    """Show which team agents are currently installed."""
    results = []
    for agent_name in TEAM_AGENTS:
        global_path = KIRO_GLOBAL / f"{agent_name}.json"
        local_path = Path.cwd() / ".kiro" / "agents" / f"{agent_name}.json"

        status = "not_installed"
        location = None
        if local_path.exists():
            status = "installed"
            location = "local"
        elif global_path.exists():
            status = "installed"
            location = "global"

        results.append({
            "agent": agent_name,
            "status": status,
            "location": location,
        })

    all_installed = all(r["status"] == "installed" for r in results)
    print(json.dumps({
        "agents": results,
        "all_installed": all_installed,
    }, indent=2))
    return 0


def uninstall_agents(local: bool = False) -> int:
    """Remove team agent configs."""
    if local:
        target = Path.cwd() / ".kiro" / "agents"
    else:
        target = KIRO_GLOBAL

    removed = []
    for agent_name in TEAM_AGENTS:
        path = target / f"{agent_name}.json"
        if path.exists():
            path.unlink()
            removed.append(agent_name)

    print(json.dumps({
        "action": "uninstall",
        "target": str(target),
        "removed": removed,
        "count": len(removed),
    }, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="agents.py",
        description="Manage agent-team agent configurations",
    )
    sub = parser.add_subparsers(dest="command")

    p_install = sub.add_parser("install", help="Install team agent configs")
    p_install.add_argument("--local", action="store_true", help="Install to .kiro/agents/ (project-local)")

    sub.add_parser("list", help="Show installed team agents")

    p_uninstall = sub.add_parser("uninstall", help="Remove team agent configs")
    p_uninstall.add_argument("--local", action="store_true", help="Remove from .kiro/agents/ (project-local)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "install": lambda: install_agents(args.local),
        "list": list_agents,
        "uninstall": lambda: uninstall_agents(args.local),
    }

    return commands[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
