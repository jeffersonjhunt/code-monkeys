"""Tests for scripts/skill-meta.py — frontmatter reader used by `make test`."""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_META = str(ROOT / "scripts" / "skill-meta.py")

FRONTMATTER = """---
name: demo
description: A demo skill
license: Apache-2.0
metadata:
  author: someone
  version: "2.1"
  runtime: container:demo-box
---

# demo
Body text with a decoy line that must not be parsed:
runtime: not-this-one
"""


def run(*args):
    return subprocess.run([sys.executable, SKILL_META, *args], capture_output=True, text=True)


def write(tmp: Path, text: str) -> str:
    p = tmp / "SKILL.md"
    p.write_text(text)
    return str(p)


def test_help():
    r = run("--help")
    assert r.returncode == 0
    assert "usage" in r.stdout.lower()


def test_reads_top_level_and_nested_keys():
    with tempfile.TemporaryDirectory() as d:
        f = write(Path(d), FRONTMATTER)
        assert run(f, "name").stdout.strip() == "demo"
        assert run(f, "metadata.version").stdout.strip() == "2.1"
        assert run(f, "metadata.runtime").stdout.strip() == "container:demo-box"


def test_body_text_is_not_parsed_as_frontmatter():
    """The decoy `runtime:` in the body must not win over the real one."""
    with tempfile.TemporaryDirectory() as d:
        f = write(Path(d), FRONTMATTER)
        assert run(f, "runtime").stdout.strip() == ""


def test_absent_key_is_empty_and_exit_zero():
    """Absent is an answer, not an error — `make test` relies on this."""
    with tempfile.TemporaryDirectory() as d:
        f = write(Path(d), FRONTMATTER)
        r = run(f, "metadata.nope")
        assert r.returncode == 0
        assert r.stdout.strip() == ""


def test_skill_without_runtime_reports_nothing():
    with tempfile.TemporaryDirectory() as d:
        f = write(Path(d), "---\nname: plain\ndescription: d\nmetadata:\n  author: x\n---\n")
        r = run(f, "metadata.runtime")
        assert r.returncode == 0 and r.stdout.strip() == ""


def test_missing_file_is_an_error():
    r = run("/nonexistent/SKILL.md", "name")
    assert r.returncode == 1
    assert "no such file" in r.stderr.lower()


def test_real_spark_bench_declares_a_runtime():
    """The regression this was built for: spark-bench must stay declared."""
    f = str(ROOT / "spark-bench" / "SKILL.md")
    assert run(f, "metadata.runtime").stdout.strip() == "container:spark-bench"
