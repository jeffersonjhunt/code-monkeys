#!/usr/bin/env python3
"""xc-shot — screenshot the running app into the project (default build/shots/).

  ios-sim  the booted simulator's screen. The status bar is pinned (9:41, full battery) so shots
           compare across runs; --appearance switches light/dark for the shot and restores the
           previous appearance afterwards.
  macos    only the app's own window (never the rest of the desktop). Needs the Screen Recording
           permission for the SSH server (sshd-keygen-wrapper); without it the window server
           hides other apps' windows from SSH sessions, and this exits 2 with the fix.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xc_common as xc  # noqa: E402

# $1 udid, $2 out path, $3 appearance ("" to leave)
SHOT = r"""
udid="$1"; out="$2"; look="$3"
mkdir -p "$(dirname "$out")"
prev=""
if [ -n "$look" ]; then
  # Appearance is simulator-wide and sticky: remember it and put it back after the shot.
  prev=$(xcrun simctl ui "$udid" appearance 2>/dev/null || true)
  xcrun simctl ui "$udid" appearance "$look"; sleep 1
fi
xcrun simctl status_bar "$udid" override --time 9:41 --batteryState charged --batteryLevel 100 >/dev/null 2>&1 || true
xcrun simctl io "$udid" screenshot --type=png "$out" >/dev/null 2>&1 || true
if [ -n "$prev" ] && [ "$prev" != "$look" ]; then xcrun simctl ui "$udid" appearance "$prev" || true; fi
[ -s "$out" ] && echo "OK=yes" || echo "OK=no"
"""


# $1 helper, $2 app, $3 executable, $4 out
MAC_SHOT = r"""
helper="$HOME/$1"; bin="$2/Contents/MacOS/$3"; out="$4"
if [ "$("$helper" preflight)" != "granted" ]; then echo "ACCESS=denied"; exit 0; fi
pid=$(pgrep -f "$(proc_re "$bin")" | head -1 || true)
[ -n "$pid" ] || { echo "PID="; exit 0; }
echo "PID=$pid"
wid=""; i=0
while [ -z "$wid" ] && [ "$i" -lt 25 ]; do       # the window may still be opening
  wid=$("$helper" window "$pid" || true); i=$((i + 1)); [ -z "$wid" ] && sleep 0.2
done
[ -n "$wid" ] || { echo "WINDOW="; exit 0; }
echo "WINDOW=$wid"
mkdir -p "$(dirname "$out")"
screencapture -x -o -l"$wid" "$out"
[ -s "$out" ] && echo "OK=yes" || echo "OK=no"
"""


def shot_macos(root, args):
    if args.appearance:
        raise xc.XcError("--appearance is simulator-only (on macOS it would change the whole Mac)")
    build = xc.read_state(root, "build-macos")
    if not build or not build.get("app"):
        raise xc.XcError("no successful macos build recorded", fix="run xc-build.py --platform macos first")
    exe = build.get("executable") or Path(build["app"]).stem
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = Path(args.out).resolve() if args.out else (Path(root) / "build" / "shots" / f"{stamp}-macos.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    helper = xc.ensure_xcwin()
    r = xc.remote(xc.PROC_RE_FN + MAC_SHOT, [helper, build["app"], exe, xc.host_path(out)], timeout=120)
    if r.returncode != 0:
        raise xc.XcError(f"screenshot failed: {r.stderr.strip()[-500:]}")
    f = dict(ln.split("=", 1) for ln in r.stdout.splitlines() if "=" in ln)
    if f.get("ACCESS") == "denied":
        raise xc.XcError("the SSH session may not record the screen", code=xc.EXIT_ENV,
                         fix=xc.SCREEN_RECORDING_FIX)
    if not f.get("PID"):
        raise xc.XcError(f"{build['bundle_id']} is not running", fix="run xc-run.py --platform macos first")
    if not f.get("WINDOW"):
        raise xc.XcError(f"{build['bundle_id']} (pid {f['PID']}) has no on-screen window to capture")
    if f.get("OK") != "yes":
        raise xc.XcError("screencapture wrote no image")
    xc.emit({"ok": True, "platform": "macos", "pid": f["PID"], "window": f["WINDOW"], "file": str(out)})
    print(f"✓ {out}", file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", default="ios-sim", choices=["ios-sim", "macos"])
    ap.add_argument("--device", help="simulator name or UDID (ios-sim; default: the one xc-run last used)")
    ap.add_argument("--appearance", choices=["light", "dark"], help="switch the simulator's appearance first")
    ap.add_argument("--out", help="output .png (default: build/shots/<time>-<device>.png)")
    ap.add_argument("--project-dir", default=".")
    args = ap.parse_args()

    root = xc.find_project_root(args.project_dir)
    if args.platform == "macos":
        return shot_macos(root, args)
    want = args.device
    if not want:
        last = xc.read_state(root, "run-ios-sim")
        want = last.get("udid") if last else None
    sim = xc.pick_simulator(xc.remote("xcrun simctl list devices available -j").stdout, want)
    if sim.get("state") != "Booted":
        raise xc.XcError(f"simulator {sim['name']} is not booted", fix="run xc-run.py --platform ios-sim first")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = Path(args.out).resolve() if args.out else (
        Path(root) / "build" / "shots" / f"{stamp}-{sim['name'].replace(' ', '-')}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    r = xc.remote(SHOT, [sim["udid"], xc.host_path(out), args.appearance or ""], timeout=120)
    if r.returncode != 0 or "OK=yes" not in r.stdout:
        raise xc.XcError(f"screenshot failed: {r.stderr.strip()[-500:] or 'no image written'}")
    xc.emit({"ok": True, "device": sim["name"], "udid": sim["udid"], "file": str(out)})
    print(f"✓ {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    xc.run_main(main)
