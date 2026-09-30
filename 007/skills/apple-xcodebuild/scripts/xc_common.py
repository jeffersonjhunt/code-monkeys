"""Shared plumbing for the apple-xcodebuild scripts: host resolution, path mapping, remote exec.

The scripts run in one of two places:
  - a container (or any other machine) sharing a folder with the Mac: commands go over SSH and
    container paths are mapped to the Mac's (`hostpath`);
  - the Mac itself, e.g. `ssh mac 'python3 …/xc-build.py --project-dir /Users/me/Source/app'` for
    a project that lives only on that Mac: commands run right here and paths need no mapping.
`on_the_mac()` decides; nothing else in the scripts differs between the two.

Everything that touches the Mac goes through `remote()`. It sends a bash script over SSH on stdin
(`bash -s`), so nothing is ever re-quoted through a remote login shell, and it always prepends
`set -euo pipefail`. That is the whole fix for the bug this skill replaces: ios-xcodebuild ran
`xcodebuild … | tail -5` in the Mac's login shell, whose exit status was tail's, so a failed build
reported success.

The Mac's /bin/bash is 3.2 — remote scripts must not use bash 4 features (assoc arrays, ${x,,},
mapfile, `|&`).

Test seams: `ssh` and `hostpath` are resolved from PATH, so the test suite puts fakes first on
PATH (a fake ssh that runs the script locally, a fake hostpath that returns its input).
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_HOST = "host.docker.internal"
DEFAULT_XCODEGEN_VERSION = "2.45.4"
XCODEGEN_REPO = "https://github.com/yonaskolb/XcodeGen.git"
# Tags can be moved, so the cached XcodeGen (compiled and run on the Mac) is pinned to a commit.
# 2.45.4 matches avatar's tools/XcodeGen submodule. Other versions: `<version>@<sha>` in
# .xcodegen-version (find it with: git ls-remote <repo> refs/tags/<version>).
KNOWN_XCODEGEN = {
    "2.45.4": "8d3d3476a69ae3e5d68e1adccc701c410c05eb36",
    "2.46.0": "8445e778451c7e44237b90281bde622d764b0084",
}
# First line of every remote script's stderr: proves ssh connected, so exit 255 afterwards is the
# script's own status, not ssh failing.
REMOTE_SENTINEL = "__XC_REMOTE_STARTED__"
KEEP_ARTIFACTS = 10
# Relative to the Mac user's $HOME; remote scripts expand it as "$HOME/$rel".
XCODEGEN_CACHE_REL = "Library/Caches/apple-xcodebuild/xcodegen"

PLATFORMS = ("ios-sim", "ios-device", "macos")

# exit codes (CONTRIBUTING.md): 1 = user/build error, 2 = missing dependency or environment
EXIT_FAIL = 1
EXIT_ENV = 2


class XcError(Exception):
    def __init__(self, message, code=EXIT_FAIL, fix=None):
        super().__init__(message)
        self.code = code
        self.fix = fix


def log(msg):
    """Progress goes to stderr; stdout is reserved for the JSON result."""
    print(f"▸ {msg}", file=sys.stderr, flush=True)


def emit(result):
    print(json.dumps(result, indent=2))


def run_main(fn):
    """Run a script's main(), turning XcError into a JSON error object and its exit code."""
    try:
        code = fn()
    except XcError as e:
        err = {"ok": False, "error": str(e)}
        if e.fix:
            err["fix"] = e.fix
        emit(err)
        print(f"✗ {e}", file=sys.stderr)
        if e.fix:
            print(f"  fix: {e.fix}", file=sys.stderr)
        sys.exit(e.code)
    sys.exit(code or 0)


# --- where the Mac is ---------------------------------------------------------------------------


def on_the_mac():
    """True when the scripts run on the Mac that builds: commands then run locally, not over SSH.

    XC_LOCAL=1 / XC_LOCAL=0 forces the answer (the test suite runs on Linux). Otherwise a Mac
    runs locally unless XC_HOST or HOST_IP names another Mac to drive — the same two settings
    host_target() reads, so a Mac never ignores a host it was told to use.
    """
    forced = os.environ.get("XC_LOCAL")
    if forced is not None:
        return forced == "1"
    return sys.platform == "darwin" and not (os.environ.get("XC_HOST") or os.environ.get("HOST_IP"))


def where():
    """The Mac being driven, for messages: user@host over SSH, or this Mac."""
    if on_the_mac():
        import socket

        return f"this Mac ({socket.gethostname()})"
    return host_target()


# --- paths ------------------------------------------------------------------------------------


def find_project_root(start):
    """The directory holding project.yml or a single *.xcodeproj, searched upward from `start`."""
    p = Path(start).resolve()
    for d in (p, *p.parents):
        if (d / "project.yml").is_file() or any(d.glob("*.xcodeproj")):
            return d
    raise XcError(
        f"no project.yml or *.xcodeproj at or above {p}",
        fix="run from the project directory, pass --project-dir, or scaffold with xc-bootstrap.py",
    )


def host_path(local):
    """Map a container path to the same path as the Mac sees it (on the Mac: the path itself).

    HOST_PROJECT_PATH (with HOST_PROJECT_ROOT, the local dir it corresponds to) wins, for setups
    without `hostpath`. Otherwise the container's `hostpath` helper does the translation.
    """
    local = str(Path(local).resolve())
    if on_the_mac():
        return local
    override = os.environ.get("HOST_PROJECT_PATH")
    if override:
        root = os.environ.get("HOST_PROJECT_ROOT")
        if not root:
            raise XcError(
                "HOST_PROJECT_PATH is set without HOST_PROJECT_ROOT",
                code=EXIT_ENV,
                fix="set HOST_PROJECT_ROOT to the local directory HOST_PROJECT_PATH corresponds to",
            )
        root = str(Path(root).resolve())
        if local != root and not local.startswith(root + "/"):
            raise XcError(f"{local} is outside HOST_PROJECT_ROOT {root}", code=EXIT_ENV)
        return override.rstrip("/") + local[len(root):]
    if not shutil.which("hostpath"):
        raise XcError(
            "cannot map container paths to the Mac: no `hostpath` and no HOST_PROJECT_PATH",
            code=EXIT_ENV,
            fix="set HOST_PROJECT_PATH=<project dir on the Mac> and HOST_PROJECT_ROOT=<same dir here>",
        )
    r = subprocess.run(["hostpath", local], capture_output=True, text=True)
    mapped = r.stdout.strip()
    if r.returncode != 0 or not mapped:
        raise XcError(
            f"hostpath could not map {local}: {r.stderr.strip() or 'no output'}",
            code=EXIT_ENV,
            fix="the project must live under a host-shared directory (e.g. ~/workspace)",
        )
    return mapped


def host_target():
    """user@host for SSH. The user defaults to the owner of the mapped workspace (/Users/<u>/…)."""
    host = os.environ.get("XC_HOST") or os.environ.get("HOST_IP") or DEFAULT_HOST
    user = os.environ.get("XC_HOST_USER") or os.environ.get("HOST_USER")
    if not user:
        ws = os.environ.get("HOST_WORKSPACE", "")
        m = re.match(r"^/Users/([^/]+)/", ws + "/")
        if m:
            user = m.group(1)
    if not user:
        raise XcError(
            "cannot tell which user to SSH to the Mac as",
            code=EXIT_ENV,
            fix="set XC_HOST_USER (or HOST_USER) to your macOS user name",
        )
    return f"{user}@{host}"


# --- remote execution -------------------------------------------------------------------------


def ssh_base():
    # BatchMode: never hang on a password/passphrase prompt. Host key checking stays ON — trust
    # the Mac once with `ssh-keyscan -H <host> >> ~/.ssh/known_hosts`.
    return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host_target()]


def remote(script, args=(), timeout=None):
    """Run a bash script on the Mac (over SSH, or directly when on_the_mac()). Returns
    CompletedProcess; never raises on a non-zero exit.

    Exit 255 without the sentinel is ssh's own failure (unreachable, auth, host key) and is turned
    into an XcError so no caller can mistake "could not ask" for "asked and got a no". A remote
    command that itself exits 255 is returned like any other status.

    Timeouts kill the local ssh only; a long remote command (xcodebuild) may keep running on the
    Mac until it finishes (accepted — the timeouts are generous).
    """
    local = on_the_mac()
    if local:
        cmd = ["bash", "-s", "--", *(str(a) for a in args)]
    else:
        argv = " ".join(shlex.quote(str(a)) for a in args)
        cmd = ssh_base() + [f"bash -s -- {argv}".rstrip()]
    body = f"echo {REMOTE_SENTINEL} >&2\nset -euo pipefail\n" + script
    try:
        r = subprocess.run(
            cmd,
            input=body,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except FileNotFoundError as e:
        raise XcError(f"{cmd[0]} is not installed here", code=EXIT_ENV) from e
    except subprocess.TimeoutExpired as e:
        raise XcError(f"remote command timed out after {timeout}s", code=EXIT_FAIL) from e
    started = REMOTE_SENTINEL in (r.stderr or "")
    r.stderr = "\n".join(ln for ln in (r.stderr or "").splitlines() if ln != REMOTE_SENTINEL)
    if r.returncode == 255 and not started and not local:
        err = r.stderr.strip()
        fix = None
        if "Host key verification failed" in err:
            host = host_target().split("@", 1)[1]
            fix = f"trust the Mac once: ssh-keyscan -H {host} >> ~/.ssh/known_hosts"
        elif "Permission denied" in err:
            fix = "install your public key in the Mac user's ~/.ssh/authorized_keys"
        raise XcError(f"ssh to {host_target()} failed: {err or 'exit 255'}", code=EXIT_ENV, fix=fix)
    return r


# --- project facts ------------------------------------------------------------------------------


def read_project_name(root):
    """The XcodeGen `name:` (top-level key), else the single .xcodeproj's stem."""
    yml = Path(root) / "project.yml"
    if yml.is_file():
        for line in yml.read_text().splitlines():
            m = re.match(r"^name:\s*['\"]?([^'\"#\s]+)", line)
            if m:
                return m.group(1)
    projs = sorted(Path(root).glob("*.xcodeproj"))
    if len(projs) == 1:
        return projs[0].stem
    raise XcError(f"cannot determine the project name in {root}")


def xcodegen_version(root):
    """(version, commit) for the project: `.xcodegen-version` holds `2.45.4` or `2.45.4@<sha>`."""
    f = Path(root) / ".xcodegen-version"
    v = f.read_text().strip() if f.is_file() else DEFAULT_XCODEGEN_VERSION
    m = re.fullmatch(r"(\d+\.\d+\.\d+)(?:@([0-9a-f]{40}))?", v)
    if not m:
        raise XcError(f".xcodegen-version holds {v!r}, expected 2.45.4 or 2.45.4@<40-hex commit>")
    version, sha = m.group(1), m.group(2)
    known = KNOWN_XCODEGEN.get(version)
    if sha and known and sha != known:
        raise XcError(f".xcodegen-version pins {version} to {sha}, but its known commit is {known}")
    sha = sha or known
    if not sha:
        raise XcError(
            f"XcodeGen {version} has no known commit to verify against",
            fix=f"pin it: echo {version}@$(git ls-remote {XCODEGEN_REPO} refs/tags/{version} | cut -f1) "
                "> .xcodegen-version",
        )
    return version, sha


def xcodegen_rel(version, sha):
    """The cached xcodegen wrapper, relative to the Mac user's $HOME (keyed by version + commit)."""
    return f"{XCODEGEN_CACHE_REL}/{version}-{sha[:12]}/bin/xcodegen"


def prune(directory, pattern, keep=KEEP_ARTIFACTS):
    """Delete all but the newest `keep` entries matching `pattern` (files or bundle dirs)."""
    d = Path(directory)
    if not d.is_dir():
        return
    entries = sorted(d.glob(pattern), key=lambda p: p.name, reverse=True)
    for p in entries[keep:]:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        else:
            p.unlink(missing_ok=True)


def parse_settings(pairs):
    """Validate `--setting KEY=VALUE` arguments."""
    for kv in pairs:
        if "=" not in kv or not kv.split("=", 1)[0].strip():
            raise XcError(f"--setting {kv!r} is not KEY=VALUE")
    return list(pairs)


def state_dir(root):
    d = Path(root) / "build" / "xc"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_state(root, name, data):
    (state_dir(root) / f"{name}.json").write_text(json.dumps(data, indent=2) + "\n")


def read_state(root, name):
    f = Path(root) / "build" / "xc" / f"{name}.json"
    if not f.is_file():
        return None
    return json.loads(f.read_text())


# --- signing ----------------------------------------------------------------------------------


def signing_settings(root, platform, team=None, adhoc=False):
    """xcodebuild setting overrides for signing.

    macOS follows avatar's precedence: `.signid` (a named identity, manual — no Apple account,
    and TCC grants survive rebuilds), then a team (`--team`, TEAM_ID, `.devteam` — automatic),
    then ad-hoc. The simulator needs no identity. A device build requires a team.
    """
    root = Path(root)
    team = team or os.environ.get("TEAM_ID") or _read_dotfile(root / ".devteam")
    signid = _read_dotfile(root / ".signid")
    if platform == "ios-sim":
        return {"style": "simulator", "settings": []}
    if adhoc and platform == "macos":
        # Explicit ad-hoc, overriding .signid/.devteam: over SSH the login keychain's private keys
        # are usually unusable (codesign fails with errSecInternalComponent).
        return {"style": "adhoc", "settings": ["CODE_SIGN_STYLE=Manual", "CODE_SIGN_IDENTITY=-",
                                                "DEVELOPMENT_TEAM="]}
    if platform == "ios-device":
        if not team:
            raise XcError(
                "a device build needs an Apple team",
                fix="pass --team <TEAMID>, set TEAM_ID, or put the ID in .devteam",
            )
        return {
            "style": "team",
            "settings": ["CODE_SIGN_STYLE=Automatic", f"DEVELOPMENT_TEAM={team}"],
            "provisioning": True,
        }
    if signid:
        return {
            "style": "identity",
            "settings": ["CODE_SIGN_STYLE=Manual", f"CODE_SIGN_IDENTITY={signid}"],
        }
    if team:
        return {
            "style": "team",
            "settings": ["CODE_SIGN_STYLE=Automatic", f"DEVELOPMENT_TEAM={team}"],
            "provisioning": True,
        }
    return {"style": "adhoc", "settings": ["CODE_SIGN_STYLE=Manual", "CODE_SIGN_IDENTITY=-"]}


def _read_dotfile(p):
    try:
        v = p.read_text().strip()
    except OSError:
        return None
    return v or None


# --- simulators -------------------------------------------------------------------------------


def _runtime_version(key):
    """com.apple.CoreSimulator.SimRuntime.iOS-27-0 -> (27, 0); non-iOS runtimes -> None."""
    m = re.search(r"SimRuntime\.iOS-(\d+)-(\d+)", key)
    return (int(m.group(1)), int(m.group(2))) if m else None


def pick_simulator(devices_json, want=None):
    """Choose one simulator from `simctl list devices available -j` output.

    `want` is a UDID or an exact device name. Without it: the newest iOS runtime's booted iPhone
    if any, else its first iPhone. Ambiguous or absent matches are errors, never a guess.
    """
    data = json.loads(devices_json) if isinstance(devices_json, str) else devices_json
    pool = []
    for key, devs in data.get("devices", {}).items():
        ver = _runtime_version(key)
        if ver is None:
            continue
        for d in devs:
            if d.get("isAvailable", True):
                pool.append((ver, d))
    if not pool:
        raise XcError(
            "no available iOS simulators on the Mac",
            code=EXIT_ENV,
            fix="on the Mac: xcodebuild -downloadPlatform iOS",
        )
    if want:
        hits = [(v, d) for v, d in pool if d["udid"] == want or d["name"] == want]
        if not hits:
            names = sorted({d["name"] for _, d in pool})
            raise XcError(f"no simulator named or with UDID {want!r}; available: {', '.join(names)}")
        newest = max(v for v, _ in hits)
        hits = [(v, d) for v, d in hits if v == newest]
        if len(hits) > 1:
            raise XcError(f"{want!r} matches {len(hits)} simulators; pass a UDID instead")
        return hits[0][1]
    newest = max(v for v, _ in pool)
    phones = [d for v, d in pool if v == newest and d["name"].startswith("iPhone")]
    if not phones:
        raise XcError(f"no iPhone simulator on iOS {newest[0]}.{newest[1]}; pass --device")
    booted = [d for d in phones if d.get("state") == "Booted"]
    return (booted or phones)[0]


# --- logs -------------------------------------------------------------------------------------

_ISSUE = re.compile(r"^(?P<file>[^:\n]+):(?P<line>\d+):(?:\d+:)? (?P<kind>error|warning): (?P<msg>.*)$")
# Errors with no source location: "xcodebuild: error: …", "error: …" from tools and linkers.
_TOOL_ISSUE = re.compile(r"^(?:(?P<tool>[\w.-]+): )?(?P<kind>error|warning): (?P<msg>.*)$")
# Failures xcodebuild reports without an "error:" prefix: a failed build command
# ("Command CodeSign failed with a nonzero exit code") and Security framework errors (codesign).
_CMD_FAILED = re.compile(r"^(?:Command .* failed with a nonzero exit code|.*: errSec\w+.*)$")


def summarize_log(text, limit=10):
    """Count and sample compiler errors/warnings from an xcodebuild log (deduplicated)."""
    errors, warnings, seen = [], [], set()
    for line in text.splitlines():
        if line in seen:
            continue
        m = _ISSUE.match(line.strip())
        if m:
            item = f"{Path(m['file']).name}:{m['line']}: {m['msg']}"
        else:
            m = _TOOL_ISSUE.match(line.strip())
            if not m:
                if _CMD_FAILED.match(line.strip()):
                    seen.add(line)
                    errors.append(Path(line.strip()).name if "errSec" in line else line.strip())
                continue
            item = f"{m['tool']}: {m['msg']}" if m["tool"] else m["msg"]
        seen.add(line)
        (errors if m["kind"] == "error" else warnings).append(item)
    tail = [ln for ln in text.splitlines() if ln.strip()][-limit:]
    return {
        "errors": len(errors),
        "warnings": len(warnings),
        "error_samples": errors[:limit],
        "warning_samples": warnings[:limit],
        "tail": tail,
    }


# --- xcodegen ---------------------------------------------------------------------------------

_ENSURE_XCODEGEN = r"""
rel="$1"; ver="$2"; repo="$3"; want="$4"
bin="$HOME/$rel"
if [ -x "$bin" ]; then echo "cached"; exit 0; fi
base="$(dirname "$(dirname "$bin")")"
mkdir -p "$(dirname "$base")"
lock="$base.lock"
# One builder at a time; a lock older than 30 min is a dead builder's and is taken over.
n=0
until mkdir "$lock" 2>/dev/null; do
  if [ -n "$(find "$lock" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then rm -rf "$lock"; continue; fi
  n=$((n + 1)); [ "$n" -gt 450 ] && { echo "timed out waiting for $lock" >&2; exit 1; }
  sleep 2
done
trap 'rm -rf "$lock"' EXIT
if [ -x "$bin" ]; then echo "cached"; exit 0; fi
rm -rf "$base"
mkdir -p "$base/bin"
git clone -q --depth 1 --branch "$ver" "$repo" "$base/src" >&2
got=$(git -C "$base/src" rev-parse HEAD)
if [ "$got" != "$want" ]; then
  rm -rf "$base"
  echo "XcodeGen tag $ver is at $got, expected $want — refusing to build it" >&2
  exit 1
fi
swift build -c release --package-path "$base/src" >&2
# Where products land depends on the toolchain (.build/release, or .build/out/Products/Release
# under the newer build system) — ask SwiftPM rather than hardcode it.
real="$(swift build -c release --package-path "$base/src" --show-bin-path)/xcodegen"
[ -x "$real" ] || { echo "build finished but $real is missing" >&2; exit 1; }
# A wrapper, not a copy or symlink: xcodegen finds its resource bundle next to the real binary.
printf '#!/bin/sh\nexec "%s" "$@"\n' "$real" > "$bin.tmp"
chmod +x "$bin.tmp"
mv "$bin.tmp" "$bin"
"$bin" --version >&2
echo "built"
"""


def ensure_xcodegen(version, sha):
    """Build the pinned XcodeGen into the Mac's cache if it is not there. Returns its $HOME-relative path."""
    rel = xcodegen_rel(version, sha)
    xc_log = f"XcodeGen {version} ({sha[:12]})"
    r = remote(_ENSURE_XCODEGEN, [rel, version, XCODEGEN_REPO, sha], timeout=1800)
    if r.returncode != 0:
        raise XcError(
            f"could not build {xc_log} on the Mac: {(r.stderr or '').strip()[-800:]}",
            fix="check git and network access on the Mac, or pin another version in .xcodegen-version",
        )
    if r.stdout.strip() == "built":
        log(f"built {xc_log} into ~/{XCODEGEN_CACHE_REL}/{version}-{sha[:12]}")
    return rel


def generate_project(root):
    """Regenerate the .xcodeproj from project.yml. A no-op for projects without project.yml."""
    root = Path(root)
    if not (root / "project.yml").is_file():
        return None
    version, sha = xcodegen_version(root)
    rel = ensure_xcodegen(version, sha)
    r = remote('cd "$1" && "$HOME/$2" generate --quiet --spec project.yml', [host_path(root), rel], timeout=300)
    if r.returncode != 0:
        raise XcError(f"xcodegen generate failed: {(r.stderr or r.stdout).strip()[-1500:]}")
    return version


def project_args(root, scheme=None):
    """-workspace/-project and -scheme for xcodebuild, as host paths."""
    root = Path(root)
    name = read_project_name(root)
    workspaces = sorted(root.glob("*.xcworkspace"))
    projects = sorted(root.glob("*.xcodeproj"))
    if len(workspaces) > 1 or (not workspaces and len(projects) > 1):
        raise XcError(f"more than one workspace/project in {root}; cannot choose")
    if workspaces:
        container = ["-workspace", host_path(workspaces[0])]
    elif projects:
        container = ["-project", host_path(projects[0])]
    else:
        raise XcError(f"no .xcodeproj in {root} (did xcodegen generate run?)")
    return container + ["-scheme", scheme or name], (scheme or name)


# --- build settings -----------------------------------------------------------------------------

SUPPORTED = r"""
xcodebuild "$@" -showBuildSettings -json 2>/dev/null
"""


def app_settings(settings_json):
    """The application target's settings from `-showBuildSettings -json` output."""
    try:
        entries = json.loads(settings_json)
    except json.JSONDecodeError as e:
        raise XcError(f"could not parse build settings: {e}") from e
    apps = [e["buildSettings"] for e in entries
            if e.get("buildSettings", {}).get("PRODUCT_TYPE") == "com.apple.product-type.application"]
    if len(apps) != 1:
        raise XcError(f"expected one application target in the scheme, found {len(apps)}")
    return apps[0]


def supported_platforms(base_args):
    r = remote(SUPPORTED, base_args, timeout=300)
    if r.returncode != 0:
        raise XcError(f"xcodebuild -showBuildSettings failed: {r.stderr.strip()[-800:]}")
    s = app_settings(r.stdout)
    sdks = s.get("SUPPORTED_PLATFORMS", "").split()
    out = []
    if "iphonesimulator" in sdks:
        out.append("ios-sim")
    if "macosx" in sdks:
        out.append("macos")
    if not out:
        raise XcError(f"scheme supports none of iOS Simulator / macOS (SUPPORTED_PLATFORMS={sdks})")
    return out


# --- macOS processes and windows --------------------------------------------------------------

# Bash: proc_re <path> -> an anchored ERE matching <path> literally, for pgrep/pkill -f. Paths may
# contain "(", "+", "[" … which would otherwise be regex syntax.
PROC_RE_FN = r"""
proc_re() { printf '^%s' "$(printf '%s' "$1" | sed 's/[][\\.*^$(){}+?|]/\\&/g')"; }
"""

XCWIN_SOURCE = Path(__file__).resolve().parent.parent / "assets" / "xcwin.swift"
XCWIN_CACHE_REL = "Library/Caches/apple-xcodebuild/xcwin"

_ENSURE_XCWIN = r"""
rel="$1"
bin="$HOME/$rel"
if [ ! -x "$bin" ]; then
  mkdir -p "$(dirname "$bin")"
  # Per-process temp names (two first runs at once each compile their own, then mv atomically).
  # The source keeps its .swift extension: swiftc picks the input's handling by extension.
  src="$(dirname "$bin")/xcwin.$$.swift"
  trap 'rm -f "$src" "$bin.$$"' EXIT
  cat > "$src" <<'XCWIN_SOURCE_EOF'
__SOURCE__
XCWIN_SOURCE_EOF
  swiftc -O "$src" -o "$bin.$$" >&2
  mv "$bin.$$" "$bin"
fi
echo "$rel"
"""


def xcwin_rel():
    """The window helper's cache path, keyed by its source hash so an edit rebuilds it."""
    import hashlib

    digest = hashlib.sha256(XCWIN_SOURCE.read_bytes()).hexdigest()[:12]
    return f"{XCWIN_CACHE_REL}/{digest}/xcwin"


def ensure_xcwin():
    """Compile the window helper on the Mac once. Returns its $HOME-relative path."""
    source = XCWIN_SOURCE.read_text()
    if "XCWIN_SOURCE_EOF" in source:
        raise XcError("xcwin.swift must not contain the heredoc marker XCWIN_SOURCE_EOF")
    rel = xcwin_rel()
    r = remote(_ENSURE_XCWIN.replace("__SOURCE__", source), [rel], timeout=300)
    if r.returncode != 0:
        raise XcError(f"could not compile the window helper on the Mac: {r.stderr.strip()[-800:]}")
    return rel


# The console session, from the IORegistry root: is someone logged in at the Mac, and is its
# screen locked? macOS UI tests need an awake, unlocked GUI session — otherwise every test waits
# 60 s and fails "Failed to activate application … (current state: Running Background)".
# CGSSessionScreenIsLocked is also set while the display merely sleeps; whether waking it asks for a
# password is the screen-lock setting (`sysadminctl -screenLock status`: "off", or a delay).
_SCREEN = r"""
s=$(ioreg -n Root -d1 2>/dev/null || true)
# No IOConsoleUsers at all means the read failed — not that nobody is logged in (that is an empty list).
case "$s" in *IOConsoleUsers*) echo "PROBE=ok" ;; *) echo "PROBE=failed" ;; esac
case "$s" in *'"kCGSSessionOnConsoleKey"=Yes'*) echo "CONSOLE=yes" ;; *) echo "CONSOLE=no" ;; esac
case "$s" in *'"CGSSessionScreenIsLocked"=Yes'*) echo "LOCKED=yes" ;; *) echo "LOCKED=no" ;; esac
case "$(sysadminctl -screenLock status 2>&1 || true)" in *"screenLock is off"*) echo "PASSWORD=no" ;; *) echo "PASSWORD=yes" ;; esac
"""

SCREEN_LOCK_FIX = ("unlock the Mac — and on a build Mac, stop it locking: System Settings ▸ Lock Screen ▸ "
                   "\"Require password after screen saver begins or display is turned off\" ▸ Never")
PROBE_FAILED_FIX = "on the Mac: run `ioreg -n Root -d1` and look for IOConsoleUsers"
NO_CONSOLE_FIX = "log in to the Mac's desktop (a GUI session, not just SSH) — or turn on automatic login"


def _screen_facts():
    r = remote(_SCREEN)
    return dict(ln.split("=", 1) for ln in r.stdout.splitlines() if "=" in ln)


def screen_state(wake=False):
    """(problem, note): problem is None if macOS UI tests can run, else (reason, fix).

    A screen "locked" only because the display slept (no password to wake it) is not a problem:
    with wake=True the display is woken here; without, the note says it will need waking.
    """
    f = _screen_facts()
    if f.get("PROBE") != "ok":
        # "Could not tell" is never reported as a state it did not observe.
        return ("could not read the Mac's desktop session (ioreg gave no IOConsoleUsers)", PROBE_FAILED_FIX), None
    if f.get("CONSOLE") != "yes":
        return ("nobody is logged in at the Mac's desktop", NO_CONSOLE_FIX), None
    if f.get("LOCKED") != "yes":
        return None, None
    if f.get("PASSWORD") == "yes":
        return ("the Mac's screen is locked (waking it asks for a password)", SCREEN_LOCK_FIX), None
    if not wake:
        return None, "the display is asleep (no password to wake it) — xc-test wakes it"
    remote("caffeinate -u -t 2 || true")
    if _screen_facts().get("LOCKED") == "yes":
        return ("the Mac's screen stayed locked after waking the display", SCREEN_LOCK_FIX), None
    return None, "woke the display"


SCREEN_RECORDING_FIX = (
    "on the Mac: System Settings ▸ Privacy & Security ▸ Screen & System Audio Recording ▸ enable "
    "sshd-keygen-wrapper (/usr/libexec/sshd-keygen-wrapper — the SSH server; add it with + if absent)"
)
