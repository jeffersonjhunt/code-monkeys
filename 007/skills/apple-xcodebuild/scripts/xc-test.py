#!/usr/bin/env python3
"""xc-test — run tests on the Mac: the scheme's test plan per platform, and/or local Swift packages.

Scheme tests run `xcodebuild test` against a concrete destination (this Mac, or one iOS
simulator) and read the counts from the .xcresult bundle. `--package DIR` runs `swift test` in
a local package (repeatable) and reads the counts from its output (XCTest and Swift Testing).

Zero tests is a FAILURE, not a pass: a suite that enumerated nothing proves nothing. So is a
test run whose counts could not be read — "could not tell" is never reported as "passed".
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xc_common as xc  # noqa: E402

# $1 = log, $2 = result bundle, $3.. = xcodebuild argv
XCTEST = r"""
log="$1"; bundle="$2"; shift 2
mkdir -p "$(dirname "$log")" "$(dirname "$bundle")"
rm -rf "$bundle"
set +e
xcodebuild "$@" -resultBundlePath "$bundle" test >"$log" 2>&1
rc=$?
set -e
echo "RC=$rc"
echo '---SUMMARY---'
if [ -d "$bundle" ]; then
  xcrun xcresulttool get test-results summary --path "$bundle" --compact 2>/dev/null || echo '{}'
else
  echo '{}'
fi
"""

# $1 = log, $2 = package dir
SWIFTTEST = r"""
log="$1"; pkg="$2"
mkdir -p "$(dirname "$log")"
set +e
swift test --package-path "$pkg" >"$log" 2>&1
rc=$?
set -e
echo "RC=$rc"
"""

SIMLIST = "xcrun simctl list devices available -j"


def counts_from_xcresult(summary):
    """(total, passed, failed, skipped) from `xcresulttool get test-results summary` JSON."""
    try:
        s = json.loads(summary)
    except json.JSONDecodeError:
        return None
    if "totalTestCount" not in s:
        return None
    return (
        int(s.get("totalTestCount", 0)),
        int(s.get("passedTests", 0)),
        int(s.get("failedTests", 0)),
        int(s.get("skippedTests", 0)),
    )


_XCTEST_RUN = re.compile(r"Executed (\d+) tests?, with (\d+) failures?")
_SWT_RUN = re.compile(r"Test run with (\d+) tests?(?: in \d+ suites?)? (passed|failed)(?:.* with (\d+) issues?)?")


def counts_from_swift_test(text):
    """(total, passed, failed, skipped) summed over XCTest and Swift Testing summaries, or None."""
    total = failed = 0
    found = False
    # XCTest prints a summary per bundle and one for "All tests"; the last one is the grand total.
    xct = _XCTEST_RUN.findall(text)
    if xct:
        found = True
        n, f = xct[-1]
        total += int(n)
        failed += int(f)
    swt = _SWT_RUN.findall(text)
    if swt:
        found = True
        n, status, issues = swt[-1]
        total += int(n)
        if status == "failed":
            # Swift Testing reports issues, not failing tests; count at least one failure.
            failed += max(1, int(issues or 0))
    if not found:
        return None
    return (total, max(total - failed, 0), failed, 0)


def verdict(kind, name, rc, counts, log_path, extra=None):
    res = {"kind": kind, "target": name, "rc": rc, "log": str(log_path), **(extra or {})}
    if counts is None:
        res.update(ok=False, reason="could not read test counts — see the log")
        return res
    total, passed, failed, skipped = counts
    res.update(total=total, passed=passed, failed=failed, skipped=skipped)
    if total == 0 and rc != 0:
        res.update(ok=False, reason=f"the test run exited {rc} before any test ran — see errors")
    elif total == 0:
        res.update(ok=False, reason="zero tests ran — a suite that found nothing is not a pass")
    elif rc != 0 or failed:
        res.update(ok=False, reason=f"{failed} failed" if failed else f"test run exited {rc}")
    else:
        res.update(ok=True)
    return res


def run_scheme(root, base, platform, device, adhoc=False, settings=()):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log_local = Path(root) / "build" / "logs" / f"{stamp}-test-{platform}.log"
    bundle_local = Path(root) / "build" / "xc" / "results" / f"{stamp}-{platform}.xcresult"
    log_local.parent.mkdir(parents=True, exist_ok=True)
    extra = {}
    if platform == "macos":
        dest = "platform=macOS"
    else:
        r = xc.remote(SIMLIST)
        sim = xc.pick_simulator(r.stdout, device)
        dest = f"platform=iOS Simulator,id={sim['udid']}"
        extra["device"] = sim["name"]
    signing = xc.signing_settings(root, platform, adhoc=adhoc)
    argv = base + [
        "-destination", dest,
        "-derivedDataPath", xc.host_path(root) + "/build/DerivedData",
        *signing["settings"],
        *settings,
    ]
    xc.log(f"testing {platform} ({dest})")
    r = xc.remote(XCTEST, [xc.host_path(log_local), xc.host_path(bundle_local), *argv], timeout=3600)
    head, _, summary = r.stdout.partition("---SUMMARY---")
    rc_line = [ln for ln in head.splitlines() if ln.startswith("RC=")]
    if r.returncode != 0 or not rc_line:
        raise xc.XcError(f"remote test wrapper failed (exit {r.returncode}): {r.stderr.strip()[-800:]}")
    rc = int(rc_line[0][3:])
    counts = counts_from_xcresult(summary.strip())
    xc.prune(log_local.parent, f"*-test-{platform}.log")
    xc.prune(bundle_local.parent, f"*-{platform}.xcresult")
    res = verdict("scheme", platform, rc, counts, log_local, {"destination": dest, **extra})
    if not res["ok"] and log_local.exists():
        res.update({k: v for k, v in xc.summarize_log(log_local.read_text(errors="replace")).items()
                    if k in ("errors", "error_samples", "tail")})
    return res


def run_package(root, pkg):
    pkg = Path(pkg).resolve()
    if not (pkg / "Package.swift").is_file():
        raise xc.XcError(f"{pkg} has no Package.swift")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log_local = Path(root) / "build" / "logs" / f"{stamp}-swifttest-{pkg.name}.log"
    log_local.parent.mkdir(parents=True, exist_ok=True)
    xc.log(f"swift test {pkg.name}")
    r = xc.remote(SWIFTTEST, [xc.host_path(log_local), xc.host_path(pkg)], timeout=3600)
    rc_line = [ln for ln in r.stdout.splitlines() if ln.startswith("RC=")]
    if r.returncode != 0 or not rc_line:
        raise xc.XcError(f"remote swift test wrapper failed (exit {r.returncode}): {r.stderr.strip()[-800:]}")
    rc = int(rc_line[0][3:])
    text = log_local.read_text(errors="replace") if log_local.exists() else ""
    xc.prune(log_local.parent, f"*-swifttest-{pkg.name}.log")
    res = verdict("package", pkg.name, rc, counts_from_swift_test(text), log_local)
    if not res["ok"]:
        res.update({k: v for k, v in xc.summarize_log(text).items() if k in ("errors", "error_samples", "tail")})
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", action="append", choices=["ios-sim", "macos"],
                    help="scheme tests to run (repeatable; default: every platform the scheme supports)")
    ap.add_argument("--package", action="append", default=[], help="local Swift package dir to `swift test`")
    ap.add_argument("--packages-only", action="store_true", help="skip scheme tests")
    ap.add_argument("--device", help="simulator name or UDID for iOS tests")
    ap.add_argument("--scheme")
    ap.add_argument("--project-dir", default=".")
    ap.add_argument("--no-generate", action="store_true")
    ap.add_argument("--adhoc", action="store_true",
                    help="sign macOS test builds ad-hoc even if .signid/.devteam exist")
    ap.add_argument("--setting", action="append", default=[], metavar="KEY=VALUE",
                    help="extra xcodebuild build setting (repeatable)")
    args = ap.parse_args()
    xc.parse_settings(args.setting)

    root = xc.find_project_root(args.project_dir)
    results = []
    for pkg in args.package:
        results.append(run_package(root, pkg))
    if not args.packages_only:
        if not args.no_generate:
            xc.generate_project(root)
        base, _ = xc.project_args(root, args.scheme)
        platforms = args.platform
        if not platforms:
            platforms = xc.supported_platforms(base)
        for p in platforms:
            results.append(run_scheme(root, base, p, args.device, args.adhoc, args.setting))

    if not results:
        raise xc.XcError("nothing to test: --packages-only with no --package")

    for res in results:
        mark = "✓" if res["ok"] else "✗"
        counts = f"{res['passed']}/{res['total']} passed" if "total" in res else "no counts"
        why = f" — {res['reason']}" if not res["ok"] else ""
        print(f"{mark} {res['kind']} {res['target']}: {counts}{why}", file=sys.stderr)
    ok = all(r["ok"] for r in results)
    xc.emit({"ok": ok, "results": results})
    return 0 if ok else xc.EXIT_FAIL


if __name__ == "__main__":
    xc.run_main(main)
