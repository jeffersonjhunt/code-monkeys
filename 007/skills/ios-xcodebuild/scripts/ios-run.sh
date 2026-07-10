#!/usr/bin/env bash
#
# ios-run.sh — Deploy and launch an iOS app on simulator or device via SSH
#
# Usage:
#   ./scripts/ios-run.sh [simulator|device]
#
# Environment (required):
#   HOST_USER          — SSH user on macOS host
#   HOST_IP            — macOS host address (default: host.docker.internal)
#   HOST_PROJECT_PATH  — Absolute path to project on host
#   BUNDLE_ID          — Bundle identifier (default: com.example.app)
#   DEVICE_ID          — Target UDID (optional, auto-detected for simulator)
#

set -euo pipefail

TARGET=${1:-simulator}

HOST_USER="${HOST_USER:-$(whoami)}"
HOST_IP="${HOST_IP:-host.docker.internal}"
HOST_PROJECT_PATH="${HOST_PROJECT_PATH:?Error: Set HOST_PROJECT_PATH}"
BUNDLE_ID="${BUNDLE_ID:-com.example.app}"
DEVICE_ID="${DEVICE_ID:-}"

SSH_CMD="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 ${HOST_USER}@${HOST_IP}"

info() { echo "▸ $*"; }
error() { echo "✗ $*" >&2; exit 1; }

# Locate .app bundle
info "Locating .app bundle on host..."
APP_PATH=$(${SSH_CMD} "find '${HOST_PROJECT_PATH}/build/DerivedData' -name '*.app' -type d | head -1")

if [[ -z "$APP_PATH" ]]; then
    error "No .app bundle found. Run ./scripts/ios-build.sh first."
fi

APP_NAME=$(basename "$APP_PATH" .app)
info "Found: ${APP_PATH}"

if [[ "$TARGET" == "simulator" ]]; then
    # Auto-detect simulator
    if [[ -z "$DEVICE_ID" ]]; then
        info "Finding available iPhone simulator..."
        DEVICE_ID=$(${SSH_CMD} "xcrun simctl list devices available -j | python3 -c \"
import json, sys
data = json.load(sys.stdin)
for runtime, devices in data['devices'].items():
    if 'iOS' in runtime:
        for d in devices:
            if 'iPhone' in d['name'] and d['isAvailable']:
                print(d['udid'])
                sys.exit(0)
\"")
        [[ -z "$DEVICE_ID" ]] && error "No available iPhone simulator found."
    fi

    info "Booting simulator ${DEVICE_ID}..."
    ${SSH_CMD} "xcrun simctl boot '${DEVICE_ID}' 2>/dev/null || true"

    info "Installing ${APP_NAME}..."
    ${SSH_CMD} "xcrun simctl install '${DEVICE_ID}' '${APP_PATH}'"

    info "Launching..."
    ${SSH_CMD} "xcrun simctl launch '${DEVICE_ID}' '${BUNDLE_ID}'"

    ${SSH_CMD} "open -a Simulator"

    echo ""
    info "${APP_NAME} running on simulator ${DEVICE_ID}"
    echo ""
    echo "Commands:"
    echo "  Stop:      ssh ${HOST_USER}@${HOST_IP} \"xcrun simctl terminate '${DEVICE_ID}' '${BUNDLE_ID}'\""
    echo "  Logs:      ssh ${HOST_USER}@${HOST_IP} \"xcrun simctl spawn '${DEVICE_ID}' log stream --predicate 'subsystem == \\\"${BUNDLE_ID}\\\"'\""
    echo "  Uninstall: ssh ${HOST_USER}@${HOST_IP} \"xcrun simctl uninstall '${DEVICE_ID}' '${BUNDLE_ID}'\""
    echo "  Shutdown:  ssh ${HOST_USER}@${HOST_IP} \"xcrun simctl shutdown '${DEVICE_ID}'\""

elif [[ "$TARGET" == "device" ]]; then
    [[ -z "$DEVICE_ID" ]] && error "DEVICE_ID required for device deployment."

    info "Installing on device ${DEVICE_ID}..."
    ${SSH_CMD} "xcrun devicectl device install app --device '${DEVICE_ID}' '${APP_PATH}'" || \
        error "Device install failed. Ensure app is signed and device is trusted."

    info "${APP_NAME} installed on device ${DEVICE_ID}"
else
    error "Unknown target: ${TARGET}. Use 'simulator' or 'device'."
fi
