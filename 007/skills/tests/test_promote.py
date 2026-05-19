"""Tests for review-adversarial promote.py."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LOOP = str(ROOT / "review-adversarial" / "scripts" / "loop.py")
REVIEW = str(ROOT / "review-adversarial" / "scripts" / "review.py")
RESPOND = str(ROOT / "review-adversarial" / "scripts" / "respond.py")
PROMOTE = str(ROOT / "review-adversarial" / "scripts" / "promote.py")
ISSUES = str(ROOT / "docs-issues" / "scripts" / "issues.py")


def run(script, args, input_data=None):
    return subprocess.run(
        [sys.executable, script] + args,
        capture_output=True, text=True, input=input_data
    )


SAMPLE_FINDINGS = json.dumps([
    {
        "id": "F1",
        "severity": "major",
        "category": "security",
        "location": "auth.py:42",
        "description": "SQL injection",
        "suggestion": "Use parameterized queries",
        "title": "SQL injection in auth"
    },
    {
        "id": "F2",
        "severity": "minor",
        "category": "clarity",
        "location": "utils.py:10",
        "description": "Unclear variable name",
        "suggestion": "Rename x to user_count",
        "title": "Unclear variable name"
    },
    {
        "id": "F3",
        "severity": "nit",
        "category": "clarity",
        "location": "app.py:1",
        "description": "Missing docstring",
        "suggestion": "Add module docstring",
        "title": "Missing docstring"
    }
])


@pytest.fixture
def review_session(tmp_path):
    """Set up a review session with sample findings, returns paths."""
    state = str(tmp_path / "state.json")
    output = str(tmp_path / "docs" / "reviews")
    run(LOOP, ["init", "--state", state])
    run(REVIEW, ["--state", state], input_data=SAMPLE_FINDINGS)
    return state, output, tmp_path


# --- Help ---

def test_promote_help():
    r = run(PROMOTE, ["--help"])
    assert r.returncode == 0


# --- Auto-classification ---

def test_promote_auto_classifies_security_as_bug(review_session):
    state, output, _ = review_session
    r = run(PROMOTE, ["--state", state, "--output", output])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    promoted_kinds = {p["finding"]: p["kind"] for p in data["promoted"]}
    assert promoted_kinds.get("F1") == "bug"


def test_promote_auto_classifies_clarity_as_debt(review_session):
    state, output, _ = review_session
    r = run(PROMOTE, ["--state", state, "--output", output])
    data = json.loads(r.stdout)
    promoted_kinds = {p["finding"]: p["kind"] for p in data["promoted"]}
    assert promoted_kinds.get("F2") == "debt"


# --- Skipping ---

def test_promote_skips_nit_by_default(review_session):
    state, output, _ = review_session
    r = run(PROMOTE, ["--state", state, "--output", output])
    data = json.loads(r.stdout)
    skipped_ids = [s["finding"] for s in data["skipped"]]
    assert "F3" in skipped_ids


def test_promote_can_include_nit(review_session):
    state, output, _ = review_session
    r = run(PROMOTE, ["--state", state, "--output", output, "--skip", ""])
    data = json.loads(r.stdout)
    promoted_ids = [p["finding"] for p in data["promoted"]]
    assert "F3" in promoted_ids


def test_promote_skips_disputed_by_default(review_session):
    state, output, _ = review_session
    run(RESPOND, ["--state", state, "--resolve", "F1=disputed"])
    r = run(PROMOTE, ["--state", state, "--output", output])
    data = json.loads(r.stdout)
    skipped = {s["finding"]: s["reason"] for s in data["skipped"]}
    assert skipped.get("F1", "").startswith("disposition=")


# --- Explicit classification ---

def test_promote_classify_override(review_session):
    state, output, _ = review_session
    r = run(PROMOTE, ["--state", state, "--output", output,
                      "--classify", "F1=feature", "F2=question"])
    data = json.loads(r.stdout)
    kinds = {p["finding"]: p["kind"] for p in data["promoted"]}
    assert kinds.get("F1") == "feature"
    assert kinds.get("F2") == "question"


def test_promote_classify_invalid_kind(review_session):
    state, output, _ = review_session
    r = run(PROMOTE, ["--state", state, "--output", output, "--classify", "F1=bogus"])
    assert r.returncode != 0
    assert "invalid kind" in r.stderr


# --- File creation ---

def test_promote_creates_files(review_session):
    state, output, _ = review_session
    r = run(PROMOTE, ["--state", state, "--output", output])
    data = json.loads(r.stdout)
    for p in data["promoted"]:
        assert Path(p["path"]).exists()


def test_promote_files_are_valid_issues(review_session):
    """Files created by promote.py should be readable by docs-issues."""
    state, output, _ = review_session
    run(PROMOTE, ["--state", state, "--output", output])
    r = run(ISSUES, ["list", "--root", output, "--format", "json"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert len(data) >= 2
    # One bug from F1, one debt from F2
    kinds = {i["kind"] for i in data}
    assert "bug" in kinds
    assert "debt" in kinds


def test_promote_preserves_source_provenance(review_session):
    state, output, _ = review_session
    run(PROMOTE, ["--state", state, "--output", output])
    r = run(ISSUES, ["list", "--root", output, "--format", "json"])
    data = json.loads(r.stdout)
    for issue in data:
        show = run(ISSUES, ["show", "--root", output, issue["id"]])
        meta = json.loads(show.stdout)["metadata"]
        assert meta["source"].startswith("review-adversarial:F")


# --- Idempotency ---

def test_promote_idempotent(review_session):
    state, output, _ = review_session
    r1 = run(PROMOTE, ["--state", state, "--output", output])
    promoted_first = json.loads(r1.stdout)["promoted"]
    r2 = run(PROMOTE, ["--state", state, "--output", output])
    promoted_second = json.loads(r2.stdout)["promoted"]
    assert len(promoted_first) > 0
    assert len(promoted_second) == 0


# --- Dry run ---

def test_promote_dry_run(review_session):
    state, output, _ = review_session
    r = run(PROMOTE, ["--state", state, "--output", output, "--dry-run"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "would_write" in data["promoted"][0]
    # No files actually created
    assert not Path(output).exists() or not any(Path(output).rglob("*.md"))


# --- Error handling ---

def test_promote_missing_state():
    r = run(PROMOTE, ["--state", "/nonexistent.json", "--output", "/tmp/x"])
    assert r.returncode != 0
    assert "cannot read state" in r.stderr
