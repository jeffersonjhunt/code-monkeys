#!/usr/bin/env python3
"""tests/test_zoo_live.py — zoo against a REAL daemon, a REAL container, a REAL tmux. Opt-in.

    ZOO_LIVE=1 python3 -m unittest discover -s tests -p 'test_zoo_live.py' -v

Skips loudly unless ZOO_LIVE=1 (spec req 30): it creates a primate session
(`primate-session <image> zoo-live-<pid> --no-workspace`) through the real zfuncs and drives zoo
against it, so it must never run where the maintainer has live sessions without being asked. It
removes its own container whatever happens, and touches no other one.

What it proves that the hermetic suites cannot: the real Engine API and CLI on this daemon
(one-shot stats, inspect, start, rm), the real ~/.zfuncs and roster, the self-guard on this side
of the container/host fork, and — the point of the tmux rework — zoo auto-wrapping into a real
tmux server, opening a real window into the container's own tmux, and killing through the confirm.

The outer tmux is isolated by TMUX_TMPDIR to a temp dir, so zoo's `new-session -A -s zoo` lands
on a private server that this suite tears down; it never touches the maintainer's tmux.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_zoo_tty import PROMPT, PROMPT_RE, Shell, has_row  # noqa: E402

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
    return sh("zsh", "-c", 'source "$1" >/dev/null 2>&1; shift; "$@"', "live", str(ZFUNCS), *fn_and_args)


def has_row_line(line, name):
    parts = line.split()
    return len(parts) > 1 and parts[0] in ("session", "primate") and parts[1] == name


@unittest.skipUnless(LIVE, SKIP)
@unittest.skipUnless(shutil.which("zsh") and shutil.which("docker") and shutil.which("tmux"),
                     "SKIPPED: needs zsh, docker and tmux")
class LiveSessionTest(unittest.TestCase):
    """One container, created before the tests and removed by the last one (and tearDownClass)."""

    @classmethod
    def setUpClass(cls):
        # The real launcher, as zoo calls it. It ends by attaching with `docker exec -it`, which
        # exits at once without a tty, leaving the detached container up — which is all we need.
        r = zfuncs_call("primate-session", IMAGE, NAME, "--no-workspace")
        cls.create_output = r.stdout + r.stderr
        ids = sh("docker", "ps", "-a", "--filter", f"label=primate.name={NAME}",
                 "--format", "{{.ID}}").stdout.split()
        if not ids:
            raise unittest.SkipTest(f"could not create the live session:\n{cls.create_output}")
        cls.cid = ids[0]

    @classmethod
    def tearDownClass(cls):
        sh("docker", "rm", "-f", NAME)

    def setUp(self):
        self.tmp = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / f"zoo-live-{os.getpid()}-{self.id().split('.')[-1]}"
        (self.tmp / "bin").mkdir(parents=True, exist_ok=True)
        link = self.tmp / "bin" / "zoo"
        if not link.exists():
            link.symlink_to(ZOO)
        self.tmux_tmpdir = self.tmp / "tmxtmp"
        self.tmux_tmpdir.mkdir(exist_ok=True)
        self.tmux_sock = str(self.tmux_tmpdir / f"tmux-{os.getuid()}" / "default")
        env = dict(os.environ)
        env["TERM"] = "xterm-256color"
        env["PATH"] = f"{self.tmp / 'bin'}:{env.get('PATH', '')}"
        env["ZOO_ZFUNCS"] = str(ZFUNCS)
        env["TMUX_TMPDIR"] = str(self.tmux_tmpdir)   # isolate zoo's tmux server
        env.pop("TMUX", None)                        # let zoo auto-wrap for real
        self.sh = Shell(env)
        self.sh.send(f"PROMPT='{PROMPT}'\r")
        self.sh.expect(PROMPT_RE)

    def tearDown(self):
        self.outer("kill-server")   # detaches the pty client and reaps zoo's isolated tmux
        self.sh.close()
        import shutil as _sh
        _sh.rmtree(self.tmp, ignore_errors=True)   # leave no temp dir behind on the host

    def outer(self, *args, timeout=10):
        return subprocess.run([shutil.which("tmux"), "-S", self.tmux_sock, *args],
                              capture_output=True, text=True, timeout=timeout)

    def wait_outer(self, args, needle, timeout=25):
        import time
        deadline = time.monotonic() + timeout
        while True:
            r = self.outer(*args)
            if r.returncode == 0 and needle in r.stdout:
                return r.stdout
            if time.monotonic() > deadline:
                raise AssertionError(f"tmux {args} never showed {needle!r}: rc={r.returncode} "
                                     f"out={r.stdout!r} err={r.stderr!r}")
            self.sh._read(0.2)

    def start_zoo(self):
        self.sh.send("zoo -i 1\r")               # no TMUX in env -> zoo auto-wraps into real tmux
        self.sh.wait_screen("KIND", timeout=25)
        self.wait_outer(["list-sessions"], "zoo")

    def select(self, name):
        """Move the highlight onto `name`, read back through the confirm prompt (the screen model
        has no attributes): x names the selected row, n keeps it."""
        self.sh.wait_until(lambda scr: has_row(scr, name), f"row {name}", timeout=25)
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
        self.sh.wait_until(lambda scr: has_row(scr, NAME), "the live session row", timeout=25)
        line = next(l for l in self.sh.screen.text() if has_row_line(l, NAME))
        self.assertIn(IMAGE, line)
        self.sh.wait_until(lambda scr: any(has_row_line(l, NAME) and "..." not in l and "stale" not in l
                                           for l in scr.text()), "a computed CPU%", timeout=25)

    def test_2_attach_opens_a_real_window_into_the_container(self):
        self.start_zoo()
        self.select(NAME)
        self.sh.send("a")
        # A real window into the container's tmux opens and becomes active in zoo's session.
        self.wait_outer(["list-windows", "-t", "zoo", "-F", "#{window_active} #{window_name}"],
                        f"1 attach-{NAME}")
        # Keystrokes now reach the container's shell (nested tmux; outer prefix is ctrl-b). Prove
        # we are inside the container by its hostname — the launchers set --hostname <image>.
        import time
        time.sleep(2)
        self.sh.send("echo HOST-$(hostname)\r")
        self.wait_outer(["capture-pane", "-p", "-t", f"zoo:attach-{NAME}"], f"HOST-{IMAGE}")
        # ctrl-b 0 returns to zoo's still-live list.
        self.sh.send(b"\x020")
        self.wait_outer(["list-windows", "-t", "zoo", "-F", "#{window_active} #{window_name}"], "1 zoo")
        self.sh.wait_screen("KIND", timeout=25)

    def test_3_kill_through_zoo_keeps_the_volume(self):
        self.assertEqual(sh("docker", "volume", "inspect", f"{IMAGE}-home").returncode, 0,
                         f"{IMAGE}-home should exist before the kill")
        self.start_zoo()
        self.select(NAME)
        self.sh.send("x")
        self.sh.wait_screen(f"Remove session '{NAME}'", timeout=10)
        self.sh.wait_screen(f"{IMAGE}-home survives", timeout=10)
        self.sh.send("y")
        self.sh.wait_screen(f"removed session {NAME}; volume {IMAGE}-home kept", timeout=30)
        self.sh.wait_until(lambda scr: not has_row(scr, NAME), "the row disappearing", timeout=25)
        self.assertNotEqual(sh("docker", "inspect", NAME).returncode, 0, "container should be gone")
        self.assertEqual(sh("docker", "volume", "inspect", f"{IMAGE}-home").returncode, 0,
                         "volume must survive")


if __name__ == "__main__":
    unittest.main()
