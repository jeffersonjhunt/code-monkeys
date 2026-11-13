"""Tests for the craft-build skill's craft-all.sh.

Pure logic only — manifest parse -> clone plan, app discovery, the --list dry run, and arg
handling — driven against a FIXTURE workspace tree in tmp_path. No network, no cargo, no real
packaging, so every test runs everywhere with nothing conditional.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = str(ROOT / "craft-build" / "scripts" / "craft-all.sh")


def run(*args):
    return subprocess.run(["bash", SCRIPT, *args], capture_output=True, text=True)


def make_app(root: Path, name: str, version: str) -> None:
    """A dir that discovery must find: has packaging/macos/package.sh + a workspace version."""
    d = root / name
    (d / "packaging" / "macos").mkdir(parents=True)
    (d / "packaging" / "macos" / "package.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
    (d / "Cargo.toml").write_text(f'[workspace.package]\nversion = "{version}"\n')
    (d / ".git").mkdir()  # make it look cloned, so the manifest won't re-plan it


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "Craft"
    root.mkdir()
    make_app(root, "appone", "1.2.3")
    make_app(root, "apptwo", "0.9.0")
    # a sibling that is NOT an app (no packaging/macos/package.sh) must be ignored
    (root / "notanapp").mkdir()
    (root / "notanapp" / "README.md").write_text("not a buildable app\n")
    # manifest: appone present, appthree missing -> only appthree should be in the clone plan
    (root / "craft.manifest").write_text(
        "# name = remote\n"
        "appone    = git@example.com:org/appone.git\n"
        "appthree  = git@example.com:other/appthree.git\n"
        "\n"
        "# a comment line and a blank above are ignored\n"
    )
    return root


# --- arg handling ----------------------------------------------------------------------


def test_help():
    r = run("--help")
    assert r.returncode == 0
    assert "Usage:" in r.stdout
    for flag in ("--root", "--manifest", "--arch", "--list"):
        assert flag in r.stdout


def test_unknown_arg_errors():
    r = run("--bogus")
    assert r.returncode == 2
    assert "unknown argument" in r.stderr


def test_missing_root_is_a_clear_error(tmp_path):
    r = run("--root", str(tmp_path / "absent"), "--list")
    assert r.returncode == 1
    assert "root not found" in r.stderr


# --- discovery + clone planning (the --list dry run) -----------------------------------


def test_list_discovers_apps_and_ignores_non_apps(tree):
    r = run("--root", str(tree), "--list")
    assert r.returncode == 0, r.stderr
    build = r.stdout.split("would build")[1]
    assert "appone" in build
    assert "apptwo" in build
    assert "notanapp" not in build


def test_list_clone_plan_only_names_missing_repos(tree):
    r = run("--root", str(tree), "--list")
    assert r.returncode == 0, r.stderr
    clone = r.stdout.split("would clone")[1].split("would build")[0]
    # appthree is in the manifest but not on disk -> planned; appone is present -> not planned
    assert "appthree <- git@example.com:other/appthree.git" in clone
    assert "appone <-" not in clone


def test_list_only_filters_the_app_set(tree):
    r = run("--root", str(tree), "--only", "appone", "--list")
    assert r.returncode == 0, r.stderr
    build = r.stdout.split("would build")[1]
    assert "appone" in build
    assert "apptwo" not in build


def test_list_reports_resolved_root_manifest_and_arch(tree):
    r = run("--root", str(tree), "--arch", "universal", "--list")
    assert r.returncode == 0, r.stderr
    assert f"root:     {tree}" in r.stdout
    assert "craft.manifest" in r.stdout
    assert "arch:     universal" in r.stdout


def test_list_does_no_build_and_writes_no_report(tree):
    r = run("--root", str(tree), "--list")
    assert r.returncode == 0, r.stderr
    assert not (tree / "craft-all.report.txt").exists()
