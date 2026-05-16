"""Tests for roll-dice skill."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = str(ROOT / "roll-dice" / "scripts" / "roll.py")


def run(args):
    return subprocess.run([sys.executable, SCRIPT] + args, capture_output=True, text=True)


def test_default_roll():
    r = run([])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["sides"] == 6
    assert data["rolls"] == 1
    assert len(data["results"]) == 1
    assert 1 <= data["results"][0] <= 6


def test_custom_sides():
    r = run(["--sides", "20"])
    data = json.loads(r.stdout)
    assert data["sides"] == 20
    assert 1 <= data["results"][0] <= 20


def test_multiple_rolls():
    r = run(["--rolls", "5"])
    data = json.loads(r.stdout)
    assert len(data["results"]) == 5
    assert data["total"] == sum(data["results"])
    assert all(1 <= v <= 6 for v in data["results"])


def test_invalid_sides():
    r = run(["--sides", "0"])
    assert r.returncode != 0
    assert "at least 1" in r.stderr


def test_invalid_rolls():
    r = run(["--rolls", "0"])
    assert r.returncode != 0
    assert "at least 1" in r.stderr


def test_help():
    r = run(["--help"])
    assert r.returncode == 0
    assert "Roll dice" in r.stdout
