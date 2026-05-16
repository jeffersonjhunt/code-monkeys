#!/usr/bin/env python3
"""Skill Changelog & Versioning Tool

Manage versions and changelogs for skills.

Usage:
    python changelog.py show --skill NAME
    python changelog.py show-all
    python changelog.py bump --skill NAME --type patch|minor|major
    python changelog.py add --skill NAME --message "Description of change"
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def read_skill_version(skill_dir):
    """Read current version from SKILL.md frontmatter."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None
    content = skill_md.read_text()
    m = re.search(r'version:\s*"?([^"\n]+)"?', content)
    return m.group(1).strip() if m else None


def write_skill_version(skill_dir, new_version):
    """Update version in SKILL.md frontmatter."""
    skill_md = skill_dir / "SKILL.md"
    content = skill_md.read_text()
    updated = re.sub(
        r'(version:\s*)"?[^"\n]+"?',
        f'\\1"{new_version}"',
        content
    )
    skill_md.write_text(updated)


def bump_version(version, bump_type):
    """Bump a semver-like version string."""
    parts = version.split(".")
    if len(parts) == 1:
        parts = [parts[0], "0", "0"]
    elif len(parts) == 2:
        parts = [parts[0], parts[1], "0"]

    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1

    return f"{major}.{minor}.{patch}"


def read_changelog(skill_dir):
    """Read CHANGELOG.md for a skill."""
    changelog = skill_dir / "CHANGELOG.md"
    if not changelog.exists():
        return None
    return changelog.read_text()


def append_changelog(skill_dir, version, message):
    """Add an entry to the skill's CHANGELOG.md."""
    changelog = skill_dir / "CHANGELOG.md"
    today = date.today().isoformat()
    entry = f"\n## [{version}] - {today}\n\n- {message}\n"

    if changelog.exists():
        content = changelog.read_text()
        # Insert after the title line
        lines = content.split("\n", 1)
        if len(lines) > 1:
            content = lines[0] + "\n" + entry + lines[1]
        else:
            content += entry
    else:
        content = f"# Changelog — {skill_dir.name}\n{entry}"

    changelog.write_text(content)


def cmd_show(skill_name):
    skill_dir = ROOT / skill_name
    if not skill_dir.exists():
        print(f"Error: skill '{skill_name}' not found.", file=sys.stderr)
        sys.exit(1)
    version = read_skill_version(skill_dir)
    changelog = read_changelog(skill_dir)
    if changelog:
        print(changelog)
    else:
        print(f"{skill_name} v{version or 'unknown'} — no changelog yet.")


def cmd_show_all():
    skills = sorted(ROOT.glob("*/SKILL.md"))
    data = []
    for skill_md in skills:
        name = skill_md.parent.name
        version = read_skill_version(skill_md.parent)
        data.append({"name": name, "version": version or "unknown"})
    print(json.dumps(data, indent=2))


def cmd_bump(skill_name, bump_type):
    skill_dir = ROOT / skill_name
    if not skill_dir.exists():
        print(f"Error: skill '{skill_name}' not found.", file=sys.stderr)
        sys.exit(1)

    current = read_skill_version(skill_dir)
    if not current:
        current = "1.0.0"

    new_version = bump_version(current, bump_type)
    write_skill_version(skill_dir, new_version)
    append_changelog(skill_dir, new_version, f"Version bump ({bump_type})")
    print(json.dumps({"skill": skill_name, "old_version": current, "new_version": new_version}))


def cmd_add(skill_name, message):
    skill_dir = ROOT / skill_name
    if not skill_dir.exists():
        print(f"Error: skill '{skill_name}' not found.", file=sys.stderr)
        sys.exit(1)

    version = read_skill_version(skill_dir) or "unknown"
    append_changelog(skill_dir, version, message)
    print(f"Added changelog entry for {skill_name} v{version}")


def main():
    parser = argparse.ArgumentParser(description="Skill versioning and changelog.")
    parser.add_argument("command", choices=["show", "show-all", "bump", "add"])
    parser.add_argument("--skill", help="Skill name")
    parser.add_argument("--type", choices=["patch", "minor", "major"], default="patch")
    parser.add_argument("--message", help="Changelog message (for add)")
    args = parser.parse_args()

    if args.command == "show-all":
        cmd_show_all()
    elif args.command == "show":
        if not args.skill:
            print("Error: --skill required", file=sys.stderr)
            sys.exit(1)
        cmd_show(args.skill)
    elif args.command == "bump":
        if not args.skill:
            print("Error: --skill required", file=sys.stderr)
            sys.exit(1)
        cmd_bump(args.skill, args.type)
    elif args.command == "add":
        if not args.skill or not args.message:
            print("Error: --skill and --message required", file=sys.stderr)
            sys.exit(1)
        cmd_add(args.skill, args.message)


if __name__ == "__main__":
    main()
