#!/usr/bin/env python3
"""xc-shot — screenshot the iOS simulator running the app, into the project (default build/shots/).

iOS simulator only. A macOS window cannot be captured over SSH: the SSH session is outside the
logged-in GUI (Aqua) session, so the window server lists no windows to it, and switching into
that session (`launchctl asuser`) needs root. Asking for macos exits 2 with that reason rather
than producing a blank or wallpaper-only image.

Optionally set the simulator's appearance and orientation-independent status bar first, so shots
are comparable across runs.
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
if [ -n "$look" ]; then xcrun simctl ui "$udid" appearance "$look"; sleep 1; fi
xcrun simctl status_bar "$udid" override --time 9:41 --batteryState charged --batteryLevel 100 >/dev/null 2>&1 || true
xcrun simctl io "$udid" screenshot --type=png "$out" >/dev/null 2>&1
[ -s "$out" ] && echo "OK=yes" || echo "OK=no"
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", default="ios-sim", choices=["ios-sim", "macos"])
    ap.add_argument("--device", help="simulator name or UDID (default: the one xc-run last used)")
    ap.add_argument("--appearance", choices=["light", "dark"], help="switch the simulator's appearance first")
    ap.add_argument("--out", help="output .png (default: build/shots/<time>-<device>.png)")
    ap.add_argument("--project-dir", default=".")
    args = ap.parse_args()

    if args.platform == "macos":
        raise xc.XcError(
            "macOS window screenshots are not possible over SSH (no GUI session access without root)",
            code=xc.EXIT_ENV,
            fix="take it on the Mac (⌘⇧4, space, click the window), or verify macOS layout with UI tests",
        )
    root = xc.find_project_root(args.project_dir)
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
