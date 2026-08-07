"""Tests for the spark-build skill.

These used to be gated on the maintainer's local `spark/cluster/cluster.env`, which is GITIGNORED —
so they skipped in a fresh checkout or any worktree and ran on exactly one machine. Five assertions
went stale under that cover (the images were renamed `*-spark` -> `cuda-*`, and SSH_USER changed from
jhunt to gdeceiver) and nothing reported it, because wherever anyone looked the tests were skipping.

They now drive the script with a FIXTURE cluster.env via $SPARK_CLUSTER_ENV, so every test runs
everywhere and nothing is conditional. The fixture deliberately uses a BARE LB_HOST, which the real
config no longer has — that is the only way the auto-suffix rule is actually exercised.
"""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = str(ROOT / "spark-build" / "scripts" / "spark-build")

SSH_USER = "testuser"
LB_HOST = "lb"          # bare on purpose: exercises the FQDN-suffix rule
REPLICAS = "hutch starsky"

FIXTURE = f"""\
SSH_USER={SSH_USER}
REPLICAS="{REPLICAS}"
LB_HOST={LB_HOST}
VLLM_PORT=8000
LB_PORT=8080
"""


@pytest.fixture(scope="module")
def cluster_env():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "cluster.env"
        p.write_text(FIXTURE)
        yield str(p)


def run(args, cluster_env=None):
    env = dict(os.environ)
    if cluster_env:
        env["SPARK_CLUSTER_ENV"] = cluster_env
    return subprocess.run([SCRIPT, *args], capture_output=True, text=True, env=env)


# --- argument handling (no cluster.env needed) -----------------------------------------


def test_help():
    r = run(["--help"])
    assert r.returncode == 0
    assert "Usage:" in r.stdout
    for flag in ("--host", "--image", "--dry-run"):
        assert flag in r.stdout


def test_unknown_arg_errors():
    r = run(["--bogus"])
    assert r.returncode != 0
    assert "unknown arg" in r.stderr


def test_invalid_sync_mode_errors():
    r = run(["--sync", "smb"])
    assert r.returncode != 0
    assert "--sync must be" in r.stderr


def test_missing_cluster_env_is_a_clear_error(tmp_path):
    """The seam must not become a way to run with no config at all."""
    r = run(["--dry-run"], cluster_env=str(tmp_path / "absent.env"))
    assert r.returncode == 2
    assert "not found" in r.stderr


# --- planning --------------------------------------------------------------------------


def test_unknown_image_errors(cluster_env):
    r = run(["--host", "hutch.tworivers", "--image", "nope", "--dry-run"], cluster_env)
    assert r.returncode != 0
    assert "unknown image" in r.stderr


def test_dry_run_default_plans_all_three_images(cluster_env):
    r = run(["--host", "hutch.tworivers", "--dry-run"], cluster_env)
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "Plan:" in out
    assert "Pre-flight on" in out
    assert "Draining" in out
    assert "rsync" in out
    for img in ("cuda-llama-cpp", "cuda-comfy", "cuda-vllm"):
        assert f"Building {img}" in out


def test_dry_run_single_image_only_plans_that_image(cluster_env):
    r = run(["--host", "hutch.tworivers", "--image", "cuda-vllm", "--dry-run"], cluster_env)
    assert r.returncode == 0, r.stderr
    assert "Building cuda-vllm" in r.stdout
    assert "Building cuda-llama-cpp" not in r.stdout
    assert "Building cuda-comfy" not in r.stdout


def test_dry_run_skip_drain_and_no_restart(cluster_env):
    r = run(
        ["--host", "hutch.tworivers", "--dry-run", "--skip-drain", "--no-restart"],
        cluster_env,
    )
    assert r.returncode == 0, r.stderr
    assert "Draining" not in r.stdout
    assert "Restarting vLLM" not in r.stdout


def test_default_host_is_first_non_lb_replica(cluster_env):
    r = run(["--dry-run"], cluster_env)
    assert r.returncode == 0, r.stderr
    assert f"host       : {SSH_USER}@hutch" in r.stdout


# --- LB host protection and resolution -------------------------------------------------


def test_lb_host_requires_force(cluster_env):
    r = run(["--host", LB_HOST, "--dry-run"], cluster_env)
    assert r.returncode != 0
    assert "LB_HOST" in r.stderr
    assert "--force" in r.stderr


def test_lb_host_with_force_allowed(cluster_env):
    r = run(["--host", LB_HOST, "--dry-run", "--force"], cluster_env)
    assert r.returncode == 0, r.stderr
    assert "Plan:" in r.stdout


def test_lb_host_auto_fqdn_from_host_suffix(cluster_env):
    """--host hutch.tworivers + bare LB_HOST=lb -> LB_TARGET=lb.tworivers."""
    r = run(["--host", "hutch.tworivers", "--dry-run"], cluster_env)
    assert r.returncode == 0, r.stderr
    assert f"LB host    : {SSH_USER}@{LB_HOST}.tworivers" in r.stdout


def test_lb_host_explicit_override(cluster_env):
    r = run(
        ["--host", "hutch.tworivers", "--dry-run", "--lb-host", "explicit.example.com"],
        cluster_env,
    )
    assert r.returncode == 0, r.stderr
    assert f"LB host    : {SSH_USER}@explicit.example.com" in r.stdout


def test_lb_host_bare_when_host_is_bare(cluster_env):
    """--host hutch (bare) -> no suffix to borrow, so LB_TARGET stays bare."""
    r = run(["--host", "hutch", "--dry-run"], cluster_env)
    assert r.returncode == 0, r.stderr
    line = f"LB host    : {SSH_USER}@{LB_HOST}"
    assert f"{line}\n" in r.stdout or f"{line} " in r.stdout


# --- sync modes ------------------------------------------------------------------------


def test_git_sync_uses_current_branch_by_default(cluster_env):
    r = run(["--host", "hutch.tworivers", "--sync", "git", "--dry-run"], cluster_env)
    assert r.returncode == 0, r.stderr
    assert "sync       : git" in r.stdout
    for token in ("fetch", "checkout", "--ff-only"):
        assert token in r.stdout
