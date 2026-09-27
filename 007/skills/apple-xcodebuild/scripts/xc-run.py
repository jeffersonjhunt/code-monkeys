#!/usr/bin/env python3
"""xc-run — launch (or stop) the app xc-build.py last built, on an iOS simulator or on the Mac.

The app and its bundle id come from build/xc/build-<platform>.json — the exact product of the
last successful build — never from searching for "some .app".

  ios-sim  pick a simulator (--device name/UDID, else the newest runtime's iPhone), boot it and
           WAIT for boot to finish, install, launch, bring Simulator.app forward.
  macos    `open` the bundle (LaunchServices — required for TCC prompts and a proper app
           activation), then confirm the process is up.

After launch the process is re-checked after --settle seconds, so a crash on launch is reported
as a failure rather than a successful "launched". --logs N captures N seconds of the app's
unified log into build/logs/.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xc_common as xc  # noqa: E402

# $1 udid, $2 app, $3 bundle id, $4 settle seconds, $5 log seconds, $6 log path, $7 executable
SIM_RUN = r"""
udid="$1"; app="$2"; bid="$3"; settle="$4"; logsecs="$5"; log="$6"; exe="$7"
xcrun simctl boot "$udid" 2>/dev/null || true
xcrun simctl bootstatus "$udid" -b >/dev/null
xcrun simctl install "$udid" "$app"
xcrun simctl terminate "$udid" "$bid" >/dev/null 2>&1 || true
out=$(xcrun simctl launch "$udid" "$bid")
pid=${out##*: }
echo "PID=$pid"
open -a Simulator >/dev/null 2>&1 || true
if [ "$logsecs" -gt 0 ]; then
  mkdir -p "$(dirname "$log")"
  xcrun simctl spawn "$udid" log stream --style compact --predicate "process == \"$exe\"" >"$log" 2>&1 &
  lp=$!; sleep "$logsecs"; kill "$lp" 2>/dev/null || true
fi
sleep "$settle"
if xcrun simctl spawn "$udid" launchctl list 2>/dev/null | grep -q "UIKitApplication:$bid"; then
  echo "RUNNING=yes"
else
  echo "RUNNING=no"
fi
"""

SIM_STOP = r"""
xcrun simctl terminate "$1" "$2" >/dev/null 2>&1 && echo "STOPPED=yes" || echo "STOPPED=no"
"""

# $1 app, $2 settle seconds, $3 log seconds, $4 log path, $5 executable
MAC_RUN = r"""
app="$1"; settle="$2"; logsecs="$3"; log="$4"; exe="$5"
bin="$app/Contents/MacOS/$exe"
pkill -f "^$bin" 2>/dev/null || true
if [ "$logsecs" -gt 0 ]; then
  mkdir -p "$(dirname "$log")"
  log stream --style compact --predicate "process == \"$exe\"" >"$log" 2>&1 &
  lp=$!
fi
open "$app"
pid=""
i=0
while [ -z "$pid" ] && [ "$i" -lt 50 ]; do
  pid=$(pgrep -f "^$bin" | head -1 || true); i=$((i + 1)); [ -z "$pid" ] && sleep 0.2
done
echo "PID=$pid"
[ "$logsecs" -gt 0 ] && { sleep "$logsecs"; kill "$lp" 2>/dev/null || true; }
sleep "$settle"
if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then echo "RUNNING=yes"; else echo "RUNNING=no"; fi
"""

MAC_STOP = r"""
bin="$1/Contents/MacOS/$2"
pkill -f "^$bin" 2>/dev/null && echo "STOPPED=yes" || echo "STOPPED=no"
"""


def facts(stdout):
    return dict(ln.split("=", 1) for ln in stdout.splitlines() if "=" in ln and ln.split("=", 1)[0].isupper())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", required=True, choices=["ios-sim", "macos"])
    ap.add_argument("--device", help="simulator name or UDID (ios-sim)")
    ap.add_argument("--stop", action="store_true", help="terminate the app instead of launching it")
    ap.add_argument("--logs", type=int, default=0, metavar="SECONDS", help="capture N seconds of app logs")
    ap.add_argument("--settle", type=int, default=2, metavar="SECONDS",
                    help="wait before confirming the app is still running (default 2)")
    ap.add_argument("--project-dir", default=".")
    args = ap.parse_args()

    root = xc.find_project_root(args.project_dir)
    build = xc.read_state(root, f"build-{args.platform}")
    if not build or not build.get("app"):
        raise xc.XcError(f"no successful {args.platform} build recorded",
                         fix=f"run xc-build.py --platform {args.platform} first")
    app, bid, exe = build["app"], build["bundle_id"], build.get("executable") or Path(build["app"]).stem
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log_local = Path(root) / "build" / "logs" / f"{stamp}-run-{args.platform}.log"
    result = {"platform": args.platform, "app": app, "bundle_id": bid}

    if args.platform == "ios-sim":
        sim = xc.pick_simulator(xc.remote("xcrun simctl list devices available -j").stdout, args.device)
        result.update(device=sim["name"], udid=sim["udid"])
        if args.stop:
            f = facts(xc.remote(SIM_STOP, [sim["udid"], bid]).stdout)
            result.update(ok=True, stopped=f.get("STOPPED") == "yes")
            xc.emit(result)
            return 0
        xc.log(f"launching {bid} on {sim['name']} ({sim['udid']})")
        r = xc.remote(SIM_RUN, [sim["udid"], app, bid, args.settle, args.logs,
                                xc.host_path(log_local) if args.logs else "", exe], timeout=600)
    else:
        if args.stop:
            f = facts(xc.remote(MAC_STOP, [app, exe]).stdout)
            result.update(ok=True, stopped=f.get("STOPPED") == "yes")
            xc.emit(result)
            return 0
        xc.log(f"opening {app}")
        r = xc.remote(MAC_RUN, [app, args.settle, args.logs,
                                xc.host_path(log_local) if args.logs else "", exe], timeout=600)

    if r.returncode != 0:
        raise xc.XcError(f"launch failed (exit {r.returncode}): {r.stderr.strip()[-800:]}")
    f = facts(r.stdout)
    running = f.get("RUNNING") == "yes"
    result.update(ok=running, pid=f.get("PID") or None, running=running)
    if not running:
        result["reason"] = f"the app was not running {args.settle}s after launch (crashed or quit)"
    if args.logs:
        result["log"] = str(log_local)
        if log_local.exists():
            result["log_tail"] = log_local.read_text(errors="replace").splitlines()[-15:]
    xc.write_state(root, f"run-{args.platform}", result)
    xc.emit(result)
    print(("✓ running" if running else f"✗ {result['reason']}") + f" — {bid}", file=sys.stderr)
    return 0 if running else xc.EXIT_FAIL


if __name__ == "__main__":
    xc.run_main(main)
