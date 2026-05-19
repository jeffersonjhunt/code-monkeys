"""Tests for docs-issues skill."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ISSUES = str(ROOT / "docs-issues" / "scripts" / "issues.py")


def run(args, input_data=None, cwd=None):
    return subprocess.run(
        [sys.executable, ISSUES] + args,
        capture_output=True, text=True, input=input_data, cwd=cwd
    )


@pytest.fixture
def reviews_root(tmp_path):
    return str(tmp_path / "reviews")


# --- Help / basic ---

def test_help():
    r = run(["--help"])
    assert r.returncode == 0
    assert "issues" in r.stdout.lower()


def test_list_empty(reviews_root):
    r = run(["list", "--root", reviews_root])
    assert r.returncode == 0
    assert "no issues" in r.stdout


# --- new ---

def test_new_bug(reviews_root):
    r = run(["new", "--root", reviews_root, "--kind", "bug",
             "--title", "Test bug", "--severity", "major"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["id"] == "bug-001"
    assert Path(data["created"]).exists()


def test_new_invalid_kind(reviews_root):
    r = run(["new", "--root", reviews_root, "--kind", "bogus", "--title", "Test"])
    assert r.returncode != 0


def test_new_invalid_severity(reviews_root):
    r = run(["new", "--root", reviews_root, "--kind", "bug",
             "--title", "Test", "--severity", "bogus"])
    assert r.returncode != 0


def test_new_increments_id(reviews_root):
    run(["new", "--root", reviews_root, "--kind", "bug", "--title", "First"])
    r = run(["new", "--root", reviews_root, "--kind", "bug", "--title", "Second"])
    data = json.loads(r.stdout)
    assert data["id"] == "bug-002"


def test_new_per_kind_id_sequence(reviews_root):
    run(["new", "--root", reviews_root, "--kind", "bug", "--title", "B"])
    r = run(["new", "--root", reviews_root, "--kind", "feature", "--title", "F"])
    data = json.loads(r.stdout)
    assert data["id"] == "feature-001"


# --- list ---

def test_list_table(reviews_root):
    run(["new", "--root", reviews_root, "--kind", "bug", "--title", "Test"])
    r = run(["list", "--root", reviews_root])
    assert r.returncode == 0
    assert "bug-001" in r.stdout
    assert "Test" in r.stdout


def test_list_json(reviews_root):
    run(["new", "--root", reviews_root, "--kind", "bug", "--title", "Test"])
    r = run(["list", "--root", reviews_root, "--format", "json"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert len(data) == 1
    assert data[0]["id"] == "bug-001"


def test_list_filter_kind(reviews_root):
    run(["new", "--root", reviews_root, "--kind", "bug", "--title", "B"])
    run(["new", "--root", reviews_root, "--kind", "feature", "--title", "F"])
    r = run(["list", "--root", reviews_root, "--kind", "bug", "--format", "json"])
    data = json.loads(r.stdout)
    assert len(data) == 1
    assert data[0]["kind"] == "bug"


def test_list_filter_status(reviews_root):
    run(["new", "--root", reviews_root, "--kind", "bug", "--title", "Test"])
    r = run(["list", "--root", reviews_root, "--status", "closed", "--format", "json"])
    data = json.loads(r.stdout)
    assert data == []


# --- show ---

def test_show(reviews_root):
    run(["new", "--root", reviews_root, "--kind", "bug",
         "--title", "Test bug", "--severity", "major", "--location", "x.py:1"])
    r = run(["show", "--root", reviews_root, "bug-001"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["metadata"]["id"] == "bug-001"
    assert data["metadata"]["title"] == "Test bug"
    assert data["metadata"]["severity"] == "major"
    assert data["metadata"]["location"] == "x.py:1"


def test_show_unknown(reviews_root):
    r = run(["show", "--root", reviews_root, "bug-999"])
    assert r.returncode != 0


# --- status ---

def test_status_change(reviews_root):
    run(["new", "--root", reviews_root, "--kind", "bug", "--title", "Test"])
    r = run(["status", "--root", reviews_root, "bug-001", "--set", "closed"])
    assert r.returncode == 0
    show = run(["show", "--root", reviews_root, "bug-001"])
    data = json.loads(show.stdout)
    assert data["metadata"]["status"] == "closed"


def test_status_invalid_value(reviews_root):
    run(["new", "--root", reviews_root, "--kind", "bug", "--title", "Test"])
    r = run(["status", "--root", reviews_root, "bug-001", "--set", "bogus"])
    assert r.returncode != 0


# --- export todo ---

def test_export_todo(reviews_root, tmp_path):
    run(["new", "--root", reviews_root, "--kind", "bug", "--title", "Bug A"])
    run(["new", "--root", reviews_root, "--kind", "feature", "--title", "Feature B"])
    todo = str(tmp_path / "TODO.md")
    r = run(["export", "--root", reviews_root, "--target", "todo", "--output", todo])
    assert r.returncode == 0
    content = Path(todo).read_text()
    assert "<!-- BEGIN: docs-issues -->" in content
    assert "<!-- END: docs-issues -->" in content
    assert "Bug A" in content
    assert "Feature B" in content


def test_export_todo_idempotent(reviews_root, tmp_path):
    run(["new", "--root", reviews_root, "--kind", "bug", "--title", "Bug A"])
    todo = str(tmp_path / "TODO.md")
    run(["export", "--root", reviews_root, "--target", "todo", "--output", todo])
    first = Path(todo).read_text()
    run(["export", "--root", reviews_root, "--target", "todo", "--output", todo])
    second = Path(todo).read_text()
    assert first == second


def test_export_todo_preserves_user_content(reviews_root, tmp_path):
    todo = tmp_path / "TODO.md"
    todo.write_text("# My Project TODO\n\nHand-written content.\n")
    run(["new", "--root", reviews_root, "--kind", "bug", "--title", "Test"])
    run(["export", "--root", reviews_root, "--target", "todo", "--output", str(todo)])
    content = todo.read_text()
    assert "# My Project TODO" in content
    assert "Hand-written content." in content
    assert "<!-- BEGIN: docs-issues -->" in content


def test_export_todo_only_open_issues(reviews_root, tmp_path):
    run(["new", "--root", reviews_root, "--kind", "bug", "--title", "Open bug"])
    run(["new", "--root", reviews_root, "--kind", "bug", "--title", "Closed bug"])
    run(["status", "--root", reviews_root, "bug-002", "--set", "closed"])
    todo = str(tmp_path / "TODO.md")
    run(["export", "--root", reviews_root, "--target", "todo", "--output", todo])
    content = Path(todo).read_text()
    assert "Open bug" in content
    assert "Closed bug" not in content


# --- export stdout ---

def test_export_stdout(reviews_root):
    run(["new", "--root", reviews_root, "--kind", "bug",
         "--title", "Test bug", "--description", "Bug body text"])
    r = run(["export", "--root", reviews_root, "--target", "stdout"])
    assert r.returncode == 0
    assert "[bug-001] Test bug" in r.stdout
    assert "Bug body text" in r.stdout


# --- export github/gitlab missing CLI ---

def test_export_github_missing_cli(reviews_root, monkeypatch):
    """If gh CLI is not on PATH, export should fail with a clear error."""
    run(["new", "--root", reviews_root, "--kind", "bug", "--title", "Test"])
    # Simulate no gh on PATH by setting empty PATH for this run
    env = {"PATH": "/nonexistent"}
    r = subprocess.run(
        [sys.executable, ISSUES, "export", "--root", reviews_root, "--target", "github"],
        capture_output=True, text=True, env=env
    )
    assert r.returncode == 2
    assert "gh" in r.stderr.lower()


# --- frontmatter parser/writer roundtrip ---

def test_frontmatter_roundtrip(reviews_root):
    """Create an issue, modify its body, ensure status update preserves body."""
    run(["new", "--root", reviews_root, "--kind", "bug",
         "--title", "Test", "--description", "Original body"])
    show1 = run(["show", "--root", reviews_root, "bug-001"])
    body1 = json.loads(show1.stdout)["body"]

    # Change status (writes back)
    run(["status", "--root", reviews_root, "bug-001", "--set", "closed"])
    show2 = run(["show", "--root", reviews_root, "bug-001"])
    body2 = json.loads(show2.stdout)["body"]

    assert "Original body" in body2
    # Body should be substantively preserved
    assert body1.strip() == body2.strip()
