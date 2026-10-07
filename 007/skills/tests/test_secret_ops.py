"""Black-box tests for the secret-ops scripts.

These exercise only the offline paths — --help, argument validation, and the "config missing"
guard — all of which run before any ssh, so the suite needs no secret host and no network.
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


# --- secret-host.sh -------------------------------------------------------------------------

def test_secret_host_help():
    r = run("secret-host.sh", "--help")
    assert r.returncode == 0
    assert "usage" in r.stderr.lower()


def test_secret_host_no_args_errors():
    r = run("secret-host.sh")
    assert r.returncode != 0


def test_secret_host_requires_config():
    # A real command, but no SECRET_HOST configured -> must fail before ssh with guidance.
    r = run("secret-host.sh", "echo hi")
    assert r.returncode != 0
    assert "SECRET_HOST" in r.stderr


# --- sops-reencrypt.sh ----------------------------------------------------------------------

def test_reencrypt_help():
    r = run("sops-reencrypt.sh", "--help")
    assert r.returncode == 0
    assert "usage" in r.stderr.lower()


def test_reencrypt_missing_args():
    r = run("sops-reencrypt.sh", "only-one-arg")
    assert r.returncode != 0
    assert "need" in r.stderr.lower()


def test_reencrypt_target_must_be_sops():
    r = run("sops-reencrypt.sh", "/tmp/plain.json", "area/config.json")
    assert r.returncode != 0
    assert ".sops" in r.stderr


def test_reencrypt_requires_config():
    # Valid-looking args, but no SECRET_HOST -> fail before ssh.
    r = run("sops-reencrypt.sh", "/tmp/plain.json", "area/config.json.sops")
    assert r.returncode != 0
    assert "SECRET_HOST" in r.stderr
