"""Tests for test-playwright skill."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = str(ROOT / "test-playwright" / "scripts" / "playwright.sh")


def run(args):
    return subprocess.run(["bash", SCRIPT] + args, capture_output=True, text=True)


def test_help():
    r = run(["help"])
    assert r.returncode == 0
    assert "playwright.sh" in r.stdout
    assert "init" in r.stdout
    assert "run" in r.stdout


def test_no_args_shows_usage():
    r = run([])
    assert r.returncode == 0
    assert "playwright.sh" in r.stdout


def test_unknown_command():
    r = run(["badcommand"])
    assert r.returncode != 0
    assert "Unknown command" in r.stderr


def test_create_no_name():
    r = run(["create"])
    assert r.returncode != 0
    assert "Usage" in r.stderr
