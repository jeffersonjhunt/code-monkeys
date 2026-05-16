"""Tests for review-adversarial skill."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LOOP = str(ROOT / "review-adversarial" / "scripts" / "loop.py")
REVIEW = str(ROOT / "review-adversarial" / "scripts" / "review.py")
RESPOND = str(ROOT / "review-adversarial" / "scripts" / "respond.py")

SAMPLE_FINDINGS = json.dumps([
    {
        "id": "F1",
        "severity": "major",
        "category": "security",
        "location": "auth.py:42",
        "description": "SQL injection",
        "suggestion": "Use parameterized queries"
    },
    {
        "id": "F2",
        "severity": "minor",
        "category": "clarity",
        "location": "utils.py:10",
        "description": "Unclear variable name",
        "suggestion": "Rename x to user_count"
    }
])


def run(script, args, input_data=None):
    return subprocess.run(
        [sys.executable, script] + args,
        capture_output=True, text=True, input=input_data
    )


@pytest.fixture
def state_file(tmp_path):
    return str(tmp_path / "state.json")


# --- loop.py tests ---

def test_loop_help():
    r = run(LOOP, ["--help"])
    assert r.returncode == 0


def test_loop_init(state_file):
    r = run(LOOP, ["init", "--state", state_file, "--max-rounds", "3"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["max_rounds"] == 3
    with open(state_file) as f:
        state = json.load(f)
    assert state["current_round"] == 1
    assert state["status"] == "active"


def test_loop_status(state_file):
    run(LOOP, ["init", "--state", state_file])
    r = run(LOOP, ["status", "--state", state_file])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["status"] == "active"
    assert data["unresolved"] == 0


def test_loop_converges_when_no_findings(state_file):
    run(LOOP, ["init", "--state", state_file])
    r = run(LOOP, ["next", "--state", state_file])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["result"] == "converged"


def test_loop_continues_with_unresolved(state_file):
    run(LOOP, ["init", "--state", state_file, "--max-rounds", "3"])
    # Add findings
    run(REVIEW, ["--state", state_file], input_data=SAMPLE_FINDINGS)
    r = run(LOOP, ["next", "--state", state_file])
    data = json.loads(r.stdout)
    assert data["result"] == "continue"
    assert data["round"] == 2


def test_loop_max_rounds(state_file):
    run(LOOP, ["init", "--state", state_file, "--max-rounds", "1"])
    run(REVIEW, ["--state", state_file], input_data=SAMPLE_FINDINGS)
    r = run(LOOP, ["next", "--state", state_file])
    data = json.loads(r.stdout)
    assert data["result"] == "max_rounds"


def test_loop_summary(state_file):
    run(LOOP, ["init", "--state", state_file])
    run(REVIEW, ["--state", state_file], input_data=SAMPLE_FINDINGS)
    r = run(LOOP, ["summary", "--state", state_file])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["total_findings"] == 2
    assert data["by_disposition"]["unresolved"] == 2


# --- review.py tests ---

def test_review_help():
    r = run(REVIEW, ["--help"])
    assert r.returncode == 0


def test_review_records_findings(state_file):
    run(LOOP, ["init", "--state", state_file])
    r = run(REVIEW, ["--state", state_file], input_data=SAMPLE_FINDINGS)
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["recorded"] == 2
    assert data["round"] == 1


def test_review_validates_findings(state_file):
    run(LOOP, ["init", "--state", state_file])
    bad = json.dumps([{"id": "F1", "severity": "bogus", "category": "security",
                       "location": "x", "description": "x", "suggestion": "x"}])
    r = run(REVIEW, ["--state", state_file], input_data=bad)
    assert r.returncode != 0
    assert "invalid severity" in r.stderr


def test_review_rejects_missing_fields(state_file):
    run(LOOP, ["init", "--state", state_file])
    bad = json.dumps([{"id": "F1"}])
    r = run(REVIEW, ["--state", state_file], input_data=bad)
    assert r.returncode != 0
    assert "missing fields" in r.stderr


# --- respond.py tests ---

def test_respond_help():
    r = run(RESPOND, ["--help"])
    assert r.returncode == 0


def test_respond_marks_fixed(state_file):
    run(LOOP, ["init", "--state", state_file])
    run(REVIEW, ["--state", state_file], input_data=SAMPLE_FINDINGS)
    r = run(RESPOND, ["--state", state_file, "--resolve", "F1=fixed"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "F1" in data["ids"]


def test_respond_disputed_with_rationale(state_file):
    run(LOOP, ["init", "--state", state_file])
    run(REVIEW, ["--state", state_file], input_data=SAMPLE_FINDINGS)
    r = run(RESPOND, ["--state", state_file, "--resolve", "F2=disputed",
                      "--rationale", "F2:Not a real issue"])
    assert r.returncode == 0
    with open(state_file) as f:
        state = json.load(f)
    resp = state["rounds"]["round_1"]["responses"]["F2"]
    assert resp["disposition"] == "disputed"
    assert resp["rationale"] == "Not a real issue"


def test_respond_invalid_disposition(state_file):
    run(LOOP, ["init", "--state", state_file])
    run(REVIEW, ["--state", state_file], input_data=SAMPLE_FINDINGS)
    r = run(RESPOND, ["--state", state_file, "--resolve", "F1=bogus"])
    assert r.returncode != 0
    assert "invalid disposition" in r.stderr


def test_respond_unknown_id(state_file):
    run(LOOP, ["init", "--state", state_file])
    run(REVIEW, ["--state", state_file], input_data=SAMPLE_FINDINGS)
    r = run(RESPOND, ["--state", state_file, "--resolve", "F99=fixed"])
    assert r.returncode != 0
    assert "unknown finding ID" in r.stderr


# --- Full loop lifecycle ---

def test_full_loop_lifecycle(state_file):
    """Test a complete review loop: init → review → respond → converge."""
    run(LOOP, ["init", "--state", state_file, "--max-rounds", "3"])
    run(REVIEW, ["--state", state_file], input_data=SAMPLE_FINDINGS)

    # Resolve all findings
    run(RESPOND, ["--state", state_file, "--resolve", "F1=fixed", "F2=accepted"])

    # Should converge
    r = run(LOOP, ["next", "--state", state_file])
    data = json.loads(r.stdout)
    assert data["result"] == "converged"

    # Summary should reflect dispositions
    r = run(LOOP, ["summary", "--state", state_file])
    summary = json.loads(r.stdout)
    assert summary["by_disposition"]["fixed"] == 1
    assert summary["by_disposition"]["accepted"] == 1
    assert summary["by_disposition"]["unresolved"] == 0
