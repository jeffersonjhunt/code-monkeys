"""Tests for img-sixel skill."""

import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = str(ROOT / "img-sixel" / "scripts" / "sixel.sh")


def run(args, env_override=None):
    import os
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
    return subprocess.run(["bash", SCRIPT] + args, capture_output=True, text=True, env=env)


def test_help():
    r = run(["help"])
    assert r.returncode == 0
    assert "sixel.sh" in r.stdout
    assert "display" in r.stdout


def test_no_args_shows_usage():
    r = run([])
    assert r.returncode == 0
    assert "sixel.sh" in r.stdout


def test_display_missing_file():
    # Use a PATH that includes img2sixel (or skip if not available)
    r = run(["display", "/nonexistent/file.png"])
    # Either fails on missing deps or missing file
    assert r.returncode != 0
    assert "Error" in r.stderr


def test_convert_missing_file():
    r = run(["convert", "/nonexistent/file.sixel"])
    assert r.returncode != 0
    assert "Error" in r.stderr


def test_unknown_command():
    r = run(["badcommand"])
    assert r.returncode != 0
    assert "Error" in r.stderr
