"""Tests for althingi skill."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ALTHINGI = str(ROOT / "althingi" / "scripts" / "althingi.py")
VOICES = str(ROOT / "althingi" / "scripts" / "voices.py")


def run(script, args, input_data=None):
    return subprocess.run(
        [sys.executable, script] + args,
        capture_output=True, text=True, input=input_data
    )


@pytest.fixture
def state_file(tmp_path):
    return str(tmp_path / "state.json")


# --- voices.py tests ---

def test_voices_help():
    r = run(VOICES, ["--help"])
    assert r.returncode == 0


def test_voices_list():
    r = run(VOICES, ["list"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert isinstance(data, list)
    assert len(data) >= 6
    ids = [v["id"] for v in data]
    assert "architect" in ids
    assert "skeptic" in ids


def test_voices_show():
    r = run(VOICES, ["show", "architect"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["id"] == "architect"
    assert "perspective" in data
    assert "style" in data
    assert "biases" in data


def test_voices_show_unknown():
    r = run(VOICES, ["show", "nonexistent"])
    assert r.returncode != 0
    assert "unknown voice" in r.stderr


def test_voices_suggest():
    r = run(VOICES, ["suggest", "--topic", "API security design"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "security" in data["suggested_voices"]


def test_voices_suggest_default():
    r = run(VOICES, ["suggest", "--topic", "something random"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    # Default set when no keywords match
    assert "architect" in data["suggested_voices"]


# --- althingi.py tests ---

def test_althingi_help():
    r = run(ALTHINGI, ["--help"])
    assert r.returncode == 0


def test_althingi_init(state_file):
    r = run(ALTHINGI, ["init", "--topic", "Test topic", "--voices", "architect,skeptic", "--state", state_file])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["topic"] == "Test topic"
    assert data["voices"] == ["architect", "skeptic"]
    assert data["mode"] == "subagent"


def test_althingi_init_solo(state_file):
    r = run(ALTHINGI, ["init", "--topic", "Test", "--voices", "architect,skeptic", "--solo", "--state", state_file])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["mode"] == "solo"


def test_althingi_init_invalid_voice(state_file):
    r = run(ALTHINGI, ["init", "--topic", "Test", "--voices", "bogus", "--state", state_file])
    assert r.returncode != 0
    assert "unknown voice" in r.stderr


def test_althingi_next(state_file):
    run(ALTHINGI, ["init", "--topic", "Microservices?", "--voices", "architect,skeptic", "--rounds", "1", "--state", state_file])
    r = run(ALTHINGI, ["next", "--state", state_file])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["result"] == "next"
    assert data["voice"] == "architect"
    assert data["round"] == 1
    assert "persona" in data


def test_althingi_record(state_file):
    run(ALTHINGI, ["init", "--topic", "Test", "--voices", "architect,skeptic", "--rounds", "1", "--state", state_file])
    r = run(ALTHINGI, ["record", "--voice", "architect", "--state", state_file], input_data="I think we should use a modular approach.")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["recorded"] == "architect"


def test_althingi_record_empty(state_file):
    run(ALTHINGI, ["init", "--topic", "Test", "--voices", "architect", "--rounds", "1", "--state", state_file])
    r = run(ALTHINGI, ["record", "--voice", "architect", "--state", state_file], input_data="")
    assert r.returncode != 0
    assert "empty response" in r.stderr


def test_althingi_status(state_file):
    run(ALTHINGI, ["init", "--topic", "Test", "--voices", "architect,skeptic", "--rounds", "2", "--state", state_file])
    r = run(ALTHINGI, ["status", "--state", state_file])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["turns_total"] == 4
    assert data["turns_completed"] == 0


def test_althingi_transcript_json(state_file):
    run(ALTHINGI, ["init", "--topic", "Test", "--voices", "architect", "--rounds", "1", "--state", state_file])
    run(ALTHINGI, ["record", "--voice", "architect", "--state", state_file], input_data="My response.")
    r = run(ALTHINGI, ["transcript", "--state", state_file, "--format", "json"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["topic"] == "Test"
    assert len(data["transcript"]) == 1


def test_althingi_transcript_markdown(state_file):
    run(ALTHINGI, ["init", "--topic", "Test", "--voices", "architect", "--rounds", "1", "--state", state_file])
    run(ALTHINGI, ["record", "--voice", "architect", "--state", state_file], input_data="My response.")
    r = run(ALTHINGI, ["transcript", "--state", state_file, "--format", "markdown"])
    assert r.returncode == 0
    assert "# Roundtable: Test" in r.stdout
    assert "The Architect" in r.stdout


def test_althingi_completion(state_file):
    """Full lifecycle: init → record all turns → complete."""
    run(ALTHINGI, ["init", "--topic", "Test", "--voices", "architect,skeptic", "--rounds", "1", "--state", state_file])
    run(ALTHINGI, ["record", "--voice", "architect", "--state", state_file], input_data="Architect speaks.")
    run(ALTHINGI, ["record", "--voice", "skeptic", "--state", state_file], input_data="Skeptic speaks.")

    r = run(ALTHINGI, ["next", "--state", state_file])
    data = json.loads(r.stdout)
    assert data["result"] == "complete"


def test_althingi_context_accumulates(state_file):
    """Verify that next includes prior responses in context."""
    run(ALTHINGI, ["init", "--topic", "Test", "--voices", "architect,skeptic", "--rounds", "1", "--state", state_file])
    run(ALTHINGI, ["record", "--voice", "architect", "--state", state_file], input_data="Modular is best.")

    r = run(ALTHINGI, ["next", "--state", state_file])
    data = json.loads(r.stdout)
    assert "Modular is best." in data["context"]
