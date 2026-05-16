#!/usr/bin/env python3
"""Skill Dependency Resolver

Reads SKILL.md frontmatter from all skills, builds a dependency graph,
and outputs a topologically sorted install order.

Usage:
    python resolve-deps.py [--skill NAME] [--check] [--graph]

Options:
    --skill NAME   Resolve dependencies for a specific skill
    --check        Validate all dependencies (no missing, no cycles)
    --graph        Print the dependency graph as JSON
"""

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def parse_frontmatter(path):
    """Extract YAML frontmatter as a dict (minimal parser, no deps)."""
    content = path.read_text()
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    # Simple key-value + list parser for frontmatter
    data = {}
    current_key = None
    current_list = None
    for line in parts[1].splitlines():
        list_match = re.match(r'^  - (.+)$', line)
        if list_match and current_key:
            if current_list is None:
                current_list = []
            current_list.append(list_match.group(1).strip())
            data[current_key] = current_list
            continue
        kv = re.match(r'^(\w[\w-]*):\s*(.*)$', line)
        if kv:
            if current_list is not None:
                current_list = None
            current_key = kv.group(1)
            val = kv.group(2).strip()
            if val:
                data[current_key] = val
            else:
                current_list = []
                data[current_key] = current_list
        elif line.strip() == "":
            current_key = None
            current_list = None
    return data


def discover_skills():
    """Find all skills and their dependencies."""
    skills = {}
    for skill_md in ROOT.glob("*/SKILL.md"):
        meta = parse_frontmatter(skill_md)
        name = meta.get("name", skill_md.parent.name)
        deps = meta.get("dependencies", [])
        if isinstance(deps, str):
            deps = [d.strip() for d in deps.split(",") if d.strip()]
        skills[name] = {"path": str(skill_md.parent), "dependencies": deps}
    return skills


def topo_sort(skills, target=None):
    """Topological sort. Returns ordered list or raises on cycle."""
    if target:
        # Only resolve subgraph reachable from target
        needed = set()
        stack = [target]
        while stack:
            s = stack.pop()
            if s in needed:
                continue
            needed.add(s)
            for dep in skills.get(s, {}).get("dependencies", []):
                stack.append(dep)
    else:
        needed = set(skills.keys())

    visited = set()
    order = []
    in_progress = set()

    def visit(name):
        if name in in_progress:
            raise ValueError(f"Circular dependency detected involving: {name}")
        if name in visited:
            return
        in_progress.add(name)
        for dep in skills.get(name, {}).get("dependencies", []):
            visit(dep)
        in_progress.remove(name)
        visited.add(name)
        order.append(name)

    for name in sorted(needed):
        visit(name)

    return order


def check_deps(skills):
    """Validate: no missing deps, no cycles."""
    errors = []
    all_names = set(skills.keys())

    for name, info in skills.items():
        for dep in info["dependencies"]:
            if dep not in all_names:
                errors.append(f"{name}: depends on unknown skill '{dep}'")

    try:
        topo_sort(skills)
    except ValueError as e:
        errors.append(str(e))

    return errors


def main():
    parser = argparse.ArgumentParser(description="Resolve skill dependencies.")
    parser.add_argument("--skill", help="Resolve deps for a specific skill")
    parser.add_argument("--check", action="store_true", help="Validate all dependencies")
    parser.add_argument("--graph", action="store_true", help="Print dependency graph")
    args = parser.parse_args()

    skills = discover_skills()

    if args.check:
        errors = check_deps(skills)
        if errors:
            for e in errors:
                print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps({"status": "ok", "skills": len(skills)}))
        return

    if args.graph:
        graph = {name: info["dependencies"] for name, info in skills.items()}
        print(json.dumps(graph, indent=2))
        return

    try:
        order = topo_sort(skills, target=args.skill)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps({"install_order": order}))


if __name__ == "__main__":
    main()
