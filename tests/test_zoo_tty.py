#!/usr/bin/env python3
"""tests/test_zoo_tty.py — the interactive view, driven through a real pty from an interactive zsh.

Why this shape (spec §8):
- req 27: job control exists only in a shell reading from a terminal. `zsh -c` and `zsh -i -c`
  run with monitor off and cannot show a stray "[1] done" or a mangled tty. So each test forks a
  pty, execs `zsh -f -i` on it, proves monitor is on, and types `zoo` at the prompt.
- req 29: nothing ambient. TERM is forced, HOME is a temp dir, zsh reads no rc files (-f), and
  DOCKER_HOST points at a fake daemon serving fixtures on a unix socket in that temp dir.
- spec §4.2 traps: every marker asserted differs from anything typed to produce it, and
  `expect` consumes the transcript in order, so "after the event" is what is asserted.
- req 20: `stty -g` before zoo and after it must be identical, for q and for ctrl-c.

Run:  python3 -m unittest discover -s tests -p 'test_zoo*.py'
Skips loudly if zsh is not installed; creates no containers.
"""
import fcntl
import json
import os
import pathlib
import pty
import re
import select
import shutil
import signal
import socketserver
import struct
import sys
import tempfile
import termios
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler

ROOT = pathlib.Path(__file__).resolve().parent.parent
ZOO = ROOT / "bin" / "zoo"

SMCUP, RMCUP = b"\x1b[?1049h", b"\x1b[?1049l"
CIVIS, CNORM = b"\x1b[?25l", b"\x1b[?25h"
PROMPT = "@Z@ "
PROMPT_RE = re.compile(rb"(?:^|[\r\n])@Z@ ")
JOB_NOTICE_RE = re.compile(rb"\[\d+\]\s*[-+]?\s*(?:done|terminated|suspended|running|exit)")


def cid(prefix):
    return (prefix + "0" * 64)[:64]


def session(name, prefix, state="running", status="Up 3 hours"):
    return {"Id": cid(prefix), "Names": ["/" + name], "Image": "claude:latest", "State": state,
            "Status": status,
            "Labels": {"primate.managed": "", "primate.session": "", "primate.image": "claude",
                       "primate.name": name}}


def fixture_small():
    return [
        session("evoc", "aa"),
        session("scratch", "bb"),
        session("build", "cc", state="exited", status="Exited (0) 2 days ago"),
        {"Id": cid("ee"), "Names": ["/sweb-eval-7"], "Image": "spark-bench:latest",
         "State": "running", "Status": "Up 1 hour", "Labels": {}},
    ]


def fixture_long(n=40):
    return [session(f"sess{i:02d}", f"{i:02x}") for i in range(n)]


# --------------------------------------------------------------------------- fake daemon


class DaemonState:
    def __init__(self, containers):
        self.containers = containers
        self.stats_ok = True
        self.down = False
        self.reads = 0
        self.requests = []


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    STATS_RE = re.compile(r"^/containers/([0-9a-f]{64})/stats\?stream=false&one-shot=true$")

    def log_message(self, *args):
        pass

    def _reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        st = self.server.state
        st.requests.append(("GET", self.path))
        if st.down:
            return self._reply(500, {"message": "daemon down (fake)"})
        if self.path == "/containers/json?all=true":
            return self._reply(200, st.containers)
        if self.STATS_RE.match(self.path):
            if not st.stats_ok:
                return self._reply(500, {"message": "stats broken (fake)"})
            st.reads += 1
            n = st.reads
            return self._reply(200, {
                "cpu_stats": {"cpu_usage": {"total_usage": 100 * n}, "system_cpu_usage": 1000 * n,
                              "online_cpus": 4},
                "memory_stats": {"usage": 2_000_000, "limit": 8_000_000, "stats": {"inactive_file": 500_000}},
                "pids_stats": {"current": 7},
            })
        return self._reply(404, {"message": "page not found"})


class FakeDaemon(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def __init__(self, path, state):
        super().__init__(path, _Handler)
        self.state = state


# --------------------------------------------------------------------------- screen model


class Screen:
    """Enough of a VT100 to know what is on the screen. curses emits only the cells that changed,
    so a byte-stream search for "refresh 1.2s" sees a lone "1" — assertions about content must be
    made against the screen, and only the escape sequences (smcup, cnorm, ...) against the stream."""

    def __init__(self, rows, cols):
        self.resize(rows, cols)
        self._esc = b""

    def resize(self, rows, cols):
        self.rows, self.cols = rows, cols
        self.grid = [[" "] * cols for _ in range(rows)]
        self.r = self.c = 0

    def text(self):
        return ["".join(line).rstrip() for line in self.grid]

    def __contains__(self, needle):
        return any(needle in line for line in self.text())

    def _put(self, ch):
        if self.c >= self.cols:
            self.c = 0
            self._lf()
        self.grid[self.r][self.c] = ch
        self.c += 1

    def _lf(self):
        if self.r + 1 >= self.rows:
            self.grid.pop(0)
            self.grid.append([" "] * self.cols)
        else:
            self.r += 1

    def _clear(self, r0, c0, r1, c1):
        for r in range(r0, r1 + 1):
            for c in range(c0 if r == r0 else 0, (c1 if r == r1 else self.cols - 1) + 1):
                self.grid[r][c] = " "

    def feed(self, data):
        for b in data.decode("utf-8", errors="replace"):
            if self._esc:
                self._esc += b
                self._escape()
                continue
            if b == "\x1b":
                self._esc = b
            elif b == "\r":
                self.c = 0
            elif b == "\n":
                self._lf()
            elif b == "\b":
                self.c = max(self.c - 1, 0)
            elif b == "\t":
                self.c = min((self.c // 8 + 1) * 8, self.cols - 1)
            elif b >= " ":
                self._put(b)

    def _escape(self):
        e = self._esc
        if len(e) == 2:
            if e[1] in "()":       # charset designation: one more byte
                return
            if e[1] != "[" and e[1] != "]":
                self._esc = b""    # ESC 7, ESC 8, ESC =, ESC >, ESC M ...: ignored
            return
        if len(e) == 3 and e[1] in "()":
            self._esc = b""
            return
        if e[1] == "]":            # OSC ... BEL
            if e.endswith("\x07") or e.endswith("\x1b\\"):
                self._esc = b""
            return
        final = e[-1]
        if not ("@" <= final <= "~"):
            return                 # still collecting parameters
        self._esc = b""
        body = e[2:-1]
        private = body.startswith("?")
        params = [int(p) if p.isdigit() else 0 for p in body.lstrip("?").split(";")] if body.lstrip("?") else []
        n = params[0] if params else 0
        r, c = self.r, self.c
        if private:
            if final in "hl" and 1049 in params:
                self.grid = [[" "] * self.cols for _ in range(self.rows)]
                self.r = self.c = 0
            return
        if final in "Hf":
            self.r = min(max((params[0] if params else 1) - 1, 0), self.rows - 1)
            self.c = min(max((params[1] if len(params) > 1 else 1) - 1, 0), self.cols - 1)
        elif final == "d":
            self.r = min(max(n - 1, 0), self.rows - 1)
        elif final in "G`":
            self.c = min(max(n - 1, 0), self.cols - 1)
        elif final == "A":
            self.r = max(r - max(n, 1), 0)
        elif final == "B":
            self.r = min(r + max(n, 1), self.rows - 1)
        elif final == "C":
            self.c = min(c + max(n, 1), self.cols - 1)
        elif final == "D":
            self.c = max(c - max(n, 1), 0)
        elif final == "J":
            if n == 0:
                self._clear(r, c, self.rows - 1, self.cols - 1)
            elif n == 1:
                self._clear(0, 0, r, c)
            else:
                self._clear(0, 0, self.rows - 1, self.cols - 1)
        elif final == "K":
            if n == 0:
                self._clear(r, c, r, self.cols - 1)
            elif n == 1:
                self._clear(r, 0, r, c)
            else:
                self._clear(r, 0, r, self.cols - 1)
        elif final == "@":
            k = max(n, 1)
            self.grid[r][c:] = ([" "] * k + self.grid[r][c:])[: self.cols - c]
        elif final == "P":
            k = max(n, 1)
            self.grid[r][c:] = (self.grid[r][c + k:] + [" "] * k)[: self.cols - c]
        elif final == "X":
            self._clear(r, c, r, min(c + max(n, 1) - 1, self.cols - 1))
        # m (attributes), r (scroll region), h/l (modes), s/u, t: nothing the tests look at


# --------------------------------------------------------------------------- pty driver


class Shell:
    """An interactive zsh on a pty. `expect` consumes the transcript in order."""

    def __init__(self, env, rows=24, cols=80):
        pid, fd = pty.fork()
        if pid == 0:  # child
            os.execvpe("zsh", ["zsh", "-f", "-i", "+o", "zle"], env)
        self.pid, self.fd = pid, fd
        self.buf = b""
        self.pos = 0
        self.screen = Screen(rows, cols)
        self.resize(rows, cols)

    def resize(self, rows, cols):
        self.screen.resize(rows, cols)
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def send(self, data):
        os.write(self.fd, data if isinstance(data, bytes) else data.encode())

    def _read(self, timeout):
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return False
        try:
            chunk = os.read(self.fd, 65536)
        except OSError:
            return False
        if not chunk:
            return False
        self.buf += chunk
        self.screen.feed(chunk)
        return True

    def wait_screen(self, needle, timeout=10.0):
        """Wait until `needle` is on the screen. Content assertions go here; the byte stream is
        only for escape sequences (see Screen)."""
        deadline = time.monotonic() + timeout
        while needle not in self.screen:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(f"{needle!r} never appeared on screen:\n" + "\n".join(self.screen.text()))
            self._read(min(remaining, 0.2))

    def wait_screen_gone(self, needle, timeout=10.0):
        deadline = time.monotonic() + timeout
        while needle in self.screen:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(f"{needle!r} is still on screen:\n" + "\n".join(self.screen.text()))
            self._read(min(remaining, 0.2))

    def expect(self, pattern, timeout=10.0):
        """Wait for `pattern` (bytes or compiled regex) after everything consumed so far."""
        if isinstance(pattern, bytes):
            pattern = re.compile(re.escape(pattern))
        deadline = time.monotonic() + timeout
        while True:
            m = pattern.search(self.buf, self.pos)
            if m:
                self.pos = m.end()
                return m
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                tail = self.buf[-600:]
                raise AssertionError(f"timed out waiting for {pattern.pattern!r}; transcript tail: {tail!r}")
            self._read(min(remaining, 0.2))

    def settle(self, seconds=0.3):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self._read(0.05)

    def since(self, mark):
        return self.buf[mark:]

    def run(self, cmd):
        """Type a command, wait for its echo, return when the prompt is back."""
        self.send(cmd + "\r")
        self.expect(cmd.encode())
        mark = self.pos
        self.expect(PROMPT_RE)
        return self.buf[mark:self.pos]

    def stty(self):
        out = self.run("stty -g")
        lines = [l.strip() for l in out.splitlines() if l.strip() and PROMPT.encode() not in l]
        assert lines, f"no stty output in {out!r}"
        return lines[0]

    def close(self):
        try:
            os.kill(self.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            os.waitpid(self.pid, 0)
        except ChildProcessError:
            pass
        os.close(self.fd)


# --------------------------------------------------------------------------- the tests


@unittest.skipUnless(shutil.which("zsh"), "SKIPPED: zsh is not installed, so the pty suite cannot run")
class TtyTest(unittest.TestCase):
    fixture = staticmethod(fixture_small)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        home = pathlib.Path(self.tmp.name)
        (home / "bin").mkdir()
        os.symlink(ZOO, home / "bin" / "zoo")
        sock = home / "d.sock"
        self.state = DaemonState(self.fixture())
        self.daemon = FakeDaemon(str(sock), self.state)
        threading.Thread(target=self.daemon.serve_forever, daemon=True).start()
        env = {
            "TERM": "xterm-256color",
            "HOME": str(home),
            "PATH": f"{home / 'bin'}:{pathlib.Path(sys.executable).parent}:/usr/bin:/bin",
            "DOCKER_HOST": f"unix://{sock}",
        }
        self.sh = Shell(env)
        self.sh.send(f"PROMPT='{PROMPT}'\r")
        self.sh.expect(PROMPT_RE)
        # Positive proof that this shell is the kind req 27 demands, so the absence assertions
        # on job notices below mean something.
        out = self.sh.run("[[ -o monitor ]] && echo MON$((1+1))")
        self.assertIn(b"MON2", out, "job control is off in the test shell; the suite would be blind")

    def tearDown(self):
        self.sh.close()
        self.daemon.shutdown()
        self.daemon.server_close()
        self.tmp.cleanup()

    def start_zoo(self, interval="0.2"):
        self.sh.send(f"zoo -i {interval}\r")
        self.sh.expect(SMCUP)
        self.sh.wait_screen("KIND")

    def assert_terminal_returned(self, mark, before, rc):
        window = self.sh.since(mark)
        self.assertIn(RMCUP, window, "did not leave the alternate screen")
        self.assertIn(CNORM, window, "did not restore the cursor")
        self.assertNotIn(b"Traceback", window)
        out = self.sh.run("echo rc=$?")
        self.assertIn(f"rc={rc}".encode(), out)
        self.assertEqual(self.sh.stty(), before, "terminal settings changed across zoo")
        self.assertIsNone(JOB_NOTICE_RE.search(self.sh.since(mark)), "a job-control notice leaked")

    def test_q_quits_and_restores_the_terminal(self):
        before = self.sh.stty()
        self.start_zoo()
        self.sh.wait_screen("evoc")
        mark = self.sh.pos
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)
        self.assert_terminal_returned(mark, before, 0)

    def test_ctrl_c_quits_and_restores_the_terminal(self):
        before = self.sh.stty()
        self.start_zoo()
        self.sh.wait_screen("evoc")
        mark = self.sh.pos
        self.sh.send(b"\x03")
        self.sh.expect(PROMPT_RE)
        self.assert_terminal_returned(mark, before, 130)

    def test_without_term_zoo_refuses_before_touching_the_screen(self):
        mark = self.sh.pos
        self.sh.send("env -u TERM zoo\r")
        self.sh.expect(b"zoo: TERM is not set")
        self.sh.expect(PROMPT_RE)
        out = self.sh.run("echo rc=$?")
        self.assertIn(b"rc=1", out)
        self.assertNotIn(SMCUP, self.sh.since(mark))

    def test_frame_shows_states_and_hides_the_unlabelled(self):
        self.start_zoo()
        self.sh.wait_screen("evoc")
        self.sh.wait_screen("40.0")   # 100/1000 * 4 cpus: a computed delta, not "..."
        self.sh.wait_screen("Exited (0) 2 days ago")
        self.assertNotIn("sweb-eval-7", self.sh.screen)
        self.assertIn("stats 0s ago", self.sh.screen)   # the clamp itself is a unit test: stats_age
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)

    def test_help_opens_and_closes_and_interval_keys_work(self):
        self.start_zoo()
        self.sh.wait_screen("evoc")
        self.sh.send("?")
        self.sh.wait_screen("any key closes this help")
        self.assertNotIn("evoc", self.sh.screen)
        self.sh.send("x")
        self.sh.wait_screen("evoc")           # rows repainted over the help text
        self.sh.wait_screen_gone("any key closes this help")
        self.assertIn("refresh 0.2s", self.sh.screen)
        self.sh.send("+")
        self.sh.wait_screen("refresh 1.2s")
        self.sh.send("-")
        self.sh.wait_screen("refresh 0.5s")   # floored, not 0.2 again
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)

    def test_daemon_trouble_is_shown_not_blank(self):
        self.start_zoo()
        self.sh.wait_screen("evoc")
        self.sh.wait_screen("40.0")
        self.state.stats_ok = False
        self.sh.wait_screen("stale")
        self.sh.wait_screen_gone("40.0")
        self.state.down = True
        self.sh.wait_screen("daemon unreachable")
        self.sh.wait_screen_gone("primates  refresh")
        self.state.down = False
        self.state.stats_ok = True
        self.sh.wait_screen("primates  refresh")   # the title came back
        self.sh.wait_screen("40.0")
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)


class LongListTtyTest(TtyTest):
    fixture = staticmethod(fixture_long)

    def test_selection_scrolls_a_list_taller_than_the_terminal(self):
        self.start_zoo()
        self.sh.wait_screen("rows 1-21 of 40")
        self.sh.wait_screen("sess20")
        self.assertNotIn("sess21", self.sh.screen)
        self.sh.send("G")
        self.sh.wait_screen("sess39")
        self.sh.wait_screen("rows 20-40 of 40")
        self.assertNotIn("sess18", self.sh.screen)
        self.sh.send("g")
        self.sh.wait_screen("rows 1-21 of 40")
        self.sh.wait_screen_gone("sess39")
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)

    def test_resize_repaints_at_the_new_size(self):
        self.start_zoo()
        self.sh.wait_screen("rows 1-21 of 40")
        self.sh.resize(12, 50)
        self.sh.wait_screen("rows 1-9 of 40")
        self.sh.wait_screen_gone("sess20")
        self.assertTrue(all(len(line) <= 50 for line in self.sh.screen.text()))
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)

    # The base class's tests run again here against the long fixture; the two below are the
    # only ones whose expectations name the small fixture, so they are excluded.
    test_frame_shows_states_and_hides_the_unlabelled = None
    test_daemon_trouble_is_shown_not_blank = None
    test_help_opens_and_closes_and_interval_keys_work = None
    test_q_quits_and_restores_the_terminal = None
    test_ctrl_c_quits_and_restores_the_terminal = None
    test_without_term_zoo_refuses_before_touching_the_screen = None


if __name__ == "__main__":
    unittest.main()
