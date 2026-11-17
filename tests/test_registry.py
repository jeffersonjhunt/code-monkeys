"""primate-pull and the primate push scripts after g.deceiver forge F4: no registry named in this public repo (exit 2
without one), ECR refused (exit 2), FILE-based pull auth (`primate-pull --login`: 0600, no credsStore, the secret on
stdin only), and pushes through a throwaway DOCKER_CONFIG (no credential = exit 8, nothing built). A stub docker on
PATH records every call and the DOCKER_CONFIG it ran with.

    uv run --no-project --with pytest pytest -q tests/test_registry.py
"""
from __future__ import annotations

import base64
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PP = REPO / "bin" / "primate-pull"
ECR = "521147433280.dkr.ecr.us-east-1.amazonaws.com"
REG = "registry.example:8443"
DOCKER = r'''#!/bin/sh
printf '%s cfg=%s\n' "$*" "${DOCKER_CONFIG:-none}" >> "$STUB/calls"
case "$1" in
  version) exit 0 ;;
  image) [ -e "$STUB/have-$(echo "$3" | tr '/:' '__')" ] && exit 0; exit 1 ;;
  pull) [ -s "$DOCKER_CONFIG/config.json" ] || { echo "unauthorized" >&2; exit 1; }; exit 0 ;;
  login) cat > "$STUB/stdin"; exit 0 ;;
esac
exit 0
'''


@pytest.fixture
def env(tmp_path):
    b = tmp_path / "bin"; b.mkdir(); (b / "docker").write_text(DOCKER); (b / "docker").chmod(0o755)
    home = tmp_path / "home"; home.mkdir()
    e = {k: v for k, v in os.environ.items() if not k.startswith(("CODEMONKEYS_", "GD_REGISTRY", "CM_"))}
    e.update(PATH=f"{b}:{os.environ['PATH']}", STUB=str(tmp_path), HOME=str(home))
    return tmp_path, home, e


def have(t, ref):
    (t / ("have-" + ref.replace("/", "_").replace(":", "_"))).write_text("")


def conf(home, reg=REG):
    d = home / ".config" / "code-monkeys"; d.mkdir(parents=True, exist_ok=True)
    (d / "registry.conf").write_text(f"CODEMONKEYS_REGISTRY={reg}\n")


def run(cmd, e, stdin=None):
    r = subprocess.run(cmd, capture_output=True, text=True, env=e, input=stdin, timeout=60)
    return r.returncode, r.stdout + r.stderr


def test_all_local_needs_no_registry_so_the_shims_keep_working(env):
    t, home, e = env
    have(t, "nyckel:latest")
    rc, out = run([str(PP), "nyckel"], e)
    assert rc == 0, out
    assert "pull" not in (t / "calls").read_text()


def test_no_registry_configured_is_exit_2_and_ecr_is_refused(env):
    t, home, e = env
    rc, out = run([str(PP), "minion"], e)
    assert rc == 2 and "no registry configured" in out, out
    conf(home, ECR)
    rc, out = run([str(PP), "minion"], e)
    assert rc == 2 and "REFUSED" in out and "pull" not in (t / "calls").read_text()
    rc, out = run([str(PP), "--registry"], dict(e, CODEMONKEYS_REGISTRY=REG))
    assert rc == 0 and out.strip() == REG, "the env wins over the file"


def test_login_writes_a_0600_file_credential_without_a_keychain(env):
    t, home, e = env
    conf(home)
    rc, out = run([str(PP), "--login"], e, stdin="robotSECRET\n")
    assert rc == 0 and "robotSECRET" not in out, out
    d = home / ".config/code-monkeys/docker"
    cfg = json.loads((d / "config.json").read_text())
    assert set(cfg) == {"auths"}, "no credsStore / credHelpers: docker must read the file"
    assert base64.b64decode(cfg["auths"][REG]["auth"]).decode() == "robot$primate-pull:robotSECRET"
    assert stat.S_IMODE((d / "config.json").stat().st_mode) == 0o600 and stat.S_IMODE(d.stat().st_mode) == 0o700
    rc, out = run([str(PP), "--login"], e, stdin="")
    assert rc == 1 and "no secret" in out


def test_a_pull_uses_the_file_credential_and_tags_it(env):
    t, home, e = env
    conf(home)
    rc, out = run([str(PP), "minion"], e)
    assert rc == 1 and "--login" in out, "no credential: say how to store it"
    run([str(PP), "--login"], e, stdin="robotSECRET\n")
    rc, out = run([str(PP), "minion"], e)
    assert rc == 0, out
    calls = (t / "calls").read_text()
    assert f"pull -q {REG}/codemonkeys/minion:latest cfg={home}/.config/code-monkeys/docker" in calls, calls
    assert f"tag {REG}/codemonkeys/minion:latest minion:latest" in calls


def test_a_symlinked_shim_finds_its_lib(env):
    t, home, e = env
    link = home / ".local/bin"; link.mkdir(parents=True)
    (link / "primate-pull").symlink_to(PP)
    have(t, "nyckel:latest")
    assert run([str(link / "primate-pull"), "nyckel"], e)[0] == 0


@pytest.mark.parametrize("script", ["build-push.sh", "manifest-push.sh"])
def test_push_scripts_refuse_without_a_registry_an_ecr_host_or_a_credential(env, script):
    t, home, e = env
    s = str(REPO / "primates" / script)
    assert run(["bash", s, "minion"], e)[0] == 2
    rc, out = run(["bash", s, "minion"], dict(e, CODEMONKEYS_REGISTRY=REG, ECR_REGISTRY=ECR))
    assert rc == 2 and "REFUSED" in out
    rc, out = run(["bash", s, "minion"], dict(e, CODEMONKEYS_REGISTRY=REG))
    assert rc == 8 and "no push credential" in out, out
    calls = (t / "calls").read_text() if (t / "calls").exists() else ""
    assert "push" not in calls and "imagetools create" not in calls


def test_push_logs_in_to_a_throwaway_config_with_the_secret_on_stdin(env):
    t, home, e = env
    (t / "robot").write_text("pushSECRET\n")
    s = str(REPO / "primates" / "manifest-push.sh")
    rc, out = run(["bash", s, "minion"], dict(e, CODEMONKEYS_REGISTRY=REG, GD_REGISTRY_PASSWORD_FILE=str(t / "robot")))
    assert rc == 0, out
    calls = (t / "calls").read_text()
    login = [c for c in calls.splitlines() if c.startswith("login")][0]
    assert f"--password-stdin {REG}" in login and "cfg=none" not in login and str(home / ".docker") not in login
    assert "pushSECRET" not in calls + out and (t / "stdin").read_text() == "pushSECRET\n"
    tmpcfg = login.split("cfg=")[1]
    assert not Path(tmpcfg).exists(), "the throwaway DOCKER_CONFIG is removed on exit"
