#!/usr/bin/env python3
"""Obsidian Tasks MCP Server — query and manage markdown tasks in an Obsidian vault."""

import os
import re
from dataclasses import dataclass
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("obsidian-tasks")

VAULT_PATH = Path(os.environ.get("OBSIDIAN_VAULT_PATH", os.path.expanduser("~/Documents/Obsidian")))

TASK_RE = re.compile(
    r"^(?P<indent>\s*)- \[(?P<status>[x ])\] "
    r"(?P<text>.*?)(?:\s*(?P<meta>(?:[📅⏳🛫✅➕]|#)\S*).*)?$"
)
DATE_RE = re.compile(r"[📅⏳🛫✅➕]\s*(\d{4}-\d{2}-\d{2})")
TAG_RE = re.compile(r"#([\w/\-]+)")


@dataclass
class Task:
    file: str
    line_num: int
    text: str
    status: str
    tags: list[str]
    dates: dict[str, str]
    raw: str


def _parse_tasks(vault: Path, glob_pattern: str = "**/*.md") -> list[Task]:
    tasks = []
    for md_file in vault.glob(glob_pattern):
        try:
            lines = md_file.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(lines):
            m = TASK_RE.match(line)
            if not m:
                continue
            text = m.group("text")
            status = "done" if m.group("status") == "x" else "open"
            tags = TAG_RE.findall(line)
            dates = {}
            for emoji, key in [("📅", "due"), ("⏳", "scheduled"), ("🛫", "start"), ("✅", "completed"), ("➕", "created")]:
                idx = line.find(emoji)
                if idx >= 0:
                    dm = re.search(r"(\d{4}-\d{2}-\d{2})", line[idx:])
                    if dm:
                        dates[key] = dm.group(1)
            rel = str(md_file.relative_to(vault))
            tasks.append(Task(file=rel, line_num=i + 1, text=text, status=status, tags=tags, dates=dates, raw=line))
    return tasks


def _format_tasks(tasks: list[Task]) -> str:
    if not tasks:
        return "No tasks found."
    lines = []
    for t in tasks:
        marker = "✅" if t.status == "done" else "⬜"
        date_str = f" (due: {t.dates['due']})" if "due" in t.dates else ""
        tag_str = f" [{', '.join('#' + tag for tag in t.tags)}]" if t.tags else ""
        lines.append(f"{marker} {t.text}{date_str}{tag_str}\n   └─ {t.file}:{t.line_num}")
    return "\n".join(lines)


@mcp.tool()
def list_tasks(status: str = "all", tag: str = "", due_before: str = "", path_filter: str = "") -> str:
    """List tasks from the Obsidian vault.

    Args:
        status: Filter by status — 'open', 'done', or 'all'
        tag: Filter by tag name (without #)
        due_before: Show tasks due on or before this date (YYYY-MM-DD)
        path_filter: Only search files matching this glob (e.g. 'Projects/**/*.md')
    """
    if not VAULT_PATH.is_dir():
        return f"Vault not found at: {VAULT_PATH}"
    glob = path_filter if path_filter else "**/*.md"
    tasks = _parse_tasks(VAULT_PATH, glob)
    if status != "all":
        tasks = [t for t in tasks if t.status == status]
    if tag:
        tasks = [t for t in tasks if tag in t.tags]
    if due_before:
        tasks = [t for t in tasks if t.dates.get("due", "9999-99-99") <= due_before]
    return _format_tasks(tasks)


@mcp.tool()
def search_tasks(query: str, status: str = "all") -> str:
    """Search tasks by text content.

    Args:
        query: Text to search for (case-insensitive substring match)
        status: Filter by status — 'open', 'done', or 'all'
    """
    if not VAULT_PATH.is_dir():
        return f"Vault not found at: {VAULT_PATH}"
    tasks = _parse_tasks(VAULT_PATH)
    q = query.lower()
    tasks = [t for t in tasks if q in t.text.lower()]
    if status != "all":
        tasks = [t for t in tasks if t.status == status]
    return _format_tasks(tasks)


@mcp.tool()
def toggle_task(file: str, line_num: int) -> str:
    """Toggle a task's completion status.

    Args:
        file: Relative path to the file within the vault
        line_num: 1-based line number of the task
    """
    target = VAULT_PATH / file
    if not target.is_file():
        return f"File not found: {file}"
    lines = target.read_text(encoding="utf-8").splitlines()
    idx = line_num - 1
    if idx < 0 or idx >= len(lines):
        return f"Line {line_num} out of range (file has {len(lines)} lines)"
    line = lines[idx]
    if "- [ ] " in line:
        lines[idx] = line.replace("- [ ] ", "- [x] ", 1)
        action = "completed"
    elif "- [x] " in line:
        lines[idx] = line.replace("- [x] ", "- [ ] ", 1)
        action = "reopened"
    else:
        return f"Line {line_num} is not a task: {line.strip()}"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f"Task {action}: {lines[idx].strip()}"


@mcp.tool()
def task_summary() -> str:
    """Get a summary of task counts by status and upcoming due dates."""
    if not VAULT_PATH.is_dir():
        return f"Vault not found at: {VAULT_PATH}"
    tasks = _parse_tasks(VAULT_PATH)
    open_tasks = [t for t in tasks if t.status == "open"]
    done_tasks = [t for t in tasks if t.status == "done"]
    overdue = [t for t in open_tasks if "due" in t.dates]
    overdue.sort(key=lambda t: t.dates["due"])
    summary = f"Total: {len(tasks)} | Open: {len(open_tasks)} | Done: {len(done_tasks)}"
    if overdue[:5]:
        summary += "\n\nUpcoming/overdue:"
        for t in overdue[:5]:
            summary += f"\n  📅 {t.dates['due']} — {t.text} ({t.file})"
    return summary


if __name__ == "__main__":
    mcp.run(transport="stdio")
