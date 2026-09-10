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
import subprocess
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


def has_row(screen, name):
    """A row for `name` is on screen: '<kind>  <name>  ...' regardless of column widths."""
    return any(re.match(rf"^(session|primate)\s+{re.escape(name)}(\s|$)", line) for line in screen.text())
CIVIS, CNORM = b"\x1b[?25l", b"\x1b[?25h"
PROMPT = "@Z@ "

# Stands in for the real zfuncs. The functions log their arguments and, like the real ones,
# occupy the terminal until the user is done: a read stands in for the container's shell.
ZFUNCS_STUB = """
function _primate_roster() { print -r -- codemonkey; print -r -- claude; print -r -- minion }
function primate() {
  print -r -- "primate $*" >> "$HOME/launch.log"
  printf 'STUB-PRIMATE-%s\\n' "$1"; read line; printf 'STUB-PRIMATE-EXIT\\n'
}
function primate-session() {
  print -r -- "primate-session $*" >> "$HOME/launch.log"
  printf 'STUB-SESSION-%s-%s\\n' "$1" "${2:-default}"; read line
}
"""
ZFUNCS_STUB_NO_ROSTER = """
function _primate_roster() { return 1 }
function primate() { print -r -- "primate $*" >> "$HOME/launch.log" }
"""

# Stands in for the docker CLI during a hand-off. Logs every call; `exec` behaves like an
# interactive child: it announces itself, waits for a line, echoes it back transformed (so the
# typed text and the marker differ), and exits. `read` runs in cooked mode, so ctrl-c kills it.
DOCKER_STUB = """#!/bin/sh
echo "$@" >> "$HOME/docker.log"
case "$1" in
  exec) printf 'STUB-CHILD-RUNNING\\n'; read line
        [ "$line" = fail ] && { printf 'STUB-CHILD-FAILING\\n'; exit 3; }
        printf 'STUB-CHILD-GOT-%s\\n' "$line"; exit 0 ;;
  *) exit 0 ;;
esac
"""

# Stands in for tmux via the ZOO_TMUX seam so the pty suite never touches a real server. It logs
# every argv to ZOO_TMUX_LOG and keeps opened window names in ZOO_TMUX_WINS, so list-windows
# reflects new-window and open_or_focus's focus-vs-open logic is exercised. It does NOT run the
# window's command (that is what a real tmux does; T3 covers it end to end) — here we assert that
# zoo issues the right tmux commands. Window 0 is always "zoo".
TMUX_STUB = r'''#!/bin/sh
printf '%s\n' "$*" >> "$ZOO_TMUX_LOG"
case "$1" in
  list-windows)
    printf '0\tzoo\n'
    if [ -f "$ZOO_TMUX_WINS" ]; then
      i=1
      while IFS= read -r n; do printf '%s\t%s\n' "$i" "$n"; i=$((i + 1)); done < "$ZOO_TMUX_WINS"
    fi
    ;;
  new-window)
    take=0; name=""
    for a in "$@"; do
      [ "$take" = 1 ] && { name="$a"; take=0; }
      [ "$a" = "-n" ] && take=1
    done
    printf '%s\n' "$name" >> "$ZOO_TMUX_WINS"
    ;;
esac
exit 0
'''
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

    def find(self, id_):
        return next((c for c in self.containers if c["Id"] == id_), None)

    def deletes(self):
        return [path for method, path in self.requests if method == "DELETE"]

    def starts(self):
        return [path for method, path in self.requests if method == "POST"]


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    STATS_RE = re.compile(r"^/containers/([0-9a-f]{64})/stats\?stream=false&one-shot=true$")
    INSPECT_RE = re.compile(r"^/containers/([0-9a-f]{64})/json$")
    DELETE_RE = re.compile(r"^/containers/([0-9a-f]{64})\?force=true$")

    START_RE = re.compile(r"^/containers/([0-9a-f]{64})/start$")

    def do_POST(self):
        st = self.server.state
        st.requests.append(("POST", self.path))
        m = self.START_RE.match(self.path)
        c = st.find(m.group(1)) if m else None
        if c is None:
            return self._reply(404, {"message": "No such container"})
        if c["State"] != "running":
            c["State"], c["Status"] = "running", "Up 1 second"
        self.send_response(204)
        self.end_headers()

    def do_DELETE(self):
        st = self.server.state
        st.requests.append(("DELETE", self.path))
        m = self.DELETE_RE.match(self.path)
        c = st.find(m.group(1)) if m else None
        if c is None:
            return self._reply(404, {"message": "No such container"})
        st.containers.remove(c)
        self.send_response(204)
        self.end_headers()

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
        if self.path == "/info":
            return self._reply(200, {"NCPU": 18, "MemTotal": 33596223488})
        m = self.INSPECT_RE.match(self.path)
        if m:
            c = st.find(m.group(1))
            if c is None:
                return self._reply(404, {"message": "No such container"})
            return self._reply(200, {"Id": c["Id"], "Name": c["Names"][0],
                                     "Config": {"Image": c["Image"], "Labels": c["Labels"]},
                                     "State": {"Status": c["State"], "Running": c["State"] == "running"}})
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

    def wait_until(self, pred, what, timeout=10.0):
        deadline = time.monotonic() + timeout
        while not pred(self.screen):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(f"{what} never happened on screen:\n" + "\n".join(self.screen.text()))
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
class TtyBase(unittest.TestCase):
    fixture = staticmethod(fixture_small)
    extra_env = {}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        home = pathlib.Path(self.tmp.name)
        (home / "bin").mkdir()
        os.symlink(ZOO, home / "bin" / "zoo")
        stub = home / "bin" / "docker"
        stub.write_text(DOCKER_STUB)   # only so `docker` is on PATH (cli truthy); its argv is now run by tmux
        stub.chmod(0o755)
        tmux_stub = home / "bin" / "tmux"
        tmux_stub.write_text(TMUX_STUB)
        tmux_stub.chmod(0o755)
        self.tmux_log = home / "tmux.log"
        sock = home / "d.sock"
        self.state = DaemonState(self.fixture())
        self.daemon = FakeDaemon(str(sock), self.state)
        threading.Thread(target=self.daemon.serve_forever, daemon=True).start()
        env = {
            "TERM": "xterm-256color",
            "HOME": str(home),
            "PATH": f"{home / 'bin'}:{pathlib.Path(sys.executable).parent}:/usr/bin:/bin",
            "DOCKER_HOST": f"unix://{sock}",
            "ZOO_TMUX": str(tmux_stub),
            "ZOO_TMUX_LOG": str(self.tmux_log),
            "ZOO_TMUX_WINS": str(home / "tmux.wins"),
            # These tests are zoo running as window 0 *inside* tmux, so it must not auto-wrap;
            # TMUX set is what tells it so. A real-tmux wrap is exercised in test_zoo_live.py.
            "TMUX": "/tmp/zoo-test-tmux,1,0",
        }
        for key, value in self.extra_env.items():
            env[key] = value.replace("{home}", str(home))
        self.prepare_home(home)
        self.sh = Shell(env)
        self.sh.send(f"PROMPT='{PROMPT}'\r")
        self.sh.expect(PROMPT_RE)
        # Positive proof that this shell is the kind req 27 demands, so the absence assertions
        # on job notices below mean something.
        out = self.sh.run("[[ -o monitor ]] && echo MON$((1+1))")
        self.assertIn(b"MON2", out, "job control is off in the test shell; the suite would be blind")

    def prepare_home(self, home):
        """Hook for fixtures that must exist before the shell starts (a zfuncs stub, mountinfo)."""

    def tearDown(self):
        self.sh.close()
        self.daemon.shutdown()
        self.daemon.server_close()
        self.tmp.cleanup()

    def start_zoo(self, interval="0.2"):
        # --in-tmux: these run with TMUX set (window 0 of the zoo session), which is the re-exec
        # state; without it zoo would refuse (T-F1). RealTmuxTest covers the real wrap.
        self.sh.send(f"zoo --in-tmux -i {interval}\r")
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

    def wait_for_delete(self, id_, timeout=10.0):
        deadline = time.monotonic() + timeout
        path = f"/containers/{id_}?force=true"
        while path not in self.state.deletes():
            if time.monotonic() > deadline:
                raise AssertionError(f"no DELETE for {id_[:12]}; requests: {self.state.requests[-6:]}")
            self.sh._read(0.1)

    def tmux_calls(self):
        try:
            return self.tmux_log.read_text().splitlines()
        except FileNotFoundError:
            return []

    def new_windows(self):
        """The argv lines for each `tmux new-window` zoo issued, in order."""
        return [c for c in self.tmux_calls() if c.startswith("new-window ")]

    def wait_tmux(self, needle, timeout=10.0):
        deadline = time.monotonic() + timeout
        while not any(needle in c for c in self.tmux_calls()):
            if time.monotonic() > deadline:
                raise AssertionError(f"{needle!r} never sent to tmux; calls: {self.tmux_calls()}")
            self.sh._read(0.1)

    def suspend(self, tries=5):
        """Send ctrl-z and wait for the shell's stop notice, resending if the byte did not land.

        Injecting ^Z through a pty does not always produce a SIGTSTP first time; a resend always
        works, and zoo has no signal-handling code of its own — ctrl-z is ncurses' default plus
        the shell's job control. So a resend here masks a test-harness race, not a zoo defect.
        """
        import re as _re
        for _ in range(tries):
            self.sh.send(b"\x1a")
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if _re.search(rb"suspended", self.sh.buf[self.sh.pos:]):
                    self.sh.expect(rb"suspended")
                    return
                self.sh._read(0.1)
        raise AssertionError("ctrl-z never suspended the job after %d tries" % tries)


class TtyTest(TtyBase):
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
        self.sh.send("env -u TERM zoo --in-tmux\r")
        self.sh.expect(b"zoo: TERM is not set")
        self.sh.expect(PROMPT_RE)
        out = self.sh.run("echo rc=$?")
        self.assertIn(b"rc=1", out)
        self.assertNotIn(SMCUP, self.sh.since(mark))

    def test_zoo_refuses_to_start_inside_an_existing_tmux_session(self):
        # TMUX is set for this suite; a plain `zoo` (no --in-tmux) models a user launching from
        # inside their own tmux. zoo owns its own session, so it refuses rather than half-run (T-F1).
        mark = self.sh.pos
        self.sh.send("zoo\r")
        self.sh.expect(b"already inside tmux")
        self.sh.expect(PROMPT_RE)
        out = self.sh.run("echo rc=$?")
        self.assertIn(b"rc=1", out)
        self.assertNotIn(SMCUP, self.sh.since(mark))   # never entered the alternate screen

    def test_title_shows_host_facts_and_the_running_sum(self):
        self.start_zoo()
        self.sh.wait_screen("evoc")
        self.sh.wait_screen("host 18 cpu")     # from docker /info
        self.sh.wait_screen("31.3G")           # total RAM
        self.sh.wait_screen("\u03a3")         # the running-primates sum (Σ)
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)

    def test_frame_shows_states_and_hides_the_unlabelled(self):
        self.start_zoo()
        self.sh.wait_screen("evoc")
        # A blank spacer sits between the column header (KIND ...) and the first primate row.
        text = self.sh.screen.text()
        hdr = next(i for i, l in enumerate(text) if l.startswith("KIND"))
        self.assertEqual(text[hdr + 1].strip(), "", "no blank line after the column header")
        self.assertTrue(text[hdr + 2].split()[:1] in (["session"], ["primate"]),
                        "first primate row should follow the spacer")
        self.sh.wait_screen("40.0")   # 100/1000 * 4 cpus: a computed delta, not "..."
        self.sh.wait_screen("Exited (0) 2 days ago")
        self.assertNotIn("sweb-eval-7", self.sh.screen)
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

    def test_kill_asks_first_and_removes_only_on_y(self):
        self.start_zoo()
        self.sh.wait_screen("evoc")
        self.sh.send("j")                        # build (stopped) is first; evoc second
        self.sh.send("x")
        self.sh.wait_screen("Remove session 'evoc'")
        self.sh.wait_screen("claude-home survives")
        self.sh.send("n")
        self.sh.wait_screen("kept session evoc")
        self.sh.wait_screen_gone("Remove session")
        self.assertEqual(self.state.deletes(), [])
        self.sh.send("x")
        self.sh.wait_screen("Remove session 'evoc'")
        self.sh.send("y")
        self.wait_for_delete(cid("aa"))
        self.sh.wait_screen("removed session evoc; volume claude-home kept")
        self.sh.wait_until(lambda scr: not has_row(scr, "evoc"), "the evoc row disappearing")
        self.assertEqual(self.state.deletes(), [f"/containers/{cid('aa')}?force=true"])
        self.assertIn("scratch", self.sh.screen)  # the neighbour is untouched
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)

    def test_kill_refuses_a_session_recreated_under_the_same_name(self):
        self.start_zoo()
        self.sh.wait_screen("evoc")
        self.sh.send("j")
        self.sh.send("x")
        self.sh.wait_screen("Remove session 'evoc'")
        # While the prompt waits, evoc is destroyed and recreated with a new id (spec §7.3).
        self.state.containers.remove(self.state.find(cid("aa")))
        self.state.containers.append(session("evoc", "a1"))
        self.sh.send("y")
        self.sh.wait_screen("refused: session evoc is gone")
        self.assertEqual(self.state.deletes(), [])
        self.assertIsNotNone(self.state.find(cid("a1")))
        # The new container is killable on a fresh selection, so the refusal was about the id.
        self.sh.wait_until(lambda scr: has_row(scr, "evoc"), "the recreated evoc row")
        self.sh.send("x")
        self.sh.wait_screen("Remove session 'evoc'")
        self.sh.send("y")
        self.wait_for_delete(cid("a1"))
        self.assertEqual(self.state.deletes(), [f"/containers/{cid('a1')}?force=true"])
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)

    def test_attach_opens_a_tmux_window_and_zoo_keeps_its_own(self):
        before = self.sh.stty()
        self.start_zoo()
        self.sh.wait_screen("evoc")
        self.sh.send("j")                        # evoc
        self.sh.wait_screen("a attach  e shell  x kill")
        self.sh.send("a")
        self.sh.wait_screen("opened attach-evoc")   # notice on zoo's own screen: no hand-off
        self.assertIn("KIND", self.sh.screen)       # zoo never left its list
        self.wait_tmux("new-window")
        nw = self.new_windows()[0]
        self.assertIn("-n attach-evoc", nw)
        self.assertIn(cid("aa"), nw)                # by the 64-char id
        self.assertIn("tmux new-session -A -s main", nw)
        # A second press focuses the one window, it does not open a duplicate.
        self.sh.send("a")
        self.sh.wait_screen("focused attach-evoc")
        self.assertEqual(len(self.new_windows()), 1)
        self.assertTrue(any(c.startswith("select-window ") for c in self.tmux_calls()))
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)
        self.assertEqual(self.sh.stty(), before)     # zoo owned the terminal throughout

    def test_resume_starts_a_stopped_session_then_opens_its_window(self):
        self.start_zoo()
        self.sh.wait_screen("a resume  x kill")   # build, stopped, is selected first
        self.sh.send("a")
        self.sh.wait_screen("opened attach-build")
        self.assertEqual(self.state.starts(), [f"/containers/{cid('cc')}/start"])
        nw = self.new_windows()[0]
        self.assertIn("-n attach-build", nw)
        self.assertIn(cid("cc"), nw)
        self.sh.wait_screen("Up 1 second")         # the row now shows the started container
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)

    def test_shell_opens_a_window_with_a_new_shell(self):
        self.start_zoo()
        self.sh.wait_screen("evoc")
        self.sh.send("j")
        self.sh.wait_screen("e shell")
        self.sh.send("e")
        self.sh.wait_screen("opened shell-evoc")
        nw = self.new_windows()[0]
        self.assertIn("-n shell-evoc", nw)
        self.assertIn(f"exec -it -e TERM=xterm-256color {cid('aa')} sh -c", nw)
        self.assertIn("exec zsh", nw)
        self.assertEqual(self.state.starts(), [])
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)

    def test_selection_stays_on_the_container_when_rows_change(self):
        self.start_zoo()
        self.sh.wait_screen("evoc")
        self.sh.send("j")                        # evoc
        self.sh.send("x")
        self.sh.wait_screen("Remove session 'evoc'")
        self.sh.send("n")
        self.sh.wait_screen("kept session evoc")
        self.state.containers.append(session("aardvark", "01"))   # sorts first, shifting every index
        self.sh.wait_until(lambda scr: has_row(scr, "aardvark"), "the aardvark row")
        self.sh.send("x")
        self.sh.wait_screen("Remove session 'evoc'")             # not aardvark
        self.sh.send("n")
        self.state.containers.remove(self.state.find(cid("aa")))  # evoc vanishes under the highlight
        self.sh.wait_until(lambda scr: not has_row(scr, "evoc"), "evoc disappearing")
        self.sh.send("x")
        self.sh.wait_screen("Remove session '")                   # some row, and zoo did not crash
        self.sh.send("n")
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)

    def test_a_bare_escape_does_not_quit(self):
        self.start_zoo()
        self.sh.wait_screen("evoc")
        self.sh.send(b"\x1b")
        self.sh.settle(0.5)
        self.sh.send("?")
        self.sh.wait_screen("any key closes this help")          # zoo is still here
        self.sh.send("x")
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)

    def test_ctrl_z_suspends_and_fg_resumes_the_view(self):
        # ctrl-z is ncurses' default handler plus the shell's job control; zoo adds no signal code.
        # This asserts the terminal is handed back on suspend and restored intact on fg.
        before = self.sh.stty()
        self.start_zoo()
        self.sh.wait_screen("evoc")
        mark = self.sh.pos
        self.suspend()
        self.sh.expect(PROMPT_RE)
        self.assertIn(RMCUP, self.sh.since(mark))                  # handed the screen back to the shell
        out = self.sh.run("echo SH-$((40+2))")
        self.assertIn(b"SH-42", out)                              # the shell is usable meanwhile
        self.sh.send("fg\r")
        self.sh.expect(SMCUP)
        self.sh.wait_screen("KIND")
        self.sh.wait_screen("evoc")
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)
        self.assertEqual(self.sh.stty(), before)

    def test_unoffered_keys_say_why(self):
        self.start_zoo()
        self.sh.wait_screen("a resume  x kill")   # build is stopped: no shell
        self.sh.send("e")
        self.sh.wait_screen("build is not running")
        self.assertEqual(self.new_windows(), [])
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
        self.sh.wait_screen_gone("host 18 cpu")     # the title line is overwritten by the error
        self.state.down = False
        self.state.stats_ok = True
        self.sh.wait_screen("host 18 cpu")          # the title came back
        self.sh.wait_screen("40.0")
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)


class InsideAContainerTtyTest(TtyBase):
    """zoo running inside one of the rows: the row is marked, and it can never be its own target."""
    extra_env = {"ZOO_MOUNTINFO": "{home}/mountinfo"}

    def test_own_row_is_marked_and_cannot_be_acted_on(self):
        mountinfo = pathlib.Path(self.tmp.name) / "mountinfo"
        mountinfo.write_text(
            "1250 1234 254:1 /docker/containers/" + cid("bb") + "/hostname /etc/hostname rw - ext4 /dev/vda1 rw\n")
        self.start_zoo()
        self.sh.wait_screen("scratch (here)")
        self.sh.wait_screen("x kill")            # build is selected first, and is killable
        self.sh.send("G")                        # scratch sorts last
        self.sh.wait_screen_gone("x kill")       # the footer changed for the row zoo runs in
        self.sh.send("x")
        self.sh.wait_screen("scratch is the container zoo is running in")
        self.assertEqual(self.state.deletes(), [])
        self.sh.send("a")
        self.sh.wait_screen("scratch is the container zoo is running in")
        self.assertEqual(self.new_windows(), [])
        self.sh.send("k")                        # evoc, one up: still killable
        self.sh.wait_screen("x kill")
        self.sh.send("x")
        self.sh.wait_screen("Remove session 'evoc'")
        self.sh.send("y")
        self.wait_for_delete(cid("aa"))
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)


class LaunchTtyTest(TtyBase):
    """n and s go through the zsh functions, via a stub zfuncs named by ZOO_ZFUNCS."""
    extra_env = {"ZOO_ZFUNCS": "{home}/zfuncs"}

    def prepare_home(self, home):
        (home / "zfuncs").write_text(ZFUNCS_STUB)

    def test_n_picks_an_image_and_opens_a_primate_window(self):
        before = self.sh.stty()
        self.start_zoo()
        self.sh.wait_screen("n new  s session")
        self.sh.send("n")
        self.sh.wait_screen("Start a primate: choose an image")
        for image in ("codemonkey", "claude", "minion"):
            self.sh.wait_screen(image)
        self.sh.send("j")
        self.sh.send("\r")
        self.sh.wait_screen("opened primate-claude")
        self.sh.wait_screen("KIND")                 # zoo stays on its list
        nw = self.new_windows()[0]
        self.assertIn("-n primate-claude", nw)
        self.assertIn("primate claude", nw)         # the zsh-function call the window runs
        self.assertIn(" -c ", nw)                   # started in zoo's cwd (workspace = $(pwd))
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)
        self.assertEqual(self.sh.stty(), before)

    def test_s_asks_for_a_name_then_opens_a_session_window(self):
        self.start_zoo()
        self.sh.wait_screen("n new  s session")
        self.sh.send("s")
        self.sh.wait_screen("Start a session: choose an image")
        self.sh.send("j")
        self.sh.send("\r")
        self.sh.wait_screen("Session name for claude")
        self.sh.send("scratchx\x7f")            # a typo, backspaced
        self.sh.wait_screen("  scratch_")
        self.sh.send("\r")
        self.sh.wait_screen("opened session-scratch")
        nw = self.new_windows()[0]
        self.assertIn("-n session-scratch", nw)
        self.assertIn("primate-session claude scratch", nw)
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)

    def test_the_name_prompt_takes_only_dockers_alphabet(self):
        self.start_zoo()
        self.sh.wait_screen("n new  s session")
        self.sh.send("s")
        self.sh.wait_screen("choose an image")
        self.sh.send("\r")
        self.sh.wait_screen("Session name for codemonkey")
        self.sh.send("a b'c")
        self.sh.wait_screen("  abc_")                              # space and quote never entered
        self.sh.send("\x7f\x7f\x7f-x\r")
        self.sh.wait_screen("start with a letter or digit")
        self.assertIn("Session name for codemonkey", self.sh.screen)   # the prompt is still open
        self.assertEqual(self.new_windows(), [])
        self.sh.send(b"\x1b")
        self.sh.wait_screen("launch cancelled")
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)

    def test_a_blank_name_means_the_launchers_default(self):
        self.start_zoo()
        self.sh.wait_screen("n new  s session")
        self.sh.send("s")
        self.sh.wait_screen("choose an image")
        self.sh.send("\r")                       # codemonkey, the first
        self.sh.wait_screen("Session name for codemonkey")
        self.sh.send("\r")
        self.sh.wait_screen("opened session-codemonkey")
        nw = self.new_windows()[0]
        self.assertIn("-n session-codemonkey", nw)
        self.assertTrue(nw.rstrip().endswith("primate-session codemonkey"))   # no name passed
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)

    def test_esc_cancels_the_picker_and_the_prompt(self):
        self.start_zoo()
        self.sh.wait_screen("n new  s session")
        self.sh.send("n")
        self.sh.wait_screen("choose an image")
        self.sh.send(b"\x1b")
        self.sh.wait_screen("launch cancelled")
        self.sh.wait_screen_gone("choose an image")
        self.sh.send("s")
        self.sh.wait_screen("choose an image")
        self.sh.send("\r")
        self.sh.wait_screen("Session name for codemonkey")
        self.sh.send(b"\x1b")
        self.sh.wait_screen("launch cancelled")
        self.sh.wait_screen_gone("Session name")
        self.assertEqual(self.new_windows(), [])
        self.sh.send("q")                          # and Esc did not quit zoo either time
        self.sh.expect(PROMPT_RE)


class NoRosterTtyTest(TtyBase):
    """Inside a primate, or on a host without a checkout: nothing to launch from, so no launch."""
    extra_env = {"ZOO_ZFUNCS": "{home}/zfuncs"}

    def prepare_home(self, home):
        (home / "zfuncs").write_text(ZFUNCS_STUB_NO_ROSTER)

    def test_launch_is_not_offered_and_says_why(self):
        self.start_zoo()
        self.sh.wait_screen("j/k select")
        self.assertNotIn("n new", self.sh.screen)
        self.sh.send("n")
        self.sh.wait_screen("no primate roster here")
        self.sh.send("?")
        self.sh.wait_screen("n / s             unavailable")
        self.sh.send("x")
        self.sh.wait_screen_gone("unavailable")
        self.assertEqual(self.new_windows(), [])
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)


class LongListTtyTest(TtyBase):
    fixture = staticmethod(fixture_long)

    def test_selection_scrolls_a_list_taller_than_the_terminal(self):
        self.start_zoo()
        self.sh.wait_screen("rows 1-20 of 40")   # body is h-4 now (title, header, spacer, footer)
        self.sh.wait_screen("sess19")
        self.assertNotIn("sess20", self.sh.screen)
        self.sh.send("G")
        self.sh.wait_screen("sess39")
        self.sh.wait_screen("rows 21-40 of 40")
        self.assertNotIn("sess19", self.sh.screen)
        self.sh.send("g")
        self.sh.wait_screen("rows 1-20 of 40")
        self.sh.wait_screen_gone("sess39")
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)

    def test_resize_repaints_at_the_new_size(self):
        self.start_zoo()
        self.sh.wait_screen("rows 1-20 of 40")
        self.sh.resize(12, 50)
        self.sh.wait_screen("rows 1-8 of 40")
        self.sh.wait_screen_gone("sess20")
        self.assertTrue(all(len(line) <= 50 for line in self.sh.screen.text()))
        self.sh.send("q")
        self.sh.expect(PROMPT_RE)


# A roster of one image whose primate/primate-session print a marker and stay up, so a launch
# window has observable, long-lived content without any docker.
REAL_ZFUNCS_STUB = """
function _primate_roster() { print -r -- alpha; print -r -- boom }
function primate() {
  [ "$1" = boom ] && { print -r -- BOOM-FAILED; return 7 }
  printf 'LAUNCHED-%s\\n' "$1"; exec sleep 300
}
function primate-session() { printf 'LAUNCHEDS-%s-%s\\n' "$1" "${2:-default}"; exec sleep 300 }
"""


@unittest.skipUnless(shutil.which("tmux") and shutil.which("zsh"),
                     "SKIPPED: needs tmux and zsh for the real-tmux end-to-end test")
class RealTmuxTest(unittest.TestCase):
    """The genuine article: zoo auto-wraps into a REAL tmux server (isolated by TMUX_TMPDIR so it
    never touches the developer's), opens a REAL window whose command actually runs, and ctrl-b 0
    returns to a list that is still refreshing. The stub tmux suites prove zoo issues the right
    commands; this proves those commands do what zoo expects against real tmux. No docker: the
    list comes from the fake daemon and the launch runs a stub zfuncs, so it is hermetic."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        home = pathlib.Path(self.tmp.name)
        (home / "bin").mkdir()
        os.symlink(ZOO, home / "bin" / "zoo")
        (home / "zfuncs").write_text(REAL_ZFUNCS_STUB)
        docker = home / "bin" / "docker"      # only so cli is truthy (actions offered)
        docker.write_text(DOCKER_STUB)
        docker.chmod(0o755)
        sock = home / "d.sock"
        self.state = DaemonState(fixture_small())
        self.daemon = FakeDaemon(str(sock), self.state)
        threading.Thread(target=self.daemon.serve_forever, daemon=True).start()
        self.tmuxbin = shutil.which("tmux")
        tmpdir = home / "tmxtmp"
        tmpdir.mkdir()
        self.tmux_sock = str(tmpdir / f"tmux-{os.getuid()}" / "default")
        env = {
            "TERM": "xterm-256color",
            "HOME": str(home),
            "PATH": f"{home / 'bin'}:{pathlib.Path(sys.executable).parent}:/usr/bin:/bin",
            "DOCKER_HOST": f"unix://{sock}",
            "ZOO_ZFUNCS": str(home / "zfuncs"),
            "TMUX_TMPDIR": str(tmpdir),   # zoo's `tmux new-session` lands on an isolated server
            # TMUX deliberately unset: this is the one suite that lets zoo auto-wrap for real.
        }
        self.sh = Shell(env, rows=24, cols=100)
        self.sh.send(f"PROMPT='{PROMPT}'\r")
        self.sh.expect(PROMPT_RE)

    def tearDown(self):
        self.tmux("kill-server")   # detaches the pty client and reaps the isolated server
        self.sh.close()
        self.daemon.shutdown()
        self.daemon.server_close()
        self.tmp.cleanup()

    def tmux(self, *args, timeout=10):
        return subprocess.run([self.tmuxbin, "-S", self.tmux_sock, *args],
                              capture_output=True, text=True, timeout=timeout)

    def wait_tmux_ok(self, args, needle, timeout=20):
        deadline = time.monotonic() + timeout
        while True:
            r = self.tmux(*args)
            if r.returncode == 0 and needle in r.stdout:
                return r.stdout
            if time.monotonic() > deadline:
                raise AssertionError(f"tmux {args} never showed {needle!r}: rc={r.returncode} "
                                     f"out={r.stdout!r} err={r.stderr!r}")
            self.sh._read(0.2)

    def active(self):
        """(active?, name) for zoo's windows, from the real server — the source of truth for
        which window has focus, rather than guessing from the pty screen mid-switch."""
        r = self.tmux("list-windows", "-t", "zoo", "-F", "#{window_active} #{window_name}")
        return r.stdout

    def test_autowrap_opens_a_real_window_and_ctrl_b_0_returns_to_a_live_list(self):
        self.sh.send("zoo -i 0.5\r")
        # Auto-wrap: a real tmux server comes up and the inner zoo renders window 0.
        self.sh.wait_screen("KIND", timeout=25)
        self.sh.wait_screen("evoc", timeout=25)      # list populated from the fake daemon
        self.sh.wait_screen("n new", timeout=25)     # roster present -> launch offered
        self.wait_tmux_ok(["list-sessions"], "zoo")  # the session zoo created, for real

        # Launch a primate: a real second window opens, becomes active, and its command runs.
        self.sh.send("n")
        self.sh.wait_screen("choose an image")
        self.sh.send("\r")                           # the one image, alpha
        self.wait_tmux_ok(["list-windows", "-t", "zoo", "-F", "#{window_active} #{window_name}"],
                          "1 primate-alpha")         # opened AND focused (the whole point)
        pane = self.wait_tmux_ok(["capture-pane", "-p", "-t", "zoo:primate-alpha"], "LAUNCHED-alpha")
        self.assertIn("LAUNCHED-alpha", pane)        # the zsh-function window really ran

        # ctrl-b 0 returns to zoo's window, which never stopped refreshing.
        self.sh.send(b"\x020")
        self.wait_tmux_ok(["list-windows", "-t", "zoo", "-F", "#{window_active} #{window_name}"],
                          "1 zoo")
        self.sh.wait_screen("KIND", timeout=25)
        self.sh.wait_screen("stats", timeout=25)     # the title's live age: zoo kept ticking

        # A second launch of the same image focuses the one window, not a duplicate.
        self.sh.send("n")
        self.sh.wait_screen("choose an image")
        self.sh.send("\r")
        self.wait_tmux_ok(["list-windows", "-t", "zoo", "-F", "#{window_active} #{window_name}"],
                          "1 primate-alpha")
        names = self.tmux("list-windows", "-t", "zoo", "-F", "#{window_name}").stdout.split()
        self.assertEqual(names.count("primate-alpha"), 1)   # focused, not duplicated

    def test_a_failing_launch_window_is_held_open_and_closes_on_enter(self):
        # T-F2: a window whose command exits non-zero must stay, showing the error and a prompt,
        # instead of vanishing. 'boom' returns 7 from the stub primate().
        self.sh.send("zoo -i 0.5\r")
        self.sh.wait_screen("KIND", timeout=25)
        self.sh.wait_screen("n new", timeout=25)
        self.sh.send("n")
        self.sh.wait_screen("choose an image")
        self.sh.send("j")                            # move to the second image, boom
        self.sh.send("\r")
        # The window opened, its command failed, and hold_command kept it: the pane shows the
        # failure and the prompt, and the window is still there.
        self.wait_tmux_ok(["capture-pane", "-p", "-t", "zoo:primate-boom"], "BOOM-FAILED")
        self.wait_tmux_ok(["capture-pane", "-p", "-t", "zoo:primate-boom"], "press Enter to close")
        self.assertIn("primate-boom",
                      self.tmux("list-windows", "-t", "zoo", "-F", "#{window_name}").stdout)
        # Enter closes the held window (the read returns), leaving zoo's session behind.
        self.sh.send("\r")
        import time as _t
        deadline = _t.monotonic() + 20
        while "primate-boom" in self.tmux("list-windows", "-t", "zoo", "-F", "#{window_name}").stdout:
            if _t.monotonic() > deadline:
                self.fail("held window did not close on Enter")
            self.sh._read(0.2)


if __name__ == "__main__":
    unittest.main()
