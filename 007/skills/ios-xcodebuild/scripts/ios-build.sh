#!/usr/bin/env bash
#
# ios-build.sh — Build an iOS app on a macOS host via SSH
#
# Usage:
#   ./scripts/ios-build.sh [simulator|device] [debug|release]
#
# Environment (required):
#   HOST_USER          — SSH user on macOS host
#   HOST_IP            — macOS host address (default: host.docker.internal)
#   HOST_PROJECT_PATH  — Absolute path to project on host
#   BUNDLE_ID          — Bundle identifier (default: com.example.app)
#   TEAM_ID            — Apple Team ID (required for device builds)
#

set -euo pipefail

TARGET=${1:-simulator}
CONFIG=${2:-debug}

HOST_USER="${HOST_USER:-$(whoami)}"
HOST_IP="${HOST_IP:-host.docker.internal}"
HOST_PROJECT_PATH="${HOST_PROJECT_PATH:?Error: Set HOST_PROJECT_PATH to the absolute project path on the macOS host}"
BUNDLE_ID="${BUNDLE_ID:-com.example.app}"
TEAM_ID="${TEAM_ID:-}"

SSH_CMD="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 ${HOST_USER}@${HOST_IP}"

info() { echo "▸ $*"; }
error() { echo "✗ $*" >&2; exit 1; }

# Validate
[[ "$TARGET" != "simulator" && "$TARGET" != "device" ]] && error "Target must be 'simulator' or 'device'"
[[ "$CONFIG" != "debug" && "$CONFIG" != "release" ]] && error "Config must be 'debug' or 'release'"
[[ "$TARGET" == "device" && -z "$TEAM_ID" ]] && error "TEAM_ID is required for device builds"

# Determine xcodebuild settings
if [[ "$TARGET" == "simulator" ]]; then
    DESTINATION="generic/platform=iOS Simulator"
    CODE_SIGN=""
else
    DESTINATION="generic/platform=iOS"
    CODE_SIGN="CODE_SIGN_IDENTITY=\"Apple Development\" DEVELOPMENT_TEAM=\"${TEAM_ID}\""
fi

CONFIG_FLAG="Debug"; [[ "$CONFIG" == "release" ]] && CONFIG_FLAG="Release"
PLATFORM_DIR="${CONFIG_FLAG}-iphonesimulator"
[[ "$TARGET" == "device" ]] && PLATFORM_DIR="${CONFIG_FLAG}-iphoneos"

APP_NAME=$(${SSH_CMD} "cd '${HOST_PROJECT_PATH}' && python3 -c \"
import json, subprocess
out = subprocess.check_output(['swift', 'package', 'dump-package'], text=True)
print(json.loads(out)['name'])
\" 2>/dev/null || basename '${HOST_PROJECT_PATH}'")

info "Building ${APP_NAME} for iOS ($TARGET, $CONFIG_FLAG)..."
info "Host: ${HOST_USER}@${HOST_IP}:${HOST_PROJECT_PATH}"

# Compile
BUILD_CMD="cd '${HOST_PROJECT_PATH}' && xcodebuild \
    -scheme '${APP_NAME}' \
    -destination '${DESTINATION}' \
    -configuration '${CONFIG_FLAG}' \
    -derivedDataPath './build/DerivedData' \
    PRODUCT_BUNDLE_IDENTIFIER='${BUNDLE_ID}' \
    SWIFT_VERSION=5.9 \
    ${CODE_SIGN} \
    -skipPackagePluginValidation \
    -allowProvisioningUpdates \
    build 2>&1 | tail -5"

info "Compiling on host..."
${SSH_CMD} "${BUILD_CMD}" || error "Build failed."

# Package into .app bundle
info "Packaging .app bundle..."
PRODUCTS="${HOST_PROJECT_PATH}/build/DerivedData/Build/Products/${PLATFORM_DIR}"

PACKAGE_CMD="
set -e
APP_DIR='${PRODUCTS}/${APP_NAME}.app'
BINARY='${PRODUCTS}/${APP_NAME}'
PLIST='${HOST_PROJECT_PATH}/Resources/Info.plist'

mkdir -p \"\${APP_DIR}\"
cp \"\${BINARY}\" \"\${APP_DIR}/${APP_NAME}\"
cp \"\${PLIST}\" \"\${APP_DIR}/Info.plist\"

sed -i '' 's/\\\$(PRODUCT_BUNDLE_IDENTIFIER)/${BUNDLE_ID}/g' \"\${APP_DIR}/Info.plist\"
sed -i '' 's/\\\$(PRODUCT_NAME)/${APP_NAME}/g' \"\${APP_DIR}/Info.plist\"

codesign --force --sign - \"\${APP_DIR}\"
echo \"\${APP_DIR}\"
"

APP_PATH=$(${SSH_CMD} "${PACKAGE_CMD}") || error "Packaging failed."

info "Build succeeded: ${APP_PATH}"
echo ""
echo "Next: ./scripts/ios-run.sh ${TARGET}"
