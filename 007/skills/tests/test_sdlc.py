"""Tests for the sdlc skill.

Every gate is tested NEGATIVELY — that it refuses when it should — because a gate that has never been
seen to fail is an assumption, and this skill exists to stop exactly that.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIFECYCLE = str(ROOT / "sdlc" / "scripts" / "lifecycle.py")
PREFLIGHT = str(ROOT / "sdlc" / "scripts" / "preflight.py")


def run(*args, cwd=None):
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True, cwd=cwd
    )


def init(state, tier="standard", task="t", why="because", cwd=None):
    return run(LIFECYCLE, "--state", state, "init", "--tier", tier, "--task", task,
               "--why", why, cwd=cwd)


def advance(state, phase, evidence="did the thing", cwd=None):
    return run(LIFECYCLE, "--state", state, "advance", phase, "--evidence", evidence,
               cwd=cwd)


def git(*args, cwd):
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)


def make_repo(path: Path, branch: str) -> None:
    git("init", "-q", cwd=path)
    git("config", "user.email", "t@t", cwd=path)
    git("config", "user.name", "t", cwd=path)
    (path / "f.txt").write_text("x")
    git("add", "-A", cwd=path)
    git("commit", "-qm", "init", cwd=path)
    git("branch", "-M", branch, cwd=path)


# --- help / basics --------------------------------------------------------------------


def test_help():
    for script in (LIFECYCLE, PREFLIGHT):
        r = run(script, "--help")
        assert r.returncode == 0
        assert "usage" in r.stdout.lower()


def test_init_reports_tier_and_phases():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "s.json")
        r = init(state)
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["tier"] == "standard"
        assert out["required_phases"][0] == "intake"
        assert "deploy" in out["required_phases"]


def test_init_rejects_unknown_tier_and_empty_why():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "s.json")
        assert init(state, tier="enormous").returncode == 1
        assert init(state, why="   ").returncode == 1


def test_status_without_init_exits_2():
    with tempfile.TemporaryDirectory() as d:
        r = run(LIFECYCLE, "--state", str(Path(d) / "nope.json"), "status")
        assert r.returncode == 2


# --- the ordering gate ----------------------------------------------------------------


def test_land_before_verify_is_refused_then_allowed():
    """The gate that would have caught this skill's own motivating incident."""
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "s.json")
        init(state)

        r = advance(state, "land", "pushed the branch")
        assert r.returncode == 1, "land must be refused before earlier phases"
        assert "verify" in r.stderr

        for p in ("intake", "plan", "isolate", "implement"):
            assert advance(state, p).returncode == 0
        assert advance(state, "verify", "negative test: gate refuses on main").returncode == 0
        assert advance(state, "review").returncode == 0

        r = advance(state, "land", "pushed the branch")
        assert r.returncode == 0, "land must be allowed once its prerequisites are met"

        # ...and the merge is NOT yet allowed: nothing has been proven on hardware.
        r = advance(state, "release", "merged")
        assert r.returncode == 1, "release must be refused before deploy/observe"
        assert "deploy" in r.stderr


def test_phase_not_in_tier_is_refused():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "s.json")
        init(state, tier="trivial")
        r = advance(state, "deploy")
        assert r.returncode == 1
        assert "not required" in r.stderr


def test_double_advance_is_refused():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "s.json")
        init(state, tier="trivial")
        assert advance(state, "isolate").returncode == 0
        assert advance(state, "isolate").returncode == 1


def test_empty_evidence_is_refused():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "s.json")
        init(state, tier="trivial")
        assert advance(state, "isolate", evidence="  ").returncode == 1


# --- tiers ----------------------------------------------------------------------------


def test_trivial_does_not_require_verify():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "s.json")
        out = json.loads(init(state, tier="trivial").stdout)
        assert out["required_phases"] == ["isolate", "implement", "land", "release"]
        assert "verify" not in out["required_phases"]


def test_undeployed_keeps_verify_but_drops_deploy_and_observe():
    """The tier exists so undeployed work is not forced to lie in either direction."""
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "s.json")
        out = json.loads(init(state, tier="undeployed").stdout)
        phases = out["required_phases"]
        assert "verify" in phases and "review" in phases, "undeployed is not a discount tier"
        assert "deploy" not in phases and "observe" not in phases

        # And the phases it does not have are actually refused, not merely absent from a list.
        r = advance(state, "deploy")
        assert r.returncode == 1
        assert "not required" in r.stderr


def test_campaign_requires_survey_first():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "s.json")
        out = json.loads(init(state, tier="campaign").stdout)
        assert out["required_phases"][0] == "survey"
        # ...and cannot be skipped
        r = advance(state, "intake")
        assert r.returncode == 1
        assert "survey" in r.stderr


# --- the verify negative-test requirement ----------------------------------------------


def test_verify_refuses_evidence_without_a_negative_test():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "s.json")
        init(state)
        for p in ("intake", "plan", "isolate", "implement"):
            advance(state, p)
        r = advance(state, "verify", "ran the tests, all green")
        assert r.returncode == 1
        assert "negative" in r.stderr.lower()

        r = advance(state, "verify", "control run with the lock removed fails; with it, passes")
        assert r.returncode == 0


# --- summary --------------------------------------------------------------------------


def test_summary_nonzero_until_complete():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "s.json")
        init(state, tier="trivial")
        r = run(LIFECYCLE, "--state", state, "summary")
        assert r.returncode == 1
        assert "INCOMPLETE" in r.stdout

        # `release` now closes every tier — even docs get merged; the tier only decides what has to
        # be true first.
        for p in ("isolate", "implement", "land"):
            advance(state, p)
        assert run(LIFECYCLE, "--state", state, "summary").returncode == 1

        advance(state, "release", "merged")
        r = run(LIFECYCLE, "--state", state, "summary")
        assert r.returncode == 0
        assert "all required phases complete" in r.stdout


# --- overrides: must CHANGE behaviour, and removal must change it back -----------------


OVERRIDE_BLOCK = """
# Project
<!-- sdlc:begin -->
tiers.trivial.phases: isolate, implement, verify, land
land.merge_by: agent
<!-- sdlc:end -->
"""


def test_override_changes_behaviour_and_removal_restores_it():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        claude = root / "CLAUDE.md"
        state = str(root / "s.json")

        # Baseline: trivial has no verify.
        out = json.loads(init(state, tier="trivial", cwd=root).stdout)
        assert "verify" not in out["required_phases"]
        assert out["config"]["merge_by"] == "host"

        # With the block: verify is required and merge_by flips.
        claude.write_text(OVERRIDE_BLOCK)
        out = json.loads(init(state, tier="trivial", cwd=root).stdout)
        assert "verify" in out["required_phases"], "override was not applied"
        assert out["config"]["merge_by"] == "agent"

        # Remove it: behaviour must go back. Proves the file is READ, not that the test
        # happened to match a default.
        claude.unlink()
        out = json.loads(init(state, tier="trivial", cwd=root).stdout)
        assert "verify" not in out["required_phases"]
        assert out["config"]["merge_by"] == "host"


def test_unknown_override_key_is_reported_not_swallowed():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "CLAUDE.md").write_text(
            "<!-- sdlc:begin -->\nnonsense.key: yes\n<!-- sdlc:end -->\n"
        )
        r = init(str(root / "s.json"), cwd=root)
        assert r.returncode == 0
        assert "nonsense.key" in r.stderr
        assert "nonsense.key" in json.loads(r.stdout)["config"]["override_problems"][0]


def test_phases_skip_removes_from_every_tier():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "CLAUDE.md").write_text(
            "<!-- sdlc:begin -->\nphases.deploy: skip\nphases.observe: skip\n<!-- sdlc:end -->\n"
        )
        out = json.loads(init(str(root / "s.json"), tier="standard", cwd=root).stdout)
        assert "deploy" not in out["required_phases"]
        assert "observe" not in out["required_phases"]


# --- release comes last ----------------------------------------------------------------


def test_release_is_the_final_phase_after_deploy_and_observe():
    """Merging before deploying makes main a promise rather than a record.

    The order is land (push) -> deploy the branch -> observe -> release (merge on the evidence).
    """
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "s.json")
        out = json.loads(init(state, tier="standard").stdout)
        assert out["required_phases"][-1] == "release"
        assert out["required_phases"].index("deploy") < out["required_phases"].index("release")
        assert out["required_phases"].index("observe") < out["required_phases"].index("release")

        for p in ("intake", "plan", "isolate", "implement"):
            advance(state, p)
        advance(state, "verify", "negative control run")
        advance(state, "review")
        advance(state, "land", "branch pushed")

        assert advance(state, "release", "merged").returncode == 1
        advance(state, "deploy", "deployed the branch sha")
        assert advance(state, "release", "merged").returncode == 1, "observe still outstanding"
        advance(state, "observe", "healthy in situ")
        assert advance(state, "release", "merged").returncode == 0


def test_summary_names_the_next_step():
    with tempfile.TemporaryDirectory() as d:
        state = str(Path(d) / "s.json")
        init(state, tier="standard")
        for p in ("intake", "plan", "isolate", "implement"):
            advance(state, p)
        advance(state, "verify", "negative control run")
        advance(state, "review")
        advance(state, "land", "pushed")
        out = run(LIFECYCLE, "--state", state, "summary").stdout
        assert "Not proven on real hardware" in out

        advance(state, "deploy", "deployed branch sha")
        advance(state, "observe", "healthy")
        out = run(LIFECYCLE, "--state", state, "summary").stdout
        assert "merge is the remaining step" in out


def test_release_merge_by_key_with_land_alias():
    """The old key keeps working; a silent un-configure would be worse than a rename."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "CLAUDE.md").write_text(
            "<!-- sdlc:begin -->\nrelease.merge_by: agent\n<!-- sdlc:end -->\n")
        assert json.loads(init(str(root / "s.json"), cwd=root).stdout)["config"]["merge_by"] == "agent"

        (root / "CLAUDE.md").write_text(
            "<!-- sdlc:begin -->\nland.merge_by: agent\n<!-- sdlc:end -->\n")
        out = json.loads(init(str(root / "s.json"), cwd=root).stdout)
        assert out["config"]["merge_by"] == "agent", "the alias must still configure"
        assert out["config"]["override_problems"] == []


# --- state file location ---------------------------------------------------------------


def test_state_lives_at_repo_root_not_cwd():
    """Init at the root, advance from a subdirectory — the bug this fixes.

    Resolving against cwd meant `advance` reported "no state, run init first" while the state file
    sat one directory up.
    """
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d) / "r"
        (repo / "sub" / "deeper").mkdir(parents=True)
        make_repo(repo, "feature")

        r = run(LIFECYCLE, "init", "--tier", "trivial", "--task", "t", "--why", "w", cwd=repo)
        assert r.returncode == 0, r.stderr
        assert (repo / ".sdlc-state.json").is_file(), "state must be written at the repo root"

        r = run(LIFECYCLE, "advance", "isolate", "--evidence", "e", cwd=repo / "sub" / "deeper")
        assert r.returncode == 0, r.stderr
        assert not (repo / "sub" / "deeper" / ".sdlc-state.json").exists()

        r = run(LIFECYCLE, "status", cwd=repo / "sub")
        assert r.returncode == 0
        assert json.loads(r.stdout)["completed"] == ["isolate"]


def test_state_file_path_is_reported():
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d) / "r"
        repo.mkdir()
        make_repo(repo, "feature")
        run(LIFECYCLE, "init", "--tier", "trivial", "--task", "t", "--why", "w", cwd=repo)
        out = json.loads(run(LIFECYCLE, "status", cwd=repo).stdout)
        assert out["state_file"].endswith(".sdlc-state.json")


def test_explicit_state_flag_still_wins():
    """The escape hatch must keep working, taken exactly as given."""
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d) / "r"
        repo.mkdir()
        make_repo(repo, "feature")
        custom = str(Path(d) / "elsewhere.json")
        r = run(LIFECYCLE, "--state", custom, "init", "--tier", "trivial",
                "--task", "t", "--why", "w", cwd=repo)
        assert r.returncode == 0, r.stderr
        assert Path(custom).is_file()
        assert not (repo / ".sdlc-state.json").exists()


def test_outside_a_repo_falls_back_to_cwd():
    with tempfile.TemporaryDirectory() as d:
        plain = Path(d) / "norepo"
        plain.mkdir()
        r = run(LIFECYCLE, "init", "--tier", "trivial", "--task", "t", "--why", "w", cwd=plain)
        assert r.returncode == 0, r.stderr
        assert (plain / ".sdlc-state.json").is_file()


# --- preflight ------------------------------------------------------------------------


def test_preflight_fails_on_main_and_passes_on_a_branch():
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d) / "r"
        repo.mkdir()
        make_repo(repo, "main")

        r = run(PREFLIGHT, "--path", str(repo))
        assert r.returncode == 1, "preflight must refuse work on main"
        out = json.loads(r.stdout)
        assert "not_protected_branch" in out["failed"]

        git("switch", "-qc", "feature", cwd=repo)
        r = run(PREFLIGHT, "--path", str(repo))
        assert r.returncode == 0, r.stdout
        assert json.loads(r.stdout)["safe"] is True


def test_preflight_flags_dirty_tree_and_detached_head():
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d) / "r"
        repo.mkdir()
        make_repo(repo, "feature")

        (repo / "f.txt").write_text("changed")
        out = json.loads(run(PREFLIGHT, "--path", str(repo)).stdout)
        assert "clean_tree" in out["failed"]

        git("checkout", "-q", "--", "f.txt", cwd=repo)
        sha = git("rev-parse", "HEAD", cwd=repo).stdout.strip()
        git("checkout", "-q", sha, cwd=repo)
        out = json.loads(run(PREFLIGHT, "--path", str(repo)).stdout)
        assert "on_branch" in out["failed"]


def test_preflight_outside_a_repo_exits_2():
    with tempfile.TemporaryDirectory() as d:
        r = run(PREFLIGHT, "--path", d)
        assert r.returncode == 2


def test_preflight_plain_format():
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d) / "r"
        repo.mkdir()
        make_repo(repo, "main")
        r = run(PREFLIGHT, "--path", str(repo), "--format", "plain")
        assert "NOT SAFE" in r.stdout
        assert "git switch -c" in r.stdout
