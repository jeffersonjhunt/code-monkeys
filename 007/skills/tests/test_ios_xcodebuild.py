"""Tests for ios-xcodebuild skill.

The build/run scripts need a reachable macOS host, so these tests only cover
what is verifiable locally: --help output, argument and environment validation
(which happens before any SSH call), and the project scaffold that
ios-bootstrap.sh produces.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "ios-xcodebuild" / "scripts"
BOOTSTRAP = str(SCRIPTS / "ios-bootstrap.sh")
BUILD = str(SCRIPTS / "ios-build.sh")
RUN = str(SCRIPTS / "ios-run.sh")

ALL_SCRIPTS = [BOOTSTRAP, BUILD, RUN]


def run(script, args=None, cwd=None, env=None):
    return subprocess.run(
        [script, *(args or [])], capture_output=True, text=True, cwd=cwd, env=env
    )


# --- syntax + conventions -------------------------------------------------


def test_scripts_are_valid_bash():
    for script in ALL_SCRIPTS:
        r = subprocess.run(["bash", "-n", script], capture_output=True, text=True)
        assert r.returncode == 0, f"{script}: {r.stderr}"


def test_scripts_use_strict_mode():
    for script in ALL_SCRIPTS:
        assert "set -euo pipefail" in Path(script).read_text()


def test_no_script_disables_host_key_checking():
    """Host key verification must stay on, including in the generated scripts."""
    for script in ALL_SCRIPTS:
        assert "StrictHostKeyChecking=no" not in Path(script).read_text()


# --- --help ---------------------------------------------------------------


def test_help_on_all_scripts():
    for script in ALL_SCRIPTS:
        for flag in ("-h", "--help"):
            r = run(script, [flag])
            assert r.returncode == 0, f"{script} {flag}: {r.stderr}"
            assert "Usage:" in r.stdout


def test_help_does_not_scaffold(tmp_path):
    """--help must not be mistaken for an app name."""
    r = run(BOOTSTRAP, ["--help"], cwd=tmp_path)
    assert r.returncode == 0
    assert list(tmp_path.iterdir()) == []


def test_help_documents_known_hosts_bootstrap():
    for script in (BUILD, RUN):
        r = run(script, ["--help"])
        assert "ssh-keyscan" in r.stdout


# --- argument / environment validation -----------------------------------


def test_bootstrap_requires_app_name(tmp_path):
    r = run(BOOTSTRAP, [], cwd=tmp_path)
    assert r.returncode == 1
    assert "Usage:" in r.stderr


def test_bootstrap_refuses_existing_directory(tmp_path):
    (tmp_path / "MyApp").mkdir()
    r = run(BOOTSTRAP, ["MyApp"], cwd=tmp_path)
    assert r.returncode == 1
    assert "already exists" in r.stderr


def test_build_requires_host_project_path(tmp_path):
    env = {"PATH": "/usr/bin:/bin"}
    r = run(BUILD, ["simulator"], cwd=tmp_path, env=env)
    assert r.returncode != 0
    assert "HOST_PROJECT_PATH" in r.stderr


def test_build_rejects_bad_target(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "HOST_PROJECT_PATH": "/tmp/x"}
    r = run(BUILD, ["emulator"], cwd=tmp_path, env=env)
    assert r.returncode != 0
    assert "simulator" in r.stderr


def test_build_rejects_bad_config(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "HOST_PROJECT_PATH": "/tmp/x"}
    r = run(BUILD, ["simulator", "profile"], cwd=tmp_path, env=env)
    assert r.returncode != 0
    assert "debug" in r.stderr


def test_build_device_requires_team_id(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "HOST_PROJECT_PATH": "/tmp/x"}
    r = run(BUILD, ["device"], cwd=tmp_path, env=env)
    assert r.returncode != 0
    assert "TEAM_ID" in r.stderr


def test_run_requires_host_project_path(tmp_path):
    env = {"PATH": "/usr/bin:/bin"}
    r = run(RUN, ["simulator"], cwd=tmp_path, env=env)
    assert r.returncode != 0
    assert "HOST_PROJECT_PATH" in r.stderr


# --- scaffold ------------------------------------------------------------


def test_bootstrap_scaffolds_project(tmp_path):
    r = run(BOOTSTRAP, ["MyApp"], cwd=tmp_path)
    assert r.returncode == 0, r.stderr

    project = tmp_path / "MyApp"
    expected = [
        "Package.swift",
        "Sources/MyApp/MyAppApp.swift",
        "Sources/MyApp/ContentView.swift",
        "Resources/Info.plist",
        "scripts/build.sh",
        "scripts/run.sh",
        ".gitignore",
    ]
    for rel in expected:
        assert (project / rel).is_file(), f"missing {rel}"

    for rel in ("scripts/build.sh", "scripts/run.sh"):
        path = project / rel
        assert path.stat().st_mode & 0o111, f"{rel} not executable"
        text = path.read_text()
        assert "set -euo pipefail" in text
        assert "StrictHostKeyChecking=no" not in text
        assert "ssh-keyscan" in text

    package = (project / "Package.swift").read_text()
    assert ".executableTarget" in package
    assert 'name: "MyApp"' in package


def test_bootstrap_default_bundle_id_is_lowercased(tmp_path):
    r = run(BOOTSTRAP, ["MyApp"], cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "com.example.myapp" in r.stdout


def test_bootstrap_accepts_explicit_bundle_id(tmp_path):
    r = run(BOOTSTRAP, ["MyApp", "com.acme.thing"], cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "com.acme.thing" in r.stdout


def test_generated_scripts_support_help(tmp_path):
    assert run(BOOTSTRAP, ["MyApp"], cwd=tmp_path).returncode == 0
    for rel in ("scripts/build.sh", "scripts/run.sh"):
        r = run(str(tmp_path / "MyApp" / rel), ["--help"])
        assert r.returncode == 0, r.stderr
        assert "Usage:" in r.stdout
