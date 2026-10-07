"""Black-box tests for the secret-ops script.

These exercise only the offline paths — --help, argument validation, and the "config missing"
guard — all of which run before any ssh, so the suite needs no secret host and no network.
(Encryption itself lives in `vault seal`, tested with vault, not here.)
"""
import os
import subprocess
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "secret-ops" / "scripts"


def run(script, *args, env=None):
    e = dict(os.environ)
    # Guarantee no ambient config leaks in: point at a non-existent conf, drop any host/user.
    e["SECRET_OPS_CONF"] = "/nonexistent/secret-ops.conf"
    e.pop("SECRET_HOST", None)
    e.pop("SECRET_USER", None)
    if env:
        e.update(env)
    return subprocess.run(
        ["bash", str(SCRIPTS / script), *args],
        capture_output=True, text=True, env=e, timeout=30,
    )


def test_secret_host_help():
    r = run("secret-host.sh", "--help")
    assert r.returncode == 0
    assert "usage" in r.stderr.lower()


def test_secret_host_no_args_errors():
    r = run("secret-host.sh")
    assert r.returncode != 0


def test_secret_host_cwd_needs_a_dir():
    r = run("secret-host.sh", "--cwd")
    assert r.returncode != 0


def test_secret_host_requires_config():
    # A real command, but no SECRET_HOST configured -> must fail before ssh with guidance.
    r = run("secret-host.sh", "echo hi")
    assert r.returncode != 0
    assert "SECRET_HOST" in r.stderr
