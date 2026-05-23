"""Tests for spark-build skill.

Most tests require spark/cluster/cluster.env to exist (gitignored, but present on
the maintainer's workstation). They skip cleanly when it's not.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = str(ROOT / "spark-build" / "scripts" / "spark-build")
CLUSTER_ENV = ROOT.parent.parent / "spark" / "cluster" / "cluster.env"


def run(args):
    return subprocess.run([SCRIPT, *args], capture_output=True, text=True)


def _load_cluster_env():
    if not CLUSTER_ENV.exists():
        return {}
    env = {}
    for line in CLUSTER_ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


CFG = _load_cluster_env()
needs_env = pytest.mark.skipif(not CFG, reason="spark/cluster/cluster.env not present")


def test_help():
    r = run(["--help"])
    assert r.returncode == 0
    assert "Usage:" in r.stdout
    assert "--host" in r.stdout
    assert "--image" in r.stdout
    assert "--dry-run" in r.stdout


def test_unknown_arg_errors():
    r = run(["--bogus"])
    assert r.returncode != 0
    assert "unknown arg" in r.stderr


def test_invalid_sync_mode_errors():
    r = run(["--sync", "smb"])
    assert r.returncode != 0
    assert "--sync must be" in r.stderr


@needs_env
def test_unknown_image_errors():
    r = run(["--host", "hutch.tworivers", "--image", "nope", "--dry-run"])
    assert r.returncode != 0
    assert "unknown image" in r.stderr


@needs_env
def test_dry_run_default_plans_all_three_images():
    r = run(["--host", "hutch.tworivers", "--dry-run"])
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "Plan:" in out
    assert "Pre-flight on" in out
    assert "Draining" in out
    assert "rsync" in out
    assert "Building llama-cpp-spark" in out
    assert "Building comfy-ui-spark" in out
    assert "Building vllm-spark" in out
    assert "Restarting vLLM" in out
    assert "Done." in out


@needs_env
def test_dry_run_single_image_only_plans_that_image():
    r = run(["--host", "hutch.tworivers", "--image", "vllm-spark", "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert "Building vllm-spark" in r.stdout
    assert "Building llama-cpp-spark" not in r.stdout
    assert "Building comfy-ui-spark" not in r.stdout


@needs_env
def test_dry_run_skip_drain_and_no_restart():
    r = run([
        "--host", "hutch.tworivers", "--dry-run",
        "--skip-drain", "--no-restart",
    ])
    assert r.returncode == 0, r.stderr
    assert "Draining" not in r.stdout
    assert "Restarting vLLM" not in r.stdout


@needs_env
def test_lb_host_requires_force():
    lb_host = CFG.get("LB_HOST")
    assert lb_host, "cluster.env missing LB_HOST"
    r = run(["--host", lb_host, "--dry-run"])
    assert r.returncode != 0
    assert "LB_HOST" in r.stderr
    assert "--force" in r.stderr


@needs_env
def test_lb_host_with_force_allowed():
    lb_host = CFG.get("LB_HOST")
    assert lb_host, "cluster.env missing LB_HOST"
    r = run(["--host", lb_host, "--dry-run", "--force"])
    assert r.returncode == 0, r.stderr
    assert "Plan:" in r.stdout


@needs_env
def test_lb_host_auto_fqdn_from_host_suffix():
    # --host hutch.tworivers + bare LB_HOST=starsky → LB_TARGET=starsky.tworivers
    r = run(["--host", "hutch.tworivers", "--dry-run"])
    assert r.returncode == 0, r.stderr
    lb_host = CFG.get("LB_HOST")
    assert lb_host, "cluster.env missing LB_HOST"
    assert f"LB host    : jhunt@{lb_host}.tworivers" in r.stdout


@needs_env
def test_lb_host_explicit_override():
    r = run([
        "--host", "hutch.tworivers", "--dry-run",
        "--lb-host", "explicit.example.com",
    ])
    assert r.returncode == 0, r.stderr
    assert "LB host    : jhunt@explicit.example.com" in r.stdout


@needs_env
def test_lb_host_bare_when_host_is_bare():
    # --host hutch (bare) → LB_TARGET stays bare (from cluster.env)
    r = run(["--host", "hutch", "--dry-run"])
    assert r.returncode == 0, r.stderr
    lb_host = CFG.get("LB_HOST")
    assert f"LB host    : jhunt@{lb_host}\n" in r.stdout or f"LB host    : jhunt@{lb_host} " in r.stdout


@needs_env
def test_git_sync_uses_current_branch_by_default():
    r = run(["--host", "hutch.tworivers", "--sync", "git", "--dry-run"])
    assert r.returncode == 0, r.stderr
    # commands are printed with printf %q escaping, so spaces appear as "\ "
    assert "sync       : git" in r.stdout
    assert "fetch" in r.stdout
    assert "checkout" in r.stdout
    assert "--ff-only" in r.stdout
