#!/usr/bin/env python3
"""tests/test_zoo_model.py — zoo's docker client, label filter, sample maths and text frame.

Hermetic: no daemon, no images, no tty, no ambient state (spec req 29). The transport seam in
bin/zoo takes a callable, so a FakeDaemon here answers the three API calls U0 makes and records
every request it receives — which lets assertions be positive ("stats were requested for exactly
these ids") rather than absences that the code doing nothing would also satisfy (spec req 31).

Run:  python3 -m unittest discover -s tests -p 'test_zoo*.py'
"""
import importlib.machinery
import importlib.util
import io
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_loader = importlib.machinery.SourceFileLoader("zoo", str(ROOT / "bin" / "zoo"))
_spec = importlib.util.spec_from_loader("zoo", _loader)
zoo = importlib.util.module_from_spec(_spec)
sys.modules["zoo"] = zoo   # dataclasses resolve the module by name while the class is built
_loader.exec_module(zoo)


def cid(prefix: str) -> str:
    """A realistic 64-character id with a recognisable prefix."""
    return (prefix + "0" * 64)[:64]


SESSION_OLD = cid("aa")     # a session from before primate.managed existed
SESSION_NEW = cid("bb")     # a session with the full label set
SESSION_STOPPED = cid("cc")
FOREGROUND = cid("dd")      # a `primate` container
EVAL = cid("ee")            # an unlabelled spark-bench eval container — must be invisible
CHROMA = cid("ff")          # something else entirely


def listing_row(id_, name, image, labels, state="running", status="Up 3 hours"):
    return {"Id": id_, "Names": ["/" + name], "Image": image, "Labels": labels,
            "State": state, "Status": status}


def fixture_listing():
    return [
        listing_row(CHROMA, "evoc-vectordb-1", "chromadb/chroma:0.5.23", {"maintainer": "x"}),
        listing_row(EVAL, "sweb-eval-7", "spark-bench:latest", {}),
        listing_row(FOREGROUND, "wonderful_kirch", "minion:latest",
                    {"primate.managed": "", "primate.image": "minion"}),
        listing_row(SESSION_NEW, "scratch", "claude:latest",
                    {"primate.managed": "", "primate.session": "", "primate.image": "claude",
                     "primate.name": "scratch"}),
        listing_row(SESSION_OLD, "evoc", "claude:latest",
                    {"primate.session": "", "primate.image": "claude", "primate.name": "evoc"}),
        listing_row(SESSION_STOPPED, "build", "claude:latest",
                    {"primate.managed": "", "primate.session": "", "primate.image": "claude",
                     "primate.name": "build"}, state="exited", status="Exited (0) 2 days ago"),
    ]


def stats_doc(cpu_total, system_cpu, online=4, usage=2_000_000, inactive_file=500_000,
              limit=8_000_000, pids=7):
    return {
        "cpu_stats": {"cpu_usage": {"total_usage": cpu_total}, "system_cpu_usage": system_cpu,
                      "online_cpus": online},
        "precpu_stats": {"cpu_usage": {"total_usage": 0}, "system_cpu_usage": 0},
        "memory_stats": {"usage": usage, "limit": limit, "stats": {"inactive_file": inactive_file}},
        "pids_stats": {"current": pids},
    }


class FakeDaemon:
    """A transport: answers the U0 calls from fixtures and logs what was asked."""

    STATS_RE = re.compile(r"^/containers/([0-9a-f]{64})/stats\?stream=false&one-shot=true$")

    def __init__(self, containers=None, stats=None):
        self.containers = fixture_listing() if containers is None else containers
        self.stats = {} if stats is None else stats   # id -> doc | callable | int (HTTP status)
        self.requests = []
        self.down = False

    def __call__(self, method, url):
        self.requests.append((method, url))
        if self.down:
            raise zoo.DockerError("connect: connection refused")
        if url == "/containers/json?all=true":
            return 200, json.dumps(self.containers).encode()
        m = self.STATS_RE.match(url)
        if m:
            entry = self.stats.get(m.group(1))
            if entry is None:
                return 404, b'{"message":"No such container"}'
            if callable(entry):
                entry = entry()
            if isinstance(entry, int):
                return entry, b'{"message":"boom"}'
            return 200, json.dumps(entry).encode()
        return 404, b'{"message":"page not found"}'

    def stats_requested_for(self):
        return [self.STATS_RE.match(u).group(1) for _, u in self.requests if self.STATS_RE.match(u)]


# --------------------------------------------------------------------------- rows


class RowsTest(unittest.TestCase):
    def test_only_labelled_containers_become_rows(self):
        rows = zoo.rows_from_listing(fixture_listing())
        ids = {r.id for r in rows}
        self.assertEqual(ids, {SESSION_OLD, SESSION_NEW, SESSION_STOPPED, FOREGROUND})
        # The trap the spec names: spark-bench is a roster image AND the image of eval containers.
        self.assertNotIn(EVAL, ids)
        self.assertNotIn(CHROMA, ids)

    def test_session_label_alone_is_still_a_session(self):
        rows = {r.id: r for r in zoo.rows_from_listing(fixture_listing())}
        self.assertEqual(rows[SESSION_OLD].kind, zoo.SESSION)
        self.assertEqual(rows[SESSION_OLD].name, "evoc")

    def test_kind_name_image_and_state_come_from_labels(self):
        rows = {r.id: r for r in zoo.rows_from_listing(fixture_listing())}
        fg = rows[FOREGROUND]
        self.assertEqual((fg.kind, fg.name, fg.image, fg.running), (zoo.PRIMATE, "wonderful_kirch", "minion", True))
        st = rows[SESSION_STOPPED]
        self.assertEqual((st.kind, st.name, st.running, st.status),
                         (zoo.SESSION, "build", False, "Exited (0) 2 days ago"))

    def test_image_falls_back_to_the_docker_image_without_a_label(self):
        row = zoo.row_from_listing(listing_row(cid("11"), "x", "kiro:latest", {"primate.managed": ""}))
        self.assertEqual(row.image, "kiro:latest")

    def test_sessions_sort_first_then_by_name(self):
        rows = zoo.rows_from_listing(fixture_listing())
        self.assertEqual([r.name for r in rows], ["build", "evoc", "scratch", "wonderful_kirch"])

    def test_a_row_without_an_id_is_an_error_not_a_row(self):
        with self.assertRaises(zoo.DockerError):
            zoo.row_from_listing({"Names": ["/x"], "Labels": {"primate.managed": ""}})
        with self.assertRaises(zoo.DockerError):
            zoo.row_from_listing({"Id": "", "Labels": {"primate.managed": ""}})


# --------------------------------------------------------------------------- samples


class SampleTest(unittest.TestCase):
    def test_parse_subtracts_inactive_file_like_docker_does(self):
        s = zoo.parse_stats(stats_doc(10, 100, usage=2_000_000, inactive_file=500_000))
        self.assertEqual(s.mem_used, 1_500_000)
        self.assertEqual((s.cpu_total, s.system_cpu, s.online_cpus, s.mem_limit, s.pids),
                         (10, 100, 4, 8_000_000, 7))

    def test_parse_accepts_cgroup_v1_field_name(self):
        doc = stats_doc(1, 2)
        doc["memory_stats"]["stats"] = {"total_inactive_file": 1_000_000}
        self.assertEqual(zoo.parse_stats(doc).mem_used, 1_000_000)

    def test_parse_tolerates_an_empty_document(self):
        s = zoo.parse_stats({})
        self.assertEqual((s.cpu_total, s.mem_used, s.pids, s.online_cpus), (0, 0, 0, 1))

    def test_cpu_percent_is_none_without_a_previous_sample(self):
        self.assertIsNone(zoo.cpu_percent(None, zoo.parse_stats(stats_doc(5, 10))))

    def test_cpu_percent_is_the_delta_scaled_by_cpus(self):
        prev = zoo.parse_stats(stats_doc(1_000_000_000, 10_000_000_000))
        cur = zoo.parse_stats(stats_doc(1_500_000_000, 14_000_000_000))  # 0.5s of 4s, 4 cpus
        self.assertAlmostEqual(zoo.cpu_percent(prev, cur), 50.0)

    def test_cpu_percent_zero_is_zero_not_none(self):
        prev = zoo.parse_stats(stats_doc(100, 1_000))
        cur = zoo.parse_stats(stats_doc(100, 2_000))
        self.assertEqual(zoo.cpu_percent(prev, cur), 0.0)

    def test_cpu_percent_refuses_a_reset_or_frozen_counter(self):
        prev = zoo.parse_stats(stats_doc(100, 1_000))
        self.assertIsNone(zoo.cpu_percent(prev, zoo.parse_stats(stats_doc(50, 2_000))))   # reset
        self.assertIsNone(zoo.cpu_percent(prev, zoo.parse_stats(stats_doc(200, 1_000))))  # no host time


# --------------------------------------------------------------------------- monitor


def moving(cpu_step=100, sys_step=1_000):
    """Counters that advance on every reading, like a live daemon's. A frozen document would
    give a zero host-time delta, which the maths (correctly) refuses to turn into a percentage."""
    reads = {"n": 0}

    def read():
        reads["n"] += 1
        return stats_doc(cpu_step * reads["n"], sys_step * reads["n"])
    return read


class MonitorTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeDaemon(stats={
            SESSION_OLD: moving(),
            SESSION_NEW: moving(),
            FOREGROUND: moving(),
        })
        self.clock = [100.0]
        self.mon = zoo.Monitor(zoo.Docker(self.fake), clock=lambda: self.clock[0])

    def test_first_tick_is_pending_second_is_live(self):
        self.mon.tick()
        fig = self.mon.figures[SESSION_OLD]
        self.assertEqual(fig.state, zoo.PENDING)
        self.assertIsNone(fig.cpu)
        self.assertEqual((fig.mem_used, fig.pids, fig.ok_at), (1_500_000, 7, 100.0))
        self.fake.stats[SESSION_OLD] = stats_doc(600, 2_000)   # after (100, 1000): 500 of 1000 on 4 cpus
        self.clock[0] = 102.0
        self.mon.tick()
        fig = self.mon.figures[SESSION_OLD]
        self.assertEqual(fig.state, zoo.LIVE)
        self.assertAlmostEqual(fig.cpu, 200.0)
        self.assertEqual(fig.ok_at, 102.0)

    def test_stats_are_requested_for_running_rows_only(self):
        self.mon.tick()
        asked = self.fake.stats_requested_for()
        self.assertEqual(sorted(asked), sorted([SESSION_OLD, SESSION_NEW, FOREGROUND]))
        self.assertEqual(self.mon.figures[SESSION_STOPPED].state, zoo.STOPPED)
        self.assertEqual(len(self.fake.requests), 4)   # one listing + three stats, nothing else

    def test_a_failed_reading_is_stale_and_keeps_the_last_numbers(self):
        self.mon.tick()
        self.fake.stats[SESSION_NEW] = 500
        self.clock[0] = 102.0
        self.mon.tick()
        fig = self.mon.figures[SESSION_NEW]
        self.assertEqual(fig.state, zoo.STALE)
        self.assertEqual((fig.mem_used, fig.pids, fig.ok_at), (1_500_000, 7, 100.0))
        self.assertIn("HTTP 500", fig.error)
        # The others were unaffected.
        self.assertEqual(self.mon.figures[SESSION_OLD].state, zoo.LIVE)

    def test_a_vanished_container_is_gone_and_a_stopped_one_has_no_stats(self):
        self.mon.tick()
        self.fake.stats[SESSION_NEW] = 404
        self.clock[0] = 102.0
        self.mon.tick()
        self.assertEqual(self.mon.figures[SESSION_NEW].state, zoo.STALE)   # listed, unreadable
        self.fake.containers = [c for c in self.fake.containers if c["Id"] != SESSION_NEW]
        self.mon.tick()
        self.assertNotIn(SESSION_NEW, self.mon.figures)
        self.assertNotIn(SESSION_NEW, [r.id for r in self.mon.rows])

    def test_a_restarted_container_starts_pending_again(self):
        self.mon.tick()
        self.mon.tick()
        self.assertEqual(self.mon.figures[FOREGROUND].state, zoo.LIVE)
        for c in self.fake.containers:
            if c["Id"] == FOREGROUND:
                c["State"] = "exited"
        self.mon.tick()
        self.assertEqual(self.mon.figures[FOREGROUND].state, zoo.STOPPED)
        for c in self.fake.containers:
            if c["Id"] == FOREGROUND:
                c["State"] = "running"
        self.mon.tick()
        self.assertEqual(self.mon.figures[FOREGROUND].state, zoo.PENDING)

    def test_a_listing_failure_keeps_rows_and_marks_them_stale(self):
        self.mon.tick()
        self.fake.down = True
        rows = self.mon.tick()
        self.assertEqual([r.id for r in rows], [r.id for r in self.mon.rows])
        self.assertEqual(len(rows), 4)
        self.assertIn("connection refused", self.mon.error)
        self.assertEqual(self.mon.figures[SESSION_OLD].state, zoo.STALE)
        self.assertEqual(self.mon.figures[SESSION_STOPPED].state, zoo.STOPPED)
        self.fake.down = False
        self.mon.tick()
        self.assertEqual(self.mon.error, "")
        self.assertEqual(self.mon.figures[SESSION_OLD].state, zoo.LIVE)


# --------------------------------------------------------------------------- layout


class LayoutTest(unittest.TestCase):
    def figures(self):
        return {
            SESSION_OLD: zoo.Figures(zoo.LIVE, cpu=12.34, mem_used=1_803_538_432, mem_limit=33_596_223_488, pids=68),
            SESSION_NEW: zoo.Figures(zoo.PENDING, mem_used=1_000, mem_limit=2_048, pids=3),
            SESSION_STOPPED: zoo.Figures(zoo.STOPPED),
            FOREGROUND: zoo.Figures(zoo.STALE, mem_used=1_000, mem_limit=2_048, pids=3, error="x"),
        }

    def test_every_state_reads_differently(self):
        cells = {r.name: zoo._cells(r, self.figures()[r.id]) for r in zoo.rows_from_listing(fixture_listing())}
        self.assertEqual(cells["evoc"][4:], ("12.3", "1.7G/31.3G", "68"))        # live
        self.assertEqual(cells["scratch"][4:], ("...", "1000B/2.0K", "3"))       # pending: not 0.0
        self.assertEqual(cells["build"][4:], ("-", "-", "-"))                    # stopped
        self.assertEqual(cells["wonderful_kirch"][4:], ("stale", "1000B/2.0K?", "3?"))  # stale

    def test_frame_has_a_header_and_one_line_per_row(self):
        lines = zoo.layout(zoo.rows_from_listing(fixture_listing()), self.figures(), 120)
        self.assertEqual(len(lines), 5)
        self.assertEqual(lines[0].split(), list(zoo.COLUMNS))
        self.assertIn("evoc", lines[2])

    def test_frame_never_exceeds_the_width(self):
        rows = zoo.rows_from_listing(fixture_listing())
        for width in (120, 60, 40, 20):
            for line in zoo.layout(rows, self.figures(), width):
                self.assertLessEqual(len(line), width, f"width {width}: {line!r}")
        narrow = zoo.layout(rows, self.figures(), 40)
        self.assertIn("~", "".join(narrow))   # something was visibly truncated, not dropped
        self.assertTrue(any("evoc" in line for line in narrow))

    def test_human_bytes(self):
        self.assertEqual(zoo.human_bytes(0), "0B")
        self.assertEqual(zoo.human_bytes(1023), "1023B")
        self.assertEqual(zoo.human_bytes(1536), "1.5K")
        self.assertEqual(zoo.human_bytes(31_290_000_000), "29.1G")


# --------------------------------------------------------------------------- socket + cli


class SocketPathTest(unittest.TestCase):
    def test_docker_host_unix_wins(self):
        self.assertEqual(zoo.socket_path({"DOCKER_HOST": "unix:///tmp/d.sock"}, exists=lambda p: False),
                         "/tmp/d.sock")

    def test_docker_host_tcp_is_refused(self):
        with self.assertRaises(zoo.DockerError):
            zoo.socket_path({"DOCKER_HOST": "tcp://1.2.3.4:2375"}, exists=lambda p: True)

    def test_first_existing_default_is_used(self):
        env = {"HOME": "/Users/x"}
        self.assertEqual(zoo.socket_path(env, exists=lambda p: p == "/Users/x/.docker/run/docker.sock"),
                         "/Users/x/.docker/run/docker.sock")
        self.assertEqual(zoo.socket_path(env, exists=lambda p: True), "/var/run/docker.sock")

    def test_no_socket_is_an_error(self):
        with self.assertRaises(zoo.DockerError):
            zoo.socket_path({"HOME": "/h"}, exists=lambda p: False)


class OnceTest(unittest.TestCase):
    def run_main(self, argv, fake):
        out, err = io.StringIO(), io.StringIO()
        rc = zoo.main(argv, stdout=out, stderr=err, environ={}, transport=fake, sleep=lambda s: None)
        return rc, out.getvalue(), err.getvalue()

    def test_once_prints_a_frame_with_real_cpu(self):
        fake = FakeDaemon(stats={SESSION_OLD: moving(), SESSION_NEW: moving(), FOREGROUND: moving()})
        rc, out, err = self.run_main(["--once", "--width", "100"], fake)
        self.assertEqual((rc, err), (0, ""))
        lines = out.splitlines()
        self.assertEqual(lines[0].split(), list(zoo.COLUMNS))
        evoc = next(l for l in lines if "evoc" in l)
        self.assertIn("40.0", evoc)          # 100/1000 * 4 cpus: a delta, not "..."
        self.assertNotIn("...", evoc)
        self.assertEqual(len(fake.stats_requested_for()), 6)   # two readings each

    def test_once_distinguishes_failure_from_nothing(self):
        fake = FakeDaemon(containers=[])
        rc, out, err = self.run_main(["--once"], fake)
        self.assertEqual((rc, out, err), (0, "No primates.\n", ""))
        fake.down = True
        rc, out, err = self.run_main(["--once"], fake)
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("zoo: cannot list containers", err)

    def test_no_socket_is_reported_not_traced(self):
        out, err = io.StringIO(), io.StringIO()
        rc = zoo.main(["--once"], stdout=out, stderr=err, environ={"DOCKER_HOST": "unix:///nonexistent/zoo.sock"})
        self.assertEqual((rc, out.getvalue()), (1, ""))
        self.assertIn("zoo: cannot list containers", err.getvalue())

    def test_interactive_mode_is_declared_missing_in_u0(self):
        rc, out, err = self.run_main([], FakeDaemon())
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("not built yet", err)


if __name__ == "__main__":
    unittest.main()
