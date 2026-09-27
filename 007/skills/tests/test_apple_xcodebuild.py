"""Tests for the apple-xcodebuild skill.

The scripts drive a Mac over SSH. Here, a fake `ssh` (tests/fixtures/apple_xcodebuild/bin) runs
the remote bash script locally, against fake xcodebuild/xcrun/swift/… that behave as FAKE_* env
vars say — so the remote logic itself (exit-code propagation, parsing, launch checks) is tested,
not just argument handling. A fake `hostpath` maps every path to itself, and HOME is a temp dir so
the XcodeGen cache is isolated.
"""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "apple-xcodebuild"
SCRIPTS = SKILL / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "apple_xcodebuild"
FAKE_BIN = FIXTURES / "bin"
SIMCTL_JSON = FIXTURES / "simctl-devices.json"

ENTRY = ["xc-doctor.py", "xc-bootstrap.py", "xc-build.py", "xc-test.py", "xc-run.py", "xc-shot.py"]

sys.path.insert(0, str(SCRIPTS))
import xc_common as xc  # noqa: E402


# --- harness --------------------------------------------------------------------------------------


@pytest.fixture
def env(tmp_path):
    home = tmp_path / "home"
    state = tmp_path / "state"
    home.mkdir()
    state.mkdir()
    e = {
        "PATH": f"{FAKE_BIN}:/usr/bin:/bin",
        "HOME": str(home),
        "XC_HOST_USER": "tester",
        "FAKE_LOG": str(tmp_path / "calls.log"),
        "FAKE_STATE": str(state),
        "FAKE_SIMCTL_JSON": str(SIMCTL_JSON),
        "FAKE_PRODUCTS": str(tmp_path / "products"),
        "FAKE_GIT_SHA": xc.KNOWN_XCODEGEN["2.45.4"],
    }
    yield e
    pidf = state / "app.pid"
    if pidf.exists():
        try:
            os.kill(int(pidf.read_text()), signal.SIGTERM)
        except (OSError, ValueError):
            pass


def run(script, args=(), env=None, cwd=None, **extra_env):
    e = dict(env or {})
    e.update({k: str(v) for k, v in extra_env.items()})
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, text=True, env=e, cwd=cwd, timeout=120,
    )
    try:
        r.json = json.loads(r.stdout) if r.stdout.strip() else None
    except json.JSONDecodeError:
        r.json = None
    return r


def calls(env):
    p = Path(env["FAKE_LOG"])
    return p.read_text() if p.exists() else ""


@pytest.fixture
def project(tmp_path, env):
    """A scaffolded Demo project (both platforms)."""
    r = run("xc-bootstrap.py", ["Demo", "--bundle-id", "com.example.demo", "--dir", str(tmp_path / "Demo")],
            env=env)
    assert r.returncode == 0, r.stderr
    return tmp_path / "Demo"


# --- conventions ----------------------------------------------------------------------------------


def test_help_on_every_script():
    for s in ENTRY:
        r = subprocess.run([sys.executable, str(SCRIPTS / s), "--help"], capture_output=True, text=True)
        assert r.returncode == 0, f"{s}: {r.stderr}"
        assert "usage" in r.stdout.lower()


def test_host_key_checking_is_never_disabled():
    for f in SCRIPTS.glob("*.py"):
        assert "StrictHostKeyChecking" not in f.read_text(), f.name


def test_remote_scripts_avoid_bash4_features():
    """The Mac's /bin/bash is 3.2: no associative arrays, case-modifying expansions, mapfile, |&."""
    blocks = 0
    for f in SCRIPTS.glob("*.py"):
        for block in f.read_text().split('r"""')[1:]:
            body = block.split('"""')[0]
            blocks += 1
            for token in ("declare -A", "mapfile", "readarray", "|&", ",,}", "^^}"):
                assert token not in body, f"{f.name}: {token}"
    assert blocks >= 8, f"found only {blocks} remote scripts — the scan is not looking at them"


# --- the regression this skill exists for -------------------------------------------------------------


def test_failed_xcodebuild_is_reported_as_failure(project, env):
    r = run("xc-build.py", ["--platform", "macos"], env=env, cwd=project,
            FAKE_XCODEBUILD_RC=65,
            FAKE_BUILD_OUTPUT="/src/Demo/ContentView.swift:7:5: error: cannot find 'x' in scope")
    assert r.returncode == 1, r.stderr
    res = r.json["results"][0]
    assert r.json["ok"] is False
    assert res["ok"] is False and res["xcodebuild_rc"] == 65
    assert res["errors"] == 1
    assert "ContentView.swift:7: cannot find 'x' in scope" in res["error_samples"]
    assert not (project / "build" / "xc" / "build-macos.json").exists(), "a failed build must not be recorded"


def test_successful_build_records_the_exact_app(project, env):
    r = run("xc-build.py", ["--platform", "macos"], env=env, cwd=project)
    assert r.returncode == 0, r.stderr
    state = json.loads((project / "build" / "xc" / "build-macos.json").read_text())
    assert state["app"] == f"{env['FAKE_PRODUCTS']}/Demo.app"
    assert state["bundle_id"] == "com.example.demo"
    assert state["signing"] == "adhoc"
    assert Path(state["log"]).is_file()


def test_platform_all_builds_what_the_scheme_supports(project, env):
    r = run("xc-build.py", env=env, cwd=project)
    assert r.returncode == 0, r.stderr
    assert [x["platform"] for x in r.json["results"]] == ["ios-sim", "macos"]
    r = run("xc-build.py", env=env, cwd=project, FAKE_SUPPORTED="macosx")
    assert [x["platform"] for x in r.json["results"]] == ["macos"]


def test_build_passes_extra_settings_and_adhoc(project, env):
    (project / ".devteam").write_text("ABCDE12345\n")
    r = run("xc-build.py", ["--platform", "macos", "--adhoc", "--setting", "NDI_SDK=/Library/NDI SDK"],
            env=env, cwd=project)
    assert r.returncode == 0, r.stderr
    assert r.json["results"][0]["signing"] == "adhoc"
    log = calls(env)
    assert "NDI_SDK=/Library/NDI SDK" in log
    assert "DEVELOPMENT_TEAM=ABCDE12345" not in log


def test_old_logs_are_pruned(project, env):
    logs = project / "build" / "logs"
    logs.mkdir(parents=True)
    for i in range(12):
        (logs / f"20000101-0000{i:02d}-build-macos.log").write_text("old")
    (logs / "20000101-000000-test-macos.log").write_text("other kind: untouched")
    assert run("xc-build.py", ["--platform", "macos"], env=env, cwd=project).returncode == 0
    kept = sorted(p.name for p in logs.glob("*-build-macos.log"))
    assert len(kept) == 10
    assert "20000101-000000-build-macos.log" not in kept and not kept[-1].startswith("2000")
    assert (logs / "20000101-000000-test-macos.log").exists()


def test_xc_test_supports_adhoc_and_settings(project, env):
    (project / ".devteam").write_text("ABCDE12345")
    r = run("xc-test.py", ["--platform", "macos", "--adhoc", "--setting", "NDI_SDK=/x y"],
            env=env, cwd=project, FAKE_TEST_SUMMARY=summary(1, 1))
    assert r.returncode == 0, r.stderr
    log = calls(env)
    assert "NDI_SDK=/x y" in log and "DEVELOPMENT_TEAM=ABCDE12345" not in log
    r = run("xc-test.py", ["--setting", "bad"], env=env, cwd=project)
    assert r.returncode == 1 and "KEY=VALUE" in r.json["error"]


def test_remote_exit_255_is_the_scripts_not_ssh(monkeypatch, env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    r = xc.remote("echo hi >&2; exit 255")
    assert r.returncode == 255
    assert r.stderr.strip() == "hi", "the sentinel must be stripped from stderr"
    monkeypatch.setenv("FAKE_SSH_RC", "255")
    with pytest.raises(xc.XcError, match="ssh to"):
        xc.remote("true")


def test_bad_setting_is_rejected(project, env):
    r = run("xc-build.py", ["--setting", "NOEQUALS"], env=env, cwd=project)
    assert r.returncode == 1 and "KEY=VALUE" in r.json["error"]


def test_unreachable_mac_is_an_environment_error_with_a_fix(project, env):
    r = run("xc-build.py", env=env, cwd=project,
            FAKE_SSH_RC=255, FAKE_SSH_STDERR="Host key verification failed.")
    assert r.returncode == 2
    assert "ssh-keyscan" in r.json["fix"]


# --- xcodegen cache ---------------------------------------------------------------------------------


def test_xcodegen_is_built_once_then_cached(project, env):
    run("xc-build.py", ["--platform", "macos"], env=env, cwd=project)
    first = calls(env)
    assert first.count("git clone") == 1
    assert "--branch 2.45.4" in first
    assert (project / "Demo.xcodeproj").is_dir(), "generate should have produced the project"
    wrapper = Path(env["HOME"]) / xc.xcodegen_rel("2.45.4", xc.KNOWN_XCODEGEN["2.45.4"])
    assert wrapper.is_file() and os.access(wrapper, os.X_OK)
    run("xc-build.py", ["--platform", "macos"], env=env, cwd=project)
    assert calls(env).count("git clone") == 1, "second build must reuse the cache"


def test_xcodegen_version_is_pinned_per_project(project, env):
    (project / ".xcodegen-version").write_text("2.46.0\n")
    r = run("xc-build.py", ["--platform", "macos"], env=env, cwd=project,
            FAKE_GIT_SHA=xc.KNOWN_XCODEGEN["2.46.0"])
    assert r.returncode == 0, r.stderr
    assert "--branch 2.46.0" in calls(env)
    (project / ".xcodegen-version").write_text("latest\n")
    r = run("xc-build.py", ["--platform", "macos"], env=env, cwd=project)
    assert r.returncode == 1 and "xcodegen-version" in r.json["error"]


def test_xcodegen_moved_tag_is_refused_and_not_cached(project, env):
    """A tag that no longer points at the pinned commit must not be built or executed."""
    r = run("xc-build.py", ["--platform", "macos"], env=env, cwd=project, FAKE_GIT_SHA="d" * 40)
    assert r.returncode == 1
    assert "refusing to build" in r.json["error"]
    assert "swift build" not in calls(env)
    assert not (Path(env["HOME"]) / xc.xcodegen_rel("2.45.4", xc.KNOWN_XCODEGEN["2.45.4"])).exists()


def test_xcodegen_unknown_version_needs_a_commit(project, env):
    (project / ".xcodegen-version").write_text("2.47.0\n")
    r = run("xc-build.py", ["--platform", "macos"], env=env, cwd=project)
    assert r.returncode == 1 and "no known commit" in r.json["error"]
    assert "git ls-remote" in r.json["fix"]
    sha = "a" * 40
    (project / ".xcodegen-version").write_text(f"2.47.0@{sha}\n")
    r = run("xc-build.py", ["--platform", "macos"], env=env, cwd=project, FAKE_GIT_SHA=sha)
    assert r.returncode == 0, r.stderr
    (project / ".xcodegen-version").write_text(f"2.45.4@{sha}\n")
    r = run("xc-build.py", ["--platform", "macos"], env=env, cwd=project)
    assert r.returncode == 1 and "known commit" in r.json["error"]


# --- doctor ------------------------------------------------------------------------------------------


def statuses(r):
    return {c["check"]: c["status"] for c in r.json["checks"]}


def test_doctor_all_green(project, env):
    r = run("xc-doctor.py", env=env, cwd=project)
    assert r.returncode == 0, r.stderr
    s = statuses(r)
    assert s["first-launch"] == "ok" and s["simulator"] == "ok" and s["project-path"] == "ok"
    assert s["codesign"] == "ok"
    assert s["xcodegen"] == "warn"  # not built yet: a warning with a fix, not a failure


def test_doctor_flags_missing_first_launch(project, env):
    r = run("xc-doctor.py", env=env, cwd=project, FAKE_FIRSTLAUNCH_RC=69)
    assert r.returncode == 1
    c = next(c for c in r.json["checks"] if c["check"] == "first-launch")
    assert c["status"] == "fail" and "runFirstLaunch" in c["fix"]


def test_doctor_flags_no_simulators(project, env, tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text('{"devices": {}}')
    r = run("xc-doctor.py", env=env, cwd=project, FAKE_SIMCTL_JSON=empty)
    assert r.returncode == 1
    assert statuses(r)["simulator"] == "fail"


def test_doctor_flags_codesign_unusable_over_ssh(project, env):
    (project / ".devteam").write_text("ABCDE12345")
    r = run("xc-doctor.py", ["--platform", "macos"], env=env, cwd=project,
            FAKE_CODESIGN_RC=1, FAKE_CODESIGN_OUT="probe: errSecInternalComponent")
    assert r.returncode == 1
    c = next(c for c in r.json["checks"] if c["check"] == "codesign")
    assert c["status"] == "fail" and "--adhoc" in c["fix"]


@pytest.mark.parametrize("content,expect", [
    ("9.9.9", "no known commit"),              # unknown version, no commit to verify against
    ("latest", "expected 2.45.4"),             # malformed
    (f"2.45.4@{'a' * 40}", "known commit"),    # pin contradicts the known commit
])
def test_doctor_reports_bad_xcodegen_version_and_keeps_checking(project, env, content, expect):
    """One bad line in .xcodegen-version must not hide every other check."""
    (project / ".xcodegen-version").write_text(content + "\n")
    r = run("xc-doctor.py", env=env, cwd=project)
    assert r.returncode == 1
    assert r.json and "checks" in r.json, "the doctor aborted instead of reporting"
    c = next(c for c in r.json["checks"] if c["check"] == "xcodegen")
    assert c["status"] == "fail" and expect in c["detail"]
    s = statuses(r)
    for other in ("ssh", "first-launch", "simulator", "project-path", "codesign", "screen-recording"):
        assert s[other] == "ok", f"{other} should still have been checked"


def test_doctor_flags_project_not_visible_on_the_mac(project, env, tmp_path):
    r = run("xc-doctor.py", env=env, cwd=project,
            HOST_PROJECT_PATH="/nonexistent/Demo", HOST_PROJECT_ROOT=project)
    assert r.returncode == 1
    assert statuses(r)["project-path"] == "fail"


# --- test -------------------------------------------------------------------------------------------


def summary(total, passed, failed=0, skipped=0):
    return json.dumps({"totalTestCount": total, "passedTests": passed, "failedTests": failed,
                       "skippedTests": skipped, "result": "Passed" if not failed else "Failed"})


def test_tests_pass(project, env):
    r = run("xc-test.py", ["--platform", "macos"], env=env, cwd=project, FAKE_TEST_SUMMARY=summary(3, 3))
    assert r.returncode == 0, r.stderr
    assert r.json["results"][0]["passed"] == 3


def test_zero_tests_is_a_failure(project, env):
    r = run("xc-test.py", ["--platform", "macos"], env=env, cwd=project, FAKE_TEST_SUMMARY=summary(0, 0))
    assert r.returncode == 1
    assert "zero tests" in r.json["results"][0]["reason"]


def test_unreadable_counts_are_a_failure(project, env):
    r = run("xc-test.py", ["--platform", "macos"], env=env, cwd=project)  # no summary written
    assert r.returncode == 1
    assert "could not read" in r.json["results"][0]["reason"]


def test_failing_tests_fail(project, env):
    r = run("xc-test.py", ["--platform", "macos"], env=env, cwd=project,
            FAKE_TEST_SUMMARY=summary(3, 2, 1), FAKE_TEST_RC=65)
    assert r.returncode == 1
    assert r.json["results"][0]["failed"] == 1


def test_run_that_dies_before_tests_says_so(project, env):
    r = run("xc-test.py", ["--platform", "macos"], env=env, cwd=project,
            FAKE_TEST_SUMMARY=summary(0, 0), FAKE_TEST_RC=65,
            FAKE_BUILD_OUTPUT="xcodebuild: error: Could not find test host for DemoTests")
    assert r.returncode == 1
    res = r.json["results"][0]
    assert "before any test ran" in res["reason"]
    assert any("Could not find test host" in e for e in res["error_samples"])


def test_ios_tests_use_a_concrete_simulator(project, env):
    r = run("xc-test.py", ["--platform", "ios-sim", "--device", "iPhone 17e"], env=env, cwd=project,
            FAKE_TEST_SUMMARY=summary(1, 1))
    assert r.returncode == 0, r.stderr
    assert "platform=iOS Simulator,id=NEW-2" in calls(env)


@pytest.mark.parametrize("output,expected", [
    ("✔ Test run with 12 tests in 3 suites passed after 0.01 seconds.", (12, 12, 0, 0)),
    ("✘ Test run with 12 tests in 3 suites failed after 0.02 seconds with 2 issues.", (12, 10, 2, 0)),
    ("Test Suite 'All tests' passed\n\t Executed 5 tests, with 0 failures (0 unexpected) in 0.1 seconds",
     (5, 5, 0, 0)),
    ("Executed 2 tests, with 1 failure (0 unexpected)\n✔ Test run with 3 tests passed after 0.1 seconds.",
     (5, 4, 1, 0)),
])
def test_swift_test_counts(output, expected):
    sys.path.insert(0, str(SCRIPTS))
    import importlib.util
    spec = importlib.util.spec_from_file_location("xc_test", SCRIPTS / "xc-test.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.counts_from_swift_test(output) == expected
    assert mod.counts_from_swift_test("Building for debugging...\nBuild complete!") is None


def test_package_with_no_tests_fails(project, env, tmp_path):
    pkg = tmp_path / "Engine"
    pkg.mkdir()
    (pkg / "Package.swift").write_text("// swift-tools-version: 6.0\n")
    r = run("xc-test.py", ["--packages-only", "--package", str(pkg)], env=env, cwd=project,
            FAKE_SWIFT_TEST_OUTPUT="✔ Test run with 0 tests passed after 0.0 seconds.")
    assert r.returncode == 1
    assert "zero tests" in r.json["results"][0]["reason"]
    r = run("xc-test.py", ["--packages-only", "--package", str(pkg)], env=env, cwd=project,
            FAKE_SWIFT_TEST_OUTPUT="✔ Test run with 4 tests in 1 suite passed after 0.0 seconds.")
    assert r.returncode == 0, r.stderr


# --- run / shot -----------------------------------------------------------------------------------


def test_run_needs_a_recorded_build(project, env):
    r = run("xc-run.py", ["--platform", "macos"], env=env, cwd=project)
    assert r.returncode == 1 and "xc-build.py" in r.json["fix"]


def test_macos_run_and_stop(project, env):
    assert run("xc-build.py", ["--platform", "macos"], env=env, cwd=project).returncode == 0
    r = run("xc-run.py", ["--platform", "macos", "--settle", "0"], env=env, cwd=project)
    assert r.returncode == 0, r.stderr
    assert r.json["running"] is True
    assert f"open {env['FAKE_PRODUCTS']}/Demo.app" in calls(env)
    r = run("xc-run.py", ["--platform", "macos", "--stop"], env=env, cwd=project)
    assert r.json["stopped"] is True


def test_macos_crash_on_launch_fails(project, env):
    assert run("xc-build.py", ["--platform", "macos"], env=env, cwd=project).returncode == 0
    r = run("xc-run.py", ["--platform", "macos", "--settle", "0"], env=env, cwd=project, FAKE_APP_CRASH=1)
    assert r.returncode == 1
    assert r.json["running"] is False and "crashed" in r.json["reason"]


def test_ios_run_boots_waits_installs_launches(project, env):
    assert run("xc-build.py", ["--platform", "ios-sim"], env=env, cwd=project).returncode == 0
    r = run("xc-run.py", ["--platform", "ios-sim", "--settle", "0"], env=env, cwd=project)
    assert r.returncode == 0, r.stderr
    assert r.json["udid"] == "NEW-1" and r.json["pid"] == "4242"
    log = calls(env)
    order = [log.index(f"simctl {s} NEW-1") for s in ("boot", "bootstatus", "install", "launch")]
    assert order == sorted(order)


def test_ios_running_check_survives_sigpipe(project, env):
    """launchctl lists the app first and then a lot more: `| grep -q` would SIGPIPE under pipefail."""
    assert run("xc-build.py", ["--platform", "ios-sim"], env=env, cwd=project).returncode == 0
    r = run("xc-run.py", ["--platform", "ios-sim", "--settle", "0"], env=env, cwd=project,
            FAKE_LAUNCHCTL_BIG=1)
    assert r.returncode == 0, r.stderr
    assert r.json["running"] is True


def test_macos_run_and_stop_with_regex_characters_in_path(project, env, tmp_path):
    products = tmp_path / "Build (1)+[x]"
    assert run("xc-build.py", ["--platform", "macos"], env=env, cwd=project,
               FAKE_PRODUCTS=products).returncode == 0
    r = run("xc-run.py", ["--platform", "macos", "--settle", "0"], env=env, cwd=project)
    assert r.returncode == 0, r.stderr
    assert r.json["running"] is True
    r = run("xc-run.py", ["--platform", "macos", "--stop"], env=env, cwd=project)
    assert r.json["stopped"] is True


def test_ios_crash_on_launch_fails(project, env):
    assert run("xc-build.py", ["--platform", "ios-sim"], env=env, cwd=project).returncode == 0
    r = run("xc-run.py", ["--platform", "ios-sim", "--settle", "0"], env=env, cwd=project, FAKE_APP_CRASH=1)
    assert r.returncode == 1 and r.json["running"] is False


def test_shot_restores_appearance(project, env, tmp_path):
    booted = json.loads(SIMCTL_JSON.read_text())
    booted["devices"]["com.apple.CoreSimulator.SimRuntime.iOS-27-0"][1]["state"] = "Booted"
    f = tmp_path / "booted.json"
    f.write_text(json.dumps(booted))
    r = run("xc-shot.py", ["--appearance", "dark"], env=env, cwd=project, FAKE_SIMCTL_JSON=f)
    assert r.returncode == 0, r.stderr
    log = calls(env)
    assert log.index("ui NEW-1 appearance dark") < log.index("io NEW-1 screenshot") \
        < log.index("ui NEW-1 appearance light")


@pytest.fixture
def mac_running(project, env):
    assert run("xc-build.py", ["--platform", "macos"], env=env, cwd=project).returncode == 0
    assert run("xc-run.py", ["--platform", "macos", "--settle", "0"], env=env, cwd=project).returncode == 0
    return project


def test_macos_shot_captures_only_the_app_window(mac_running, env):
    r = run("xc-shot.py", ["--platform", "macos", "--out", str(mac_running / "build" / "m.png")],
            env=env, cwd=mac_running)
    assert r.returncode == 0, r.stderr
    assert r.json["window"] == "77"
    assert "screencapture -x -o -l77 " in calls(env)
    assert (mac_running / "build" / "m.png").read_text() == "PNG"


def test_macos_shot_helper_is_compiled_once(mac_running, env):
    for _ in range(2):
        assert run("xc-shot.py", ["--platform", "macos"], env=env, cwd=mac_running).returncode == 0
    assert calls(env).count("swiftc ") == 1
    assert (Path(env["HOME"]) / xc.xcwin_rel()).is_file()


def test_macos_shot_without_screen_recording_says_how_to_grant_it(mac_running, env):
    r = run("xc-shot.py", ["--platform", "macos"], env=env, cwd=mac_running, FAKE_SCREEN_ACCESS="denied")
    assert r.returncode == 2
    assert "sshd-keygen-wrapper" in r.json["fix"]
    assert "screencapture" not in calls(env)


def test_macos_shot_needs_a_running_app_with_a_window(project, env, mac_running):
    r = run("xc-shot.py", ["--platform", "macos"], env=env, cwd=mac_running, FAKE_WINDOW_ID="")
    assert r.returncode == 1 and "no on-screen window" in r.json["error"]
    assert "screencapture" not in calls(env), "no window must never fall back to a capture"
    run("xc-run.py", ["--platform", "macos", "--stop"], env=env, cwd=mac_running)
    r = run("xc-shot.py", ["--platform", "macos"], env=env, cwd=mac_running)
    assert r.returncode == 1 and "not running" in r.json["error"] and "xc-run" in r.json["fix"]


def test_macos_shot_refuses_appearance(mac_running, env):
    r = run("xc-shot.py", ["--platform", "macos", "--appearance", "dark"], env=env, cwd=mac_running)
    assert r.returncode == 1 and "simulator-only" in r.json["error"]


def test_doctor_reports_screen_recording(project, env):
    r = run("xc-doctor.py", ["--platform", "macos"], env=env, cwd=project)
    assert statuses(r)["screen-recording"] == "ok"
    r = run("xc-doctor.py", ["--platform", "macos"], env=env, cwd=project, FAKE_SCREEN_ACCESS="denied")
    assert r.returncode == 0, "a missing grant only disables screenshots: warn, do not fail"
    c = next(c for c in r.json["checks"] if c["check"] == "screen-recording")
    assert c["status"] == "warn" and "sshd-keygen-wrapper" in c["fix"]


def test_shot_requires_a_booted_simulator(project, env):
    r = run("xc-shot.py", env=env, cwd=project)
    assert r.returncode == 1 and "not booted" in r.json["error"]


def test_shot_writes_png(project, env, tmp_path):
    booted = json.loads(SIMCTL_JSON.read_text())
    booted["devices"]["com.apple.CoreSimulator.SimRuntime.iOS-27-0"][1]["state"] = "Booted"
    f = tmp_path / "booted.json"
    f.write_text(json.dumps(booted))
    r = run("xc-shot.py", ["--out", str(project / "build" / "s.png")], env=env, cwd=project,
            FAKE_SIMCTL_JSON=f)
    assert r.returncode == 0, r.stderr
    assert (project / "build" / "s.png").read_text() == "PNG"


# --- bootstrap ----------------------------------------------------------------------------------


def test_bootstrap_multiplatform(project):
    yml = (project / "project.yml").read_text()
    assert "supportedDestinations: [iOS, macOS]" in yml
    assert 'iOS: "17.0"' in yml and 'macOS: "14.0"' in yml
    assert "TEST_HOST[sdk=macosx*]: $(BUILT_PRODUCTS_DIR)/Demo.app/Contents/MacOS/Demo" in yml
    assert "PRODUCT_BUNDLE_IDENTIFIER: com.example.demo" in yml
    assert 'SWIFT_VERSION: "6.0"' in yml
    for rel in ("Sources/Demo/DemoApp.swift", "Tests/DemoTests/DemoTests.swift",
                "Resources/Assets.xcassets/AppIcon.appiconset/Contents.json", ".gitignore", ".xcodegen-version"):
        assert (project / rel).is_file(), rel
    assert "__APP__" not in "".join(p.read_text() for p in project.rglob("*") if p.is_file())


def test_bootstrap_macos_only(tmp_path, env):
    r = run("xc-bootstrap.py", ["Tool", "--platforms", "macos", "--dir", str(tmp_path / "Tool")], env=env)
    assert r.returncode == 0, r.stderr
    yml = (tmp_path / "Tool" / "project.yml").read_text()
    assert "supportedDestinations: [macOS]" in yml
    assert "iOS:" not in yml and "UILaunchScreen" not in yml and "TARGETED_DEVICE_FAMILY" not in yml


def test_bootstrap_into_existing_repo_extends_gitignore(tmp_path, env):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text("# mine\n.build/\n")
    (repo / "README.md").write_text("keep me")
    r = run("xc-bootstrap.py", ["Game", "--dir", str(repo)], env=env)
    assert r.returncode == 0, r.stderr
    gi = (repo / ".gitignore").read_text()
    assert gi.startswith("# mine\n.build/\n")
    assert "*.xcodeproj/" in gi and gi.count(".build/") == 1
    assert (repo / "README.md").read_text() == "keep me"


def test_bootstrap_refuses_to_overwrite(project, env):
    r = run("xc-bootstrap.py", ["Demo", "--dir", str(project)], env=env)
    assert r.returncode == 1 and "refusing to overwrite" in r.json["error"]


@pytest.mark.parametrize("args", [["demo"], ["My-App"], ["Demo", "--bundle-id", "nodots"],
                                  ["Demo", "--platforms", "tvos"], ["Demo", "--ios", "17"]])
def test_bootstrap_validates_input(tmp_path, env, args):
    r = run("xc-bootstrap.py", [*args, "--dir", str(tmp_path / "x")], env=env)
    assert r.returncode == 1
    assert not (tmp_path / "x").exists()


# --- pure helpers ---------------------------------------------------------------------------------


DEVICES = json.loads(SIMCTL_JSON.read_text())


def test_pick_simulator_prefers_newest_runtime_iphone():
    assert xc.pick_simulator(DEVICES)["udid"] == "NEW-1"


def test_pick_simulator_prefers_booted():
    d = json.loads(json.dumps(DEVICES))
    d["devices"]["com.apple.CoreSimulator.SimRuntime.iOS-27-0"][2]["state"] = "Booted"
    assert xc.pick_simulator(d)["udid"] == "NEW-2"


def test_pick_simulator_by_name_and_udid():
    assert xc.pick_simulator(DEVICES, "iPhone 17")["udid"] == "OLD-1"
    assert xc.pick_simulator(DEVICES, "NEW-PAD")["name"].startswith("iPad")
    with pytest.raises(xc.XcError, match="no simulator named"):
        xc.pick_simulator(DEVICES, "iPhone 3G")
    with pytest.raises(xc.XcError, match="no available iOS simulators") as e:
        xc.pick_simulator({"devices": {}})
    assert "downloadPlatform" in e.value.fix


def test_pick_simulator_refuses_ambiguous_names():
    d = json.loads(json.dumps(DEVICES))
    d["devices"]["com.apple.CoreSimulator.SimRuntime.iOS-27-0"].append(
        {"udid": "DUP", "name": "iPhone 18 Pro", "state": "Shutdown", "isAvailable": True})
    with pytest.raises(xc.XcError, match="UDID"):
        xc.pick_simulator(d, "iPhone 18 Pro")


def test_signing_precedence(tmp_path, monkeypatch):
    monkeypatch.delenv("TEAM_ID", raising=False)
    assert xc.signing_settings(tmp_path, "macos")["style"] == "adhoc"
    assert xc.signing_settings(tmp_path, "ios-sim")["settings"] == []
    with pytest.raises(xc.XcError, match="team"):
        xc.signing_settings(tmp_path, "ios-device")
    (tmp_path / ".devteam").write_text("TEAM123456")
    assert xc.signing_settings(tmp_path, "macos")["style"] == "team"
    (tmp_path / ".signid").write_text("My Local Cert")
    s = xc.signing_settings(tmp_path, "macos")
    assert s["style"] == "identity" and "CODE_SIGN_IDENTITY=My Local Cert" in s["settings"]
    assert xc.signing_settings(tmp_path, "macos", adhoc=True)["style"] == "adhoc"
    assert xc.signing_settings(tmp_path, "ios-device")["style"] == "team"


def test_host_path_override_and_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("HOST_PROJECT_PATH", "/Users/me/proj")
    monkeypatch.setenv("HOST_PROJECT_ROOT", str(tmp_path))
    assert xc.host_path(tmp_path / "build" / "x.log") == "/Users/me/proj/build/x.log"
    with pytest.raises(xc.XcError, match="outside"):
        xc.host_path("/etc")
    monkeypatch.delenv("HOST_PROJECT_ROOT")
    with pytest.raises(xc.XcError, match="HOST_PROJECT_ROOT"):
        xc.host_path(tmp_path)
    monkeypatch.delenv("HOST_PROJECT_PATH")
    monkeypatch.setenv("PATH", "/nonexistent")
    with pytest.raises(xc.XcError) as e:
        xc.host_path(tmp_path)
    assert e.value.code == xc.EXIT_ENV


def test_host_user_from_workspace(monkeypatch):
    for k in ("XC_HOST_USER", "HOST_USER", "XC_HOST", "HOST_IP"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HOST_WORKSPACE", "/Users/jhunt/Source/Edda")
    assert xc.host_target() == "jhunt@host.docker.internal"
    monkeypatch.delenv("HOST_WORKSPACE")
    with pytest.raises(xc.XcError, match="which user") as e:
        xc.host_target()
    assert "XC_HOST_USER" in e.value.fix


def test_summarize_log():
    text = "\n".join([
        "/a/Foo.swift:3:5: error: cannot find 'x'",
        "/a/Foo.swift:3:5: error: cannot find 'x'",
        "/a/Bar.swift:9:1: warning: unused",
        "xcodebuild: error: Could not find test host",
        "/p/App.debug.dylib: errSecInternalComponent",
        "Command CodeSign failed with a nonzero exit code",
        "** BUILD FAILED **",
    ])
    s = xc.summarize_log(text)
    assert s["errors"] == 4 and s["warnings"] == 1
    assert "Foo.swift:3: cannot find 'x'" in s["error_samples"]
    assert "App.debug.dylib: errSecInternalComponent" in s["error_samples"]
    assert s["tail"][-1] == "** BUILD FAILED **"
