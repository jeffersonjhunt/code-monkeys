#!/usr/bin/env python3
"""xc-build — build an Xcode project on the Mac over SSH, for iOS Simulator, iOS device or macOS.

Regenerates the project from project.yml (XcodeGen, cached on the Mac) when there is one, runs
xcodebuild with its real exit status, writes the full log to build/logs/, and records the built
app (path + bundle id, straight from the build settings) in build/xc/build-<platform>.json so
xc-run never has to guess which .app to launch.

--platform all builds every platform the scheme supports (from SUPPORTED_PLATFORMS).
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xc_common as xc  # noqa: E402

DESTINATIONS = {
    "ios-sim": "generic/platform=iOS Simulator",
    "ios-device": "generic/platform=iOS",
    "macos": "platform=macOS",
}

# Remote: $1 = log path, $2.. = xcodebuild argv. Prints RC=<n>, then the app's build settings.
BUILD = r"""
log="$1"; shift
mkdir -p "$(dirname "$log")"
set +e
xcodebuild "$@" build >"$log" 2>&1
rc=$?
set -e
echo "RC=$rc"
if [ "$rc" -eq 0 ]; then
  echo '---SETTINGS---'
  xcodebuild "$@" -showBuildSettings -json 2>/dev/null
fi
"""

def build_one(root, base_args, platform, config, team, extra_settings=(), adhoc=False):
    signing = xc.signing_settings(root, platform, team, adhoc)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log_local = Path(root) / "build" / "logs" / f"{stamp}-build-{platform}.log"
    log_local.parent.mkdir(parents=True, exist_ok=True)
    argv = base_args + [
        "-configuration", config,
        "-destination", DESTINATIONS[platform],
        "-derivedDataPath", xc.host_path(root) + "/build/DerivedData",
        *signing["settings"],
        *extra_settings,
    ]
    if signing.get("provisioning"):
        argv.append("-allowProvisioningUpdates")

    xc.log(f"building {platform} ({config}, signing: {signing['style']})")
    t0 = time.time()
    r = xc.remote(BUILD, [xc.host_path(log_local), *argv], timeout=3600)
    seconds = round(time.time() - t0, 1)
    head, _, settings = r.stdout.partition("---SETTINGS---")
    rc_line = [ln for ln in head.splitlines() if ln.startswith("RC=")]
    if r.returncode != 0 or not rc_line:
        # The wrapper itself failed (not xcodebuild): report that, never a build result.
        raise xc.XcError(f"remote build wrapper failed (exit {r.returncode}): {r.stderr.strip()[-800:]}")
    rc = int(rc_line[0][3:])
    text = log_local.read_text(errors="replace") if log_local.exists() else ""
    result = {
        "platform": platform,
        "ok": rc == 0,
        "xcodebuild_rc": rc,
        "config": config,
        "destination": DESTINATIONS[platform],
        "signing": signing["style"],
        "seconds": seconds,
        "log": str(log_local),
        **xc.summarize_log(text),
    }
    if rc == 0:
        s = xc.app_settings(settings)
        app_host = f"{s['TARGET_BUILD_DIR']}/{s['FULL_PRODUCT_NAME']}"
        result.update({
            "app": app_host,
            "bundle_id": s.get("PRODUCT_BUNDLE_IDENTIFIER"),
            "executable": s.get("EXECUTABLE_NAME"),
        })
        xc.write_state(root, f"build-{platform}", result)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", default="all", choices=[*xc.PLATFORMS, "all"])
    ap.add_argument("--config", default="debug", choices=["debug", "release"])
    ap.add_argument("--scheme", help="scheme to build (default: the project name)")
    ap.add_argument("--team", help="Apple team ID (device builds; also used for macOS signing)")
    ap.add_argument("--adhoc", action="store_true",
                    help="sign macOS builds ad-hoc even if .signid/.devteam exist (see signing-and-tcc.md)")
    ap.add_argument("--project-dir", default=".")
    ap.add_argument("--no-generate", action="store_true", help="do not run xcodegen first")
    ap.add_argument("--setting", action="append", default=[], metavar="KEY=VALUE",
                    help="extra xcodebuild build setting (repeatable), e.g. NDI_SDK=/Library/NDI SDK")
    args = ap.parse_args()
    for kv in args.setting:
        if "=" not in kv or not kv.split("=", 1)[0].strip():
            raise xc.XcError(f"--setting {kv!r} is not KEY=VALUE")

    root = xc.find_project_root(args.project_dir)
    if not args.no_generate:
        v = xc.generate_project(root)
        if v:
            xc.log(f"generated project with XcodeGen {v}")
    base, scheme = xc.project_args(root, args.scheme)
    config = args.config.capitalize()

    platforms = xc.supported_platforms(base) if args.platform == "all" else [args.platform]
    results = [build_one(root, base, p, config, args.team, args.setting, args.adhoc) for p in platforms]

    for res in results:
        mark = "✓" if res["ok"] else "✗"
        print(f"{mark} {res['platform']}: {res['errors']} error(s), {res['warnings']} warning(s) "
              f"in {res['seconds']}s — {res.get('app') or res['log']}", file=sys.stderr)
        for e in res["error_samples"]:
            print(f"    {e}", file=sys.stderr)
    ok = all(r["ok"] for r in results)
    xc.emit({"ok": ok, "scheme": scheme, "results": results})
    return 0 if ok else xc.EXIT_FAIL


if __name__ == "__main__":
    xc.run_main(main)
