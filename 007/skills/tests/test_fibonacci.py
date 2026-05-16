"""Tests for math-fibonacci skill."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = str(ROOT / "math-fibonacci" / "scripts" / "fibonacci-generator.py")


def run(args):
    result = subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True, text=True
    )
    return result


def test_default_output():
    r = run([])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["start"] == 0
    assert data["count"] == 10
    assert data["values"] == [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]


def test_count():
    r = run(["--count", "5"])
    data = json.loads(r.stdout)
    assert data["values"] == [0, 1, 1, 2, 3]


def test_start_offset():
    r = run(["--start", "5", "--count", "3"])
    data = json.loads(r.stdout)
    assert data["start"] == 5
    assert data["values"] == [5, 8, 13]


def test_count_zero():
    r = run(["--count", "0"])
    data = json.loads(r.stdout)
    assert data["values"] == []


def test_negative_start_errors():
    r = run(["--start", "-1"])
    assert r.returncode != 0
    assert "non-negative" in r.stderr


def test_negative_count_errors():
    r = run(["--count", "-1"])
    assert r.returncode != 0
    assert "non-negative" in r.stderr


def test_help():
    r = run(["--help"])
    assert r.returncode == 0
    assert "Fibonacci" in r.stdout
