#!/usr/bin/env python3
"""xc-bootstrap — scaffold a SwiftUI app as an XcodeGen project for iOS, macOS, or both.

One target serves every requested platform (XcodeGen `supportedDestinations`), with a Swift
Testing unit-test target, an asset catalog, a generated Info.plist and a pinned XcodeGen
version. Nothing is compiled here; run xc-build.py next.

The target directory may already exist (e.g. a fresh git repo): scaffolding proceeds only if no
file it would write is already there. An existing .gitignore is extended, never replaced.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xc_common as xc  # noqa: E402

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "templates" / "app"

IOS_SETTINGS = """\
        TARGETED_DEVICE_FAMILY: "1,2"
        INFOPLIST_KEY_UILaunchScreen_Generation: YES
        INFOPLIST_KEY_UIApplicationSceneManifest_Generation: YES
        INFOPLIST_KEY_UISupportedInterfaceOrientations_iPhone: "UIInterfaceOrientationPortrait UIInterfaceOrientationLandscapeLeft UIInterfaceOrientationLandscapeRight"
        INFOPLIST_KEY_UISupportedInterfaceOrientations_iPad: "UIInterfaceOrientationPortrait UIInterfaceOrientationPortraitUpsideDown UIInterfaceOrientationLandscapeLeft UIInterfaceOrientationLandscapeRight\""""


def render(text, subs):
    for k, v in subs.items():
        text = text.replace(k, v)
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("app", help="app / module name, e.g. Solitaire (letters and digits, capitalised)")
    ap.add_argument("--bundle-id", help="bundle identifier (default: com.example.<app lowercased>)")
    ap.add_argument("--platforms", default="ios,macos", help="comma list of ios, macos (default: both)")
    ap.add_argument("--ios", default="17.0", help="iOS deployment target (default: 17.0)")
    ap.add_argument("--macos", default="14.0", help="macOS deployment target (default: 14.0)")
    ap.add_argument("--dir", help="directory to scaffold into (default: ./<app>)")
    args = ap.parse_args()

    if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", args.app):
        raise xc.XcError(f"app name {args.app!r} must start with a capital letter and be letters/digits only")
    bundle_id = args.bundle_id or f"com.example.{args.app.lower()}"
    if not re.fullmatch(r"[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+", bundle_id):
        raise xc.XcError(f"bundle id {bundle_id!r} is not reverse-DNS (e.g. com.example.app)")
    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    bad = [p for p in platforms if p not in ("ios", "macos")]
    if bad or not platforms:
        raise xc.XcError(f"--platforms takes ios and/or macos, got {args.platforms!r}")
    for flag, v in (("--ios", args.ios), ("--macos", args.macos)):
        if not re.fullmatch(r"\d+\.\d+", v):
            raise xc.XcError(f"{flag} {v!r} is not a version like 17.0")

    dest = Path(args.dir or args.app).resolve()
    targets = []
    if "ios" in platforms:
        targets.append(f'    iOS: "{args.ios}"')
    if "macos" in platforms:
        targets.append(f'    macOS: "{args.macos}"')
    subs = {
        "__APP__": args.app,
        "__BUNDLE_ID__": bundle_id,
        "__BUNDLE_PREFIX__": bundle_id.rsplit(".", 1)[0],
        "__DEPLOYMENT_TARGETS__": "\n".join(targets),
        "__DESTINATIONS__": ", ".join({"ios": "iOS", "macos": "macOS"}[p] for p in platforms),
        "__IOS_SETTINGS__": IOS_SETTINGS if "ios" in platforms else "",
    }

    plan = []
    for src in sorted(TEMPLATE.rglob("*")):
        if not src.is_file():
            continue
        rel = render(str(src.relative_to(TEMPLATE)), subs)
        if rel == "gitignore":
            rel = ".gitignore"
        plan.append((src, dest / rel))

    conflicts = [str(d.relative_to(dest)) for _, d in plan if d.exists() and d.name != ".gitignore"]
    if conflicts:
        raise xc.XcError(f"refusing to overwrite existing files in {dest}: {', '.join(conflicts)}")

    created, extended = [], []
    for src, dst in plan:
        text = render(src.read_text(), subs)
        text = re.sub(r"\n{3,}", "\n\n", text) if dst.name == "project.yml" else text
        text = text.replace("\n\n    scheme:", "\n    scheme:")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.name == ".gitignore" and dst.exists():
            have = set(dst.read_text().splitlines())
            add = [ln for ln in text.splitlines() if ln and not ln.startswith("#") and ln not in have]
            if add:
                with dst.open("a") as f:
                    f.write("\n# apple-xcodebuild\n" + "\n".join(add) + "\n")
                extended.append(".gitignore")
            continue
        dst.write_text(text)
        created.append(str(dst.relative_to(dest)))

    xc.log(f"scaffolded {args.app} ({', '.join(platforms)}) in {dest}")
    xc.emit({
        "ok": True,
        "app": args.app,
        "bundle_id": bundle_id,
        "platforms": platforms,
        "dir": str(dest),
        "created": created,
        "extended": extended,
        "next": f"python3 {Path(__file__).parent / 'xc-build.py'} --project-dir {dest}",
    })
    return 0


if __name__ == "__main__":
    xc.run_main(main)
