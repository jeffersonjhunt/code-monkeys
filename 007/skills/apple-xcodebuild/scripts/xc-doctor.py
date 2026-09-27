#!/usr/bin/env python3
"""xc-doctor — is the Mac ready to build this project? Every check that blocked a real session.

Each check is ok / warn / fail, with a fix for anything not ok. A check that could not run is a
fail with the reason — never silently a pass. Exit 1 if any check fails, 2 if the Mac is
unreachable.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xc_common as xc  # noqa: E402

PROBE = r"""
p() { printf '%s=%s\n' "$1" "$2"; }
dev=$(xcode-select -p 2>/dev/null || true); p developer_dir "$dev"
v=$(xcodebuild -version 2>/dev/null | head -1 || true); p xcode "$v"
set +e
xcodebuild -checkFirstLaunchStatus >/dev/null 2>&1; p first_launch_rc "$?"
set -e
sdks=$(xcodebuild -showsdks 2>/dev/null | grep -oE -- '-sdk [a-z]+' | awk '{print $2}' | sort -u | tr '\n' ' ' || true)
p sdks "$sdks"
if [ -n "${1:-}" ]; then
  if [ -d "$1" ]; then p project_visible yes; else p project_visible no; fi
fi
if [ -n "${2:-}" ]; then
  p xcodegen_cached "$([ -x "$HOME/$2" ] && echo yes || echo no)"
fi
p git "$(command -v git >/dev/null && echo yes || echo no)"
echo '---SIMCTL---'
xcrun simctl list devices available -j 2>/dev/null || echo '{}'
"""


# $1 = identity to try ("Apple Development" matches any cert of that kind)
SIGN_PROBE = r"""
n=$(security find-identity -v -p codesigning 2>/dev/null | grep -c '^ *[0-9][0-9]*)' || true)
echo "IDENTITIES=$n"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp /usr/bin/true "$tmp/probe"
set +e
out=$(codesign --force --sign "$1" "$tmp/probe" 2>&1)
rc=$?
set -e
echo "SIGN_RC=$rc"
echo "SIGN_OUT=$(printf '%s' "$out" | tr '\n' ' ')"
"""


def signing_check(root):
    """Can the signing a macOS build of this project would use actually sign over SSH?"""
    signid = (root / ".signid").read_text().strip() if (root / ".signid").is_file() else ""
    team = (root / ".devteam").read_text().strip() if (root / ".devteam").is_file() else ""
    if not signid and not team:
        return check("codesign", "ok", "ad-hoc (no .signid/.devteam) — needs no keychain")
    identity = signid or "Apple Development"
    r = xc.remote(SIGN_PROBE, [identity])
    f = dict(ln.split("=", 1) for ln in r.stdout.splitlines() if "=" in ln)
    if f.get("SIGN_RC") == "0":
        return check("codesign", "ok", f"signed a probe with {identity!r} over SSH")
    out = f.get("SIGN_OUT", "").strip()
    if "errSecInternalComponent" in out:
        return check("codesign", "fail",
                     f"{identity!r} exists but its key is unusable over SSH (errSecInternalComponent: "
                     "the login keychain is locked to this session)",
                     "build with --adhoc; or try unlocking it over SSH first (unverified — see "
                     "references/signing-and-tcc.md)")
    return check("codesign", "fail", f"cannot sign with {identity!r}: {out or 'no identity'} "
                 f"({f.get('IDENTITIES', '?')} codesigning identities)",
                 "fix .signid/.devteam, or build with --adhoc")


def screen_recording_check():
    """Screenshots of macOS windows need the Screen Recording grant for the SSH server."""
    try:
        helper = xc.ensure_xcwin()
    except xc.XcError as e:
        return check("screen-recording", "warn", f"could not build the window helper: {e}",
                     "macOS screenshots are unavailable until it builds (needs swiftc on the Mac)")
    r = xc.remote('"$HOME/$1" preflight', [helper])
    if r.stdout.strip() == "granted":
        return check("screen-recording", "ok", "SSH sessions may capture windows (macOS screenshots work)")
    return check("screen-recording", "warn",
                 "SSH sessions may not record the screen — xc-shot --platform macos will refuse",
                 xc.SCREEN_RECORDING_FIX)


def check(name, status, detail, fix=None):
    c = {"check": name, "status": status, "detail": detail}
    if fix:
        c["fix"] = fix
    return c


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-dir", default=".", help="project to check visibility of (default: .)")
    ap.add_argument(
        "--platform",
        action="append",
        choices=["ios", "macos"],
        help="platforms that must be buildable (repeatable; default: both)",
    )
    ap.add_argument("--no-project", action="store_true", help="only check the Mac, not a project")
    args = ap.parse_args()
    platforms = args.platform or ["ios", "macos"]

    checks = []
    root = ver = None
    project_host = xcodegen_rel = ""
    if not args.no_project:
        root = xc.find_project_root(args.project_dir)
        project_host = xc.host_path(root)
        if (root / "project.yml").is_file():
            ver, sha = xc.xcodegen_version(root)
            xcodegen_rel = xc.xcodegen_rel(ver, sha)
    target = xc.host_target()

    xc.log(f"probing {target}")
    r = xc.remote(PROBE, [project_host, xcodegen_rel])
    checks.append(check("ssh", "ok", f"connected to {target}"))
    if r.returncode != 0:
        raise xc.XcError(f"probe failed on the Mac (exit {r.returncode}): {r.stderr.strip()}")

    head, _, sim_json = r.stdout.partition("---SIMCTL---")
    facts = dict(line.split("=", 1) for line in head.splitlines() if "=" in line)

    dev = facts.get("developer_dir", "")
    if "Xcode" in dev and dev.endswith("/Contents/Developer"):
        checks.append(check("xcode-select", "ok", dev))
    else:
        checks.append(check("xcode-select", "fail", dev or "not set",
                            "on the Mac: sudo xcode-select -s /Applications/Xcode.app"))

    checks.append(check("xcode", "ok" if facts.get("xcode") else "fail", facts.get("xcode") or "xcodebuild not found",
                        None if facts.get("xcode") else "install Xcode from the App Store or developer.apple.com"))

    rc = facts.get("first_launch_rc", "")
    if rc == "0":
        checks.append(check("first-launch", "ok", "Xcode system components installed"))
    else:
        checks.append(check("first-launch", "fail",
                            f"xcodebuild -checkFirstLaunchStatus exited {rc or '?'} — system packages "
                            "(CoreSimulator, MobileDevice) missing or older than this Xcode",
                            "on the Mac: sudo xcodebuild -runFirstLaunch"))

    sdks = facts.get("sdks", "").split()
    need = {"macos": ["macosx"], "ios": ["iphoneos", "iphonesimulator"]}
    for plat in platforms:
        missing = [s for s in need[plat] if s not in sdks]
        if missing:
            checks.append(check(f"sdk-{plat}", "fail", f"missing SDK(s): {', '.join(missing)}",
                                "on the Mac: xcodebuild -downloadPlatform iOS" if plat == "ios" else
                                "reinstall Xcode"))
        else:
            checks.append(check(f"sdk-{plat}", "ok", " ".join(need[plat])))

    if "ios" in platforms:
        try:
            dev_json = json.loads(sim_json.strip() or "{}")
        except json.JSONDecodeError:
            dev_json = None
        if dev_json is None:
            checks.append(check("simulator", "fail", "could not parse simctl output",
                                "on the Mac: xcrun simctl list devices available"))
        else:
            try:
                sim = xc.pick_simulator(dev_json)
                count = sum(len(v) for k, v in dev_json.get("devices", {}).items() if "iOS" in k)
                checks.append(check("simulator", "ok", f"{count} iOS simulator(s); default: {sim['name']}"))
            except xc.XcError as e:
                checks.append(check("simulator", "fail", str(e),
                                    e.fix or "on the Mac: xcodebuild -downloadPlatform iOS"))

    if not args.no_project:
        vis = facts.get("project_visible")
        if vis == "yes":
            checks.append(check("project-path", "ok", project_host))
        else:
            checks.append(check("project-path", "fail", f"{project_host} does not exist on the Mac",
                                "keep the project under a host-shared directory (~/workspace)"))
        cached = facts.get("xcodegen_cached")
        if ver:
            if cached == "yes":
                checks.append(check("xcodegen", "ok", f"cached {ver}"))
            else:
                checks.append(check("xcodegen", "warn", f"{ver} not built yet",
                                    "xc-build.py builds it on first use (needs git + network on the Mac)"
                                    if facts.get("git") == "yes" else "install git on the Mac"))

    if "macos" in platforms:
        checks.append(screen_recording_check())
    if root is not None and "macos" in platforms:
        checks.append(signing_check(root))

    failed = [c for c in checks if c["status"] == "fail"]
    xc.emit({"ok": not failed, "host": target, "checks": checks})
    for c in checks:
        mark = {"ok": "✓", "warn": "!", "fail": "✗"}[c["status"]]
        print(f"{mark} {c['check']}: {c['detail']}", file=sys.stderr)
        if c.get("fix"):
            print(f"    fix: {c['fix']}", file=sys.stderr)
    return xc.EXIT_FAIL if failed else 0


if __name__ == "__main__":
    xc.run_main(main)
