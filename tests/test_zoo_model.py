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


def inspect_doc(c):
    """/containers/{id}/json, from a listing row: the fields zoo reads."""
    return {"Id": c["Id"], "Name": c["Names"][0],
            "Config": {"Image": c["Image"], "Labels": c["Labels"]},
            "State": {"Status": c["State"], "Running": c["State"] == "running"}}


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

    INSPECT_RE = re.compile(r"^/containers/([0-9a-f]{64})/json$")
    DELETE_RE = re.compile(r"^/containers/([0-9a-f]{64})\?force=true$")

    def find(self, id_):
        return next((c for c in self.containers if c["Id"] == id_), None)

    def __call__(self, method, url):
        self.requests.append((method, url))
        if self.down:
            raise zoo.DockerError("connect: connection refused")
        if url == "/containers/json?all=true":
            return 200, json.dumps(self.containers).encode()
        m = self.INSPECT_RE.match(url)
        if m:
            c = self.find(m.group(1))
            if c is None:
                return 404, b'{"message":"No such container"}'
            return 200, json.dumps(inspect_doc(c)).encode()
        m = self.DELETE_RE.match(url)
        if m and method == "DELETE":
            c = self.find(m.group(1))
            if c is None:
                return 404, b'{"message":"No such container"}'
            self.containers.remove(c)
            return 204, b""
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


# --------------------------------------------------------------------------- identity


MOUNTINFO_IN_CONTAINER = (
    "1234 1000 0:200 / / rw,relatime - overlay overlay rw,lowerdir=/var/lib/docker/overlay2/l/ABC,"
    "upperdir=/var/lib/docker/overlay2/" + "f" * 64 + "/diff\n"
    "1250 1234 254:1 /docker/containers/" + SESSION_NEW + "/hostname /etc/hostname rw - ext4 /dev/vda1 rw\n"
    "1251 1234 254:1 /docker/containers/" + SESSION_NEW + "/hosts /etc/hosts rw - ext4 /dev/vda1 rw\n"
)
MOUNTINFO_ON_HOST = (
    "25 30 0:23 / /sys rw,nosuid - sysfs sysfs rw\n"
    "300 25 254:1 /var/lib/docker/overlay2/" + "e" * 64 + "/merged /mnt rw - ext4 /dev/vda1 rw\n"
)


class IdentityTest(unittest.TestCase):
    def test_self_id_comes_from_the_containers_path_only(self):
        self.assertEqual(zoo.self_container_id(MOUNTINFO_IN_CONTAINER), SESSION_NEW)
        # A layer id is also 64 hex characters; it must not be mistaken for the container.
        self.assertEqual(zoo.self_container_id(MOUNTINFO_ON_HOST), "")
        self.assertEqual(zoo.self_container_id(""), "")

    def test_reading_a_missing_mountinfo_is_a_host(self):
        self.assertEqual(zoo.read_self_container_id("/nonexistent/zoo/mountinfo"), "")

    def test_the_own_row_is_marked_and_offers_nothing(self):
        rows = {r.id: r for r in zoo.rows_from_listing(fixture_listing())}
        lines = zoo.layout(list(rows.values()), {}, 120, self_id=SESSION_NEW)
        self.assertTrue(any("scratch (here)" in l for l in lines))
        self.assertFalse(any("evoc (here)" in l for l in lines))
        self.assertEqual(zoo.actions_for(rows[SESSION_NEW], SESSION_NEW), [])
        self.assertEqual(zoo.actions_for(rows[SESSION_OLD], SESSION_NEW), [("x", "kill")])
        self.assertEqual(zoo.actions_for(None, SESSION_NEW), [])
        # An empty self id is a host: it matches nothing, rather than everything.
        self.assertEqual(zoo.actions_for(rows[SESSION_NEW], ""), [("x", "kill")])
        self.assertFalse(any("(here)" in l for l in zoo.layout(list(rows.values()), {}, 120, self_id="")))


class VerifyTargetTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeDaemon()
        self.docker = zoo.Docker(self.fake)
        self.rows = {r.id: r for r in zoo.rows_from_listing(fixture_listing())}

    def test_a_live_unchanged_target_verifies(self):
        fresh = zoo.verify_target(self.docker, self.rows[SESSION_OLD], "")
        self.assertEqual((fresh.id, fresh.kind, fresh.name), (SESSION_OLD, zoo.SESSION, "evoc"))
        self.assertIn(("GET", f"/containers/{SESSION_OLD}/json"), self.fake.requests)

    def refusal(self, row, self_id=""):
        with self.assertRaises(zoo.Refusal) as ctx:
            zoo.verify_target(self.docker, row, self_id)
        return str(ctx.exception)

    def test_refuses_the_container_zoo_runs_in(self):
        msg = self.refusal(self.rows[SESSION_NEW], self_id=SESSION_NEW)
        self.assertIn("zoo is running in", msg)
        self.assertNotIn(("GET", f"/containers/{SESSION_NEW}/json"), self.fake.requests)

    def test_refuses_a_gone_container(self):
        self.fake.containers = [c for c in self.fake.containers if c["Id"] != SESSION_OLD]
        self.assertIn("is gone", self.refusal(self.rows[SESSION_OLD]))

    def test_refuses_when_the_labels_are_gone(self):
        self.fake.find(SESSION_OLD)["Labels"] = {}
        self.assertIn("no longer labelled", self.refusal(self.rows[SESSION_OLD]))

    def test_refuses_a_renamed_container(self):
        self.fake.find(SESSION_OLD)["Names"] = ["/other"]
        self.fake.find(SESSION_OLD)["Labels"]["primate.name"] = "other"
        self.assertIn("now named other", self.refusal(self.rows[SESSION_OLD]))

    def test_refuses_a_kind_change(self):
        # SESSION_NEW keeps primate.managed, so it is still a primate — just not a session now.
        del self.fake.find(SESSION_NEW)["Labels"]["primate.session"]
        self.assertIn("now a primate", self.refusal(self.rows[SESSION_NEW]))

    def test_refuses_when_the_daemon_cannot_answer(self):
        self.fake.down = True
        self.assertIn("cannot verify", self.refusal(self.rows[SESSION_OLD]))

    def test_refuses_an_unusable_row(self):
        row = zoo.Row(id="", kind=zoo.SESSION, name="x", image="i", running=True, status="")
        self.assertIn("nothing usable", self.refusal(row))


class KillTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeDaemon()
        self.docker = zoo.Docker(self.fake)
        self.rows = {r.id: r for r in zoo.rows_from_listing(fixture_listing())}

    def deletes(self):
        return [u for m, u in self.fake.requests if m == "DELETE"]

    def test_kill_removes_exactly_the_verified_id(self):
        msg = zoo.kill(self.docker, self.rows[SESSION_OLD], "")
        self.assertEqual(self.deletes(), [f"/containers/{SESSION_OLD}?force=true"])
        self.assertIsNone(self.fake.find(SESSION_OLD))
        self.assertEqual(msg, "removed session evoc; volume claude-home kept")

    def test_a_recreated_name_is_not_killed_in_its_place(self):
        stale = self.rows[SESSION_OLD]
        self.fake.containers.remove(self.fake.find(SESSION_OLD))
        self.fake.containers.append(listing_row(cid("a1"), "evoc", "claude:latest",
                                                {"primate.session": "", "primate.image": "claude",
                                                 "primate.name": "evoc"}))
        with self.assertRaises(zoo.Refusal):
            zoo.kill(self.docker, stale, "")
        self.assertEqual(self.deletes(), [])
        self.assertIsNotNone(self.fake.find(cid("a1")))

    def test_kill_refuses_self_before_asking_the_daemon(self):
        with self.assertRaises(zoo.Refusal):
            zoo.kill(self.docker, self.rows[SESSION_NEW], SESSION_NEW)
        self.assertEqual(self.fake.requests, [])

    def test_confirm_text_says_what_dies_and_what_survives(self):
        text = zoo.confirm_kill_text(self.rows[SESSION_OLD])
        self.assertIn("session 'evoc'", text)
        self.assertIn("tmux server", text)
        self.assertIn("claude-home survives", text)
        text = zoo.confirm_kill_text(self.rows[FOREGROUND])
        self.assertIn("primate 'wonderful_kirch'", text)
        self.assertIn("loses its shell", text)
        self.assertIn("minion-home survives", text)
        text = zoo.confirm_kill_text(self.rows[SESSION_STOPPED])
        self.assertIn("stopped session 'build'", text)
        self.assertIn("no longer be resumed", text)

    def test_footer_lists_only_offered_keys(self):
        self.assertTrue(zoo.footer_text([("x", "kill")]).startswith("x kill  "))
        self.assertNotIn("kill", zoo.footer_text([]))


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

    def test_interval_has_a_floor(self):
        rc, out, err = self.run_main(["-i", "0.01", "--once"], FakeDaemon())
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("--interval", err)


class InteractiveRefusalTest(unittest.TestCase):
    """The curses view itself is exercised through a pty in test_zoo_tty.py; here only the two
    refusals that must happen before curses is touched (spec req 28: TERM set and unset)."""

    def run_main(self, environ):
        out, err = io.StringIO(), io.StringIO()
        rc = zoo.main([], stdin=io.StringIO(), stdout=out, stderr=err, environ=environ,
                      transport=FakeDaemon())
        return rc, out.getvalue(), err.getvalue()

    def test_no_term_is_refused_before_curses(self):
        rc, out, err = self.run_main({})
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("TERM is not set", err)

    def test_no_tty_is_refused_before_curses(self):
        rc, out, err = self.run_main({"TERM": "xterm-256color"})
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("needs a terminal", err)


class AgedTest(unittest.TestCase):
    def test_an_old_reading_is_shown_stale_even_if_nothing_failed(self):
        figs = {
            "fresh": zoo.Figures(zoo.LIVE, cpu=1.0, mem_used=1, mem_limit=2, pids=3, ok_at=99.0),
            "old": zoo.Figures(zoo.LIVE, cpu=1.0, mem_used=1, mem_limit=2, pids=3, ok_at=90.0),
            "pending-old": zoo.Figures(zoo.PENDING, mem_used=1, mem_limit=2, pids=3, ok_at=90.0),
            "stopped": zoo.Figures(zoo.STOPPED),
        }
        shown = zoo.aged(figs, now=100.0, stale_after=4.0)
        self.assertEqual(shown["fresh"].state, zoo.LIVE)
        self.assertEqual(shown["old"].state, zoo.STALE)
        self.assertEqual((shown["old"].mem_used, shown["old"].pids), (1, 3))   # numbers kept
        self.assertIn("10s ago", shown["old"].error)
        self.assertEqual(shown["pending-old"].state, zoo.STALE)
        self.assertEqual(shown["stopped"].state, zoo.STOPPED)
        self.assertEqual(figs["old"].state, zoo.LIVE)   # the monitor's own record is untouched

    def test_title_drops_optional_parts_before_the_row_indicator(self):
        full = zoo.title_text(40, 0, 21, 0.2, 3.0, 120)
        self.assertEqual(full, "zoo  40 primates  rows 1-21 of 40  refresh 0.2s  stats 3s ago")
        self.assertEqual(zoo.title_text(40, 0, 21, 0.2, 3.0, 50), "zoo  40 primates  rows 1-21 of 40  refresh 0.2s")
        self.assertEqual(zoo.title_text(40, 0, 21, 0.2, 3.0, 40), "zoo  40 primates  rows 1-21 of 40")
        self.assertEqual(zoo.title_text(40, 19, 21, 0.2, 3.0, 20), "zoo  40 primates  rows 20-40 of 40")  # never dropped
        self.assertEqual(zoo.title_text(1, 0, 21, 2.0, None, 80), "zoo  1 primate  refresh 2s")
        self.assertEqual(zoo.title_text(0, 0, 21, 2.0, None, 80), "zoo  0 primates  refresh 2s")

    def test_stats_age_is_the_newest_reading_or_none(self):
        self.assertIsNone(zoo.stats_age({}, 100.0))
        self.assertIsNone(zoo.stats_age({"a": zoo.Figures(zoo.STOPPED)}, 100.0))
        figs = {"a": zoo.Figures(zoo.LIVE, ok_at=90.0), "b": zoo.Figures(zoo.LIVE, ok_at=97.0)}
        self.assertEqual(zoo.stats_age(figs, 100.0), 3.0)
        self.assertEqual(zoo.stats_age(figs, 96.5), 0.0)   # a reading newer than the clock is 0, not -0


if __name__ == "__main__":
    unittest.main()
