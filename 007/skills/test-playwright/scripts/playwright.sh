#!/usr/bin/env bash
# playwright.sh — Manage, create, and run Playwright tests
#
# Dependencies:
#   Node.js >= 18
#   npm or pnpm
#
# Usage:
#   playwright.sh init                     Set up Playwright in current project
#   playwright.sh create <name>            Scaffold a new test file
#   playwright.sh run [filter] [options]   Run tests
#   playwright.sh debug [filter]           Run with trace, headed, slow-mo
#   playwright.sh codegen [url]            Launch test recorder
#   playwright.sh report                   Open last HTML report
#   playwright.sh ci                       Run in CI mode
#   playwright.sh update                   Update Playwright browsers
#   playwright.sh help                     Show this help
#
# Run options:
#   --headed                Run with visible browser
#   --browser=BROWSER       chromium, firefox, or webkit
#   --workers=N             Parallel workers (default: auto)
#   --retries=N             Retry failed tests
#   --grep=PATTERN          Filter tests by title pattern

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATES_DIR="$SCRIPT_DIR/../assets/templates"

die() { echo "Error: $*" >&2; exit 1; }

usage() {
    sed -n '2,/^[^#]/s/^# \{0,1\}//p' "$0"
    exit 0
}

find_pkg_manager() {
    if [[ -f "pnpm-lock.yaml" ]]; then
        echo "pnpm"
    else
        echo "npm"
    fi
}

find_config() {
    for f in playwright.config.ts playwright.config.js playwright.config.mjs; do
        [[ -f "$f" ]] && echo "$f" && return
    done
}

ensure_node() {
    command -v node >/dev/null 2>&1 || die "Node.js is required but not installed.
Install from https://nodejs.org or via nvm."
    local ver
    ver=$(node -v | sed 's/v//' | cut -d. -f1)
    [[ "$ver" -ge 18 ]] || die "Node.js >= 18 required (found v$ver)"
}

ensure_playwright() {
    [[ -f "node_modules/.bin/playwright" ]] || die "Playwright not found in this project.
Run: playwright.sh init"
}

cmd_init() {
    ensure_node
    local pm
    pm=$(find_pkg_manager)

    if [[ -f "node_modules/.bin/playwright" ]]; then
        echo "Playwright already installed."
    else
        echo "Installing Playwright..."
        $pm install -D @playwright/test
    fi

    echo "Installing browsers..."
    npx playwright install

    if [[ ! -f "$(find_config)" ]]; then
        echo "Creating playwright.config.ts..."
        cp "$TEMPLATES_DIR/playwright.config.ts" .
    fi

    if [[ ! -d "tests" ]]; then
        mkdir -p tests
        cp "$TEMPLATES_DIR/basic.spec.ts" tests/example.spec.ts
        echo "Created tests/example.spec.ts"
    fi

    echo "Done. Run: playwright.sh run"
}

cmd_create() {
    local name="${1:-}"
    [[ -z "$name" ]] && die "Usage: playwright.sh create <name>
Example: playwright.sh create login"

    ensure_playwright

    local dir="tests"
    [[ -d "e2e" ]] && dir="e2e"
    [[ -d "test" ]] && dir="test"

    local file="$dir/${name}.spec.ts"
    [[ -f "$file" ]] && die "File already exists: $file"

    mkdir -p "$dir"
    sed "s/{{NAME}}/$name/g" "$TEMPLATES_DIR/basic.spec.ts" > "$file"
    echo "Created $file"
}

cmd_run() {
    ensure_node
    ensure_playwright

    local args=()
    local filter=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --headed)         args+=(--headed); shift ;;
            --browser=*)     args+=(--project="${1#--browser=}"); shift ;;
            --workers=*)     args+=(--workers="${1#--workers=}"); shift ;;
            --retries=*)     args+=(--retries="${1#--retries=}"); shift ;;
            --grep=*)        args+=(--grep="${1#--grep=}"); shift ;;
            -*)              args+=("$1"); shift ;;
            *)               filter="$1"; shift ;;
        esac
    done

    [[ -n "$filter" ]] && args+=("$filter")

    npx playwright test "${args[@]+"${args[@]}"}"
}

cmd_debug() {
    ensure_node
    ensure_playwright

    local filter="${1:-}"
    local args=(--headed --trace=on)

    [[ -n "$filter" ]] && args+=("$filter")

    PWDEBUG=1 npx playwright test "${args[@]}"
}

cmd_codegen() {
    ensure_node
    ensure_playwright

    local url="${1:-http://localhost:3000}"
    npx playwright codegen "$url"
}

cmd_report() {
    ensure_playwright
    npx playwright show-report
}

cmd_ci() {
    ensure_node
    ensure_playwright
    npx playwright test --retries=2 --reporter=html,github
}

cmd_update() {
    ensure_node
    ensure_playwright
    echo "Updating Playwright browsers..."
    npx playwright install
    echo "Done."
}

# --- Main ---

[[ $# -eq 0 ]] && usage

case "${1:-}" in
    help|--help|-h) usage ;;
esac

case "$1" in
    init)    shift; cmd_init "$@" ;;
    create)  shift; cmd_create "$@" ;;
    run)     shift; cmd_run "$@" ;;
    debug)   shift; cmd_debug "$@" ;;
    codegen) shift; cmd_codegen "$@" ;;
    report)  shift; cmd_report "$@" ;;
    ci)      shift; cmd_ci "$@" ;;
    update)  shift; cmd_update "$@" ;;
    *)       die "Unknown command: $1
Run: playwright.sh help" ;;
esac
