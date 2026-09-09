#!/usr/bin/env python3
"""tests/test_zoo_live.py — zoo against a REAL daemon, with a REAL session. Opt-in (spec req 30).

    ZOO_LIVE=1 python3 -m unittest discover -s tests -p 'test_zoo_live.py' -v

Skips loudly unless ZOO_LIVE=1: it creates a primate session (`primate-session minion
zoo-live-<pid> --no-workspace`) through the real zfuncs, drives zoo through the pty harness to
attach to it and detach, opens a shell in it, and removes it through zoo's confirm — so it must
never run on a machine where the maintainer has live sessions without being asked. It cleans up
its own session on the way out, whatever happened, and touches no other container.

What it proves that the hermetic suites cannot: the real API and CLI on this daemon (one-shot
stats, inspect, start, rm, exec -it), a real tmux hand-off and return, the real ~/.zfuncs and
roster on this host, and the self-guard on this side of the container/host fork.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_zoo_tty import PROMPT, PROMPT_RE, RMCUP, SMCUP, Shell, has_row  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
ZOO = ROOT / "bin" / "zoo"
ZFUNCS = ROOT / "zfuncs"
IMAGE = os.environ.get("ZOO_LIVE_IMAGE", "minion")
NAME = f"zoo-live-{os.getpid()}"

LIVE = os.environ.get("ZOO_LIVE") == "1"
SKIP = ("SKIPPED: set ZOO_LIVE=1 to run the live suite — it creates and removes a real primate "
        f"session ({IMAGE}) on this daemon")


def sh(*argv, **kw):
    return subprocess.run(argv, capture_output=True, text=True, timeout=120, **kw)


def zfuncs_call(*fn_and_args):
    """Run a zfuncs function the way zoo does: source the real file in a child zsh."""
    return sh("zsh", "-c", 'source "$1" >/dev/null 2>&1; shift; "$@"', "live", str(ZFUNCS), *fn_and_args)


@unittest.skipUnless(LIVE, SKIP)
@unittest.skipUnless(shutil.which("zsh") and shutil.which("docker"), "SKIPPED: needs zsh and docker")
class LiveSessionTest(unittest.TestCase):
    """One session, created before the tests and removed after — and by the last test itself."""

    @classmethod
    def setUpClass(cls):
        # The real launcher, the way zoo calls it. It ends by attaching with `docker exec -it`,
        # which fails at once without a tty — and the detached container stays up, which is all
        # that is wanted here. Creating it any other way would test something other than zoo's path.
        r = zfuncs_call("primate-session", IMAGE, NAME, "--no-workspace")
        cls.create_output = (r.stdout + r.stderr)
        ids = sh("docker", "ps", "-a", "--filter", f"label=primate.name={NAME}", "--format", "{{.ID}}").stdout.split()
        if not ids:
            raise unittest.SkipTest(f"could not create the live session:\n{cls.create_output}")
        cls.cid = ids[0]

    @classmethod
    def tearDownClass(cls):
        sh("docker", "rm", "-f", NAME)   # idempotent: the last test removes it through zoo

    def setUp(self):
        self.tmp = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / f"zoo-live-{os.getpid()}"
        self.tmp.mkdir(exist_ok=True)
        (self.tmp / "bin").mkdir(exist_ok=True)
        link = self.tmp / "bin" / "zoo"
        if not link.exists():
            link.symlink_to(ZOO)
        env = dict(os.environ)
        env["TERM"] = "xterm-256color"
        env["PATH"] = f"{self.tmp / 'bin'}:{env.get('PATH', '')}"
        env["ZOO_ZFUNCS"] = str(ZFUNCS)
        self.sh = Shell(env)
        self.sh.send(f"PROMPT='{PROMPT}'\r")
        self.sh.expect(PROMPT_RE)

    def tearDown(self):
        self.sh.close()

    def start_zoo(self):
        self.sh.send("zoo -i 1\r")
        self.sh.expect(SMCUP)
        self.sh.wait_screen("KIND", timeout=20)

    def select(self, name):
        """Move the selection to the row named `name`. The screen model carries no attributes, so
        the selection is read back through the confirm prompt: x names the selected row, n keeps it."""
        self.sh.wait_until(lambda scr: has_row(scr, name), f"row {name}", timeout=20)
        self.sh.send("g")
        for _ in range(60):
            self.sh.send("x")
            self.sh.wait_screen("Remove ", timeout=10)
            if f"'{name}'" in self.sh.screen:
                self.sh.send("n")
                self.sh.wait_screen(f"kept session {name}", timeout=10)
                return
            self.sh.send("n")
            self.sh.wait_screen_gone("Remove ", timeout=10)
            self.sh.send("j")
        raise AssertionError(f"could not select {name}")

    def test_1_listed_with_live_figures(self):
        self.start_zoo()
        self.sh.wait_until(lambda scr: has_row(scr, NAME), "the live session row", timeout=20)
        line = next(l for l in self.sh.screen.text() if has_row_line(l, NAME))
        self.assertIn(IMAGE, line)
        # A live figure, not "..." or "stale": wait for the second tick's delta.
        self.sh.wait_until(lambda scr: any(has_row_line(l, NAME) and "..." not in l and "stale" not in l
                                           for l in scr.text()), "a computed CPU%", timeout=20)
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)

    def test_2_attach_detach_and_shell(self):
        self.start_zoo()
        self.select(NAME)
        self.sh.send("a")
        self.sh.wait_screen(f"attaching to session {NAME}", timeout=20)
        # Inside tmux now. Prove it with tmux's own environment, then detach.
        time.sleep(2)
        self.sh.send("echo TMUX-IS-$(( 20 + 3 ))\r")
        self.sh.wait_screen("TMUX-IS-23", timeout=20)
        self.sh.send(b"\x02d")   # ctrl-b d
        self.sh.wait_screen(f"attach {NAME} ended", timeout=20)
        self.sh.wait_screen("KIND", timeout=20)
        self.sh.send("e")
        # The full banner exceeds 80 columns with a pid in the name and wraps mid-word on the real
        # terminal; its wording is asserted by the hermetic pty suite. Here: that it began, and
        # that a shell in the container followed.
        self.sh.wait_screen("opening a new shell in session", timeout=20)
        time.sleep(2)
        self.sh.send("echo SHELL-IN-$(hostname)\r")
        self.sh.wait_screen(f"SHELL-IN-{IMAGE}", timeout=20)   # the launchers set --hostname <image>
        self.sh.send("exit\r")
        self.sh.wait_screen(f"shell {NAME} ended", timeout=20)
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)

    def test_3_kill_through_zoo_keeps_the_volume(self):
        before = self.sh.stty()
        vol = sh("docker", "volume", "inspect", f"{IMAGE}-home").returncode
        self.assertEqual(vol, 0, f"{IMAGE}-home should exist before the kill")
        self.start_zoo()
        self.select(NAME)
        self.sh.send("x")
        self.sh.wait_screen(f"Remove session '{NAME}'", timeout=10)
        self.sh.wait_screen(f"{IMAGE}-home survives", timeout=10)
        self.sh.send("y")
        self.sh.wait_screen(f"removed session {NAME}; volume {IMAGE}-home kept", timeout=30)
        self.sh.wait_until(lambda scr: not has_row(scr, NAME), "the row disappearing", timeout=20)
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)
        self.assertEqual(self.sh.stty(), before)
        self.assertNotEqual(sh("docker", "inspect", NAME).returncode, 0, "container should be gone")
        self.assertEqual(sh("docker", "volume", "inspect", f"{IMAGE}-home").returncode, 0, "volume must survive")


def has_row_line(line, name):
    parts = line.split()
    return len(parts) > 1 and parts[0] in ("session", "primate") and parts[1] == name


if __name__ == "__main__":
    unittest.main()
