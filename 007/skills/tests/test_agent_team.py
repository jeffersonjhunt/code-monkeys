"""Tests for the agent-team skill.

Tests the orchestrator state machine and agents.py config manager as black boxes.
Every gate is tested negatively — ensuring invalid transitions are refused.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORCHESTRATOR = str(ROOT / "agent-team" / "scripts" / "orchestrator.py")
AGENTS = str(ROOT / "agent-team" / "scripts" / "agents.py")


def run(*args, cwd=None, stdin=None):
    return subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        input=stdin,
    )


def init(state, task="build a REST API", skip_design=False, cwd=None):
    args = [ORCHESTRATOR, "--state", state, "init", "--task", task]
    if skip_design:
        args.append("--skip-design")
    return run(*args, cwd=cwd)


def next_phase(state, cwd=None):
    return run(ORCHESTRATOR, "--state", state, "next", cwd=cwd)


def advance(state, phase, output=None, stdin=None, cwd=None):
    args = [ORCHESTRATOR, "--state", state, "advance", phase]
    if output:
        args.extend(["--output", output])
    return run(*args, cwd=cwd, stdin=stdin)


def decide(state, phase, action, feedback=None, cwd=None):
    args = [ORCHESTRATOR, "--state", state, "decide", phase, "--action", action]
    if feedback:
        args.extend(["--feedback", feedback])
    return run(*args, cwd=cwd)


def status(state, cwd=None):
    return run(ORCHESTRATOR, "--state", state, "status", cwd=cwd)


def summary(state, cwd=None):
    return run(ORCHESTRATOR, "--state", state, "summary", cwd=cwd)


# ─── Help ────────────────────────────────────────────────────────────────────


def test_orchestrator_help():
    r = run(ORCHESTRATOR, "--help")
    assert r.returncode == 0
    assert "orchestrator" in r.stdout.lower() or "usage" in r.stdout.lower()


def test_agents_help():
    r = run(AGENTS, "--help")
    assert r.returncode == 0
    assert "agents" in r.stdout.lower() or "usage" in r.stdout.lower()


# ─── Init ────────────────────────────────────────────────────────────────────


def test_init_creates_state():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "state.json")
        r = init(state, task="build something")
        assert r.returncode == 0
        result = json.loads(r.stdout)
        assert result["status"] == "initialized"
        assert result["next_phase"] == "intake"
        assert result["next_agent"] == "team-pm"
        # State file exists
        assert Path(state).exists()


def test_init_empty_task_refused():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "state.json")
        r = init(state, task="  ")
        assert r.returncode == 1
        assert "must not be empty" in r.stderr


def test_init_skip_design():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "state.json")
        r = init(state, task="CLI tool", skip_design=True)
        assert r.returncode == 0
        result = json.loads(r.stdout)
        assert "design" in result["skipped"]


# ─── Next ────────────────────────────────────────────────────────────────────


def test_next_returns_first_phase():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "state.json")
        init(state, task="build an API")
        r = next_phase(state)
        assert r.returncode == 0
        result = json.loads(r.stdout)
        assert result["phase"] == "intake"
        assert result["lead_agent"] == "team-pm"
        assert "prompt" in result


def test_next_missing_state():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "nonexistent.json")
        r = next_phase(state)
        assert r.returncode == 2


# ─── Advance ─────────────────────────────────────────────────────────────────


def test_advance_records_output():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "state.json")
        artifact = Path(d) / "brief.md"
        artifact.write_text("# Project Brief\n\nBuild an API for books.")

        init(state, task="build an API")
        r = advance(state, "intake", output=str(artifact))
        assert r.returncode == 0
        result = json.loads(r.stdout)
        assert result["status"] == "awaiting_decision"


def test_advance_wrong_phase_refused():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "state.json")
        init(state, task="build an API")
        # Try to advance planning before intake
        r = advance(state, "planning", stdin="some output")
        assert r.returncode == 1
        assert "current phase" in r.stderr


def test_advance_no_output_refused():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "state.json")
        init(state, task="build an API")
        r = advance(state, "intake")
        assert r.returncode == 1
        assert "no output" in r.stderr


def test_advance_stdin():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "state.json")
        init(state, task="build an API")
        r = advance(state, "intake", stdin="# Brief\n\nContent here.")
        assert r.returncode == 0


# ─── Decide ──────────────────────────────────────────────────────────────────


def test_decide_approve_advances():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "state.json")
        init(state, task="build an API")
        advance(state, "intake", stdin="# Brief\n\nContent.")
        r = decide(state, "intake", "approve")
        assert r.returncode == 0
        result = json.loads(r.stdout)
        assert result["status"] == "approve"
        assert result["next_phase"] == "planning"


def test_decide_revise_keeps_phase():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "state.json")
        init(state, task="build an API")
        advance(state, "intake", stdin="# Brief\n\nContent.")
        r = decide(state, "intake", "revise", feedback="add more detail on auth")
        assert r.returncode == 0
        result = json.loads(r.stdout)
        assert result["status"] == "revise"
        # Next phase should still be intake (it got reset)
        r2 = next_phase(state)
        result2 = json.loads(r2.stdout)
        assert result2["phase"] == "intake"
        # Feedback is in the prompt
        assert "add more detail on auth" in result2["prompt"]


def test_decide_skip_only_skippable():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "state.json")
        init(state, task="build an API")
        advance(state, "intake", stdin="# Brief")
        # intake is not skippable
        r = decide(state, "intake", "skip")
        assert r.returncode == 1
        assert "cannot be skipped" in r.stderr


def test_decide_skip_design():
    """Design phase IS skippable."""
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "state.json")
        init(state, task="CLI tool")

        # Walk through intake, planning, architecture
        advance(state, "intake", stdin="brief")
        decide(state, "intake", "approve")
        advance(state, "planning", stdin="plan")
        decide(state, "planning", "approve")
        advance(state, "architecture", stdin="arch doc")
        decide(state, "architecture", "approve")

        # Now at design — should be skippable
        advance(state, "design", stdin="design doc")
        r = decide(state, "design", "skip")
        assert r.returncode == 0
        result = json.loads(r.stdout)
        assert result["next_phase"] == "implementation"


def test_decide_abort():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "state.json")
        init(state, task="build an API")
        advance(state, "intake", stdin="# Brief")
        r = decide(state, "intake", "abort")
        assert r.returncode == 0
        result = json.loads(r.stdout)
        assert result["status"] == "aborted"


def test_decide_not_awaiting_refused():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "state.json")
        init(state, task="build an API")
        # Try to decide before advancing
        r = decide(state, "intake", "approve")
        assert r.returncode == 1
        assert "not awaiting" in r.stderr


def test_decide_invalid_action():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "state.json")
        init(state, task="build an API")
        advance(state, "intake", stdin="# Brief")
        r = run(ORCHESTRATOR, "--state", state, "decide", "intake", "--action", "yolo")
        # commander should reject invalid choice
        assert r.returncode != 0


# ─── Review Loop ─────────────────────────────────────────────────────────────


def test_review_loop_tracking():
    """Review revisions increment the loop counter."""
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "state.json")
        init(state, task="build an API", skip_design=True)

        # Fast-forward to review phase
        phases_before_review = ["intake", "planning", "architecture", "implementation", "testing"]
        for phase in phases_before_review:
            advance(state, phase, stdin=f"{phase} output")
            decide(state, phase, "approve")

        # Now at review
        advance(state, "review", stdin="NEEDS_CHANGES: fix SQL injection")
        r = decide(state, "review", "revise", feedback="agree, fix it")
        assert r.returncode == 0

        # Check state has review_loops incremented
        state_data = json.loads(Path(state).read_text())
        assert state_data["review_loops"] == 1


# ─── Status & Summary ────────────────────────────────────────────────────────


def test_status():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "state.json")
        init(state, task="build an API")
        r = status(state)
        assert r.returncode == 0
        result = json.loads(r.stdout)
        assert result["task"] == "build an API"
        assert result["current_phase"] == "intake"
        assert len(result["phases"]) == 8


def test_summary():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "state.json")
        init(state, task="build an API")
        advance(state, "intake", stdin="brief")
        decide(state, "intake", "approve")
        r = summary(state)
        assert r.returncode == 0
        result = json.loads(r.stdout)
        assert "intake" in result["completed_phases"]
        assert "brief" in result["artifacts_produced"]


# ─── Full Workflow ───────────────────────────────────────────────────────────


def test_full_workflow_completes():
    """Walk through all 8 phases and verify completion."""
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "state.json")
        init(state, task="build a todo app", skip_design=True)

        phases = ["intake", "planning", "architecture", "implementation", "testing", "review", "delivery"]
        for phase in phases:
            r = next_phase(state)
            result = json.loads(r.stdout)
            assert result["phase"] == phase, f"Expected {phase}, got {result['phase']}"

            advance(state, phase, stdin=f"# {phase} output\n\nContent for {phase}.")
            decide(state, phase, "approve")

        # After all phases, next should return complete
        r = next_phase(state)
        result = json.loads(r.stdout)
        assert result["phase"] is None
        assert result["status"] == "complete"


# ─── Agents.py ───────────────────────────────────────────────────────────────


def test_agents_list():
    r = run(AGENTS, "list")
    assert r.returncode == 0
    result = json.loads(r.stdout)
    assert "agents" in result
    assert len(result["agents"]) == 7  # 7 team agents


def test_agents_install_local():
    """Install to a temp .kiro/agents/ dir."""
    with tempfile.TemporaryDirectory() as d:
        kiro_dir = Path(d) / ".kiro" / "agents"
        # Monkey-patch by running from the temp dir
        r = run(AGENTS, "install", "--local", cwd=d)
        assert r.returncode == 0
        result = json.loads(r.stdout)
        assert result["action"] == "install"
        assert result["count"] == 7
        # Check files exist
        assert (kiro_dir / "team-lead.json").exists()
        assert (kiro_dir / "team-pm.json").exists()


def test_agents_uninstall_local():
    """Uninstall from a temp dir."""
    with tempfile.TemporaryDirectory() as d:
        # Install first
        run(AGENTS, "install", "--local", cwd=d)
        # Uninstall
        r = run(AGENTS, "uninstall", "--local", cwd=d)
        assert r.returncode == 0
        result = json.loads(r.stdout)
        assert result["action"] == "uninstall"
        assert result["count"] == 7
        # Files gone
        kiro_dir = Path(d) / ".kiro" / "agents"
        assert not (kiro_dir / "team-lead.json").exists()
