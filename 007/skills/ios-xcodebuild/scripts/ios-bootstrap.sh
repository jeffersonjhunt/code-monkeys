#!/usr/bin/env bash
#
# ios-bootstrap.sh — Scaffold a new iOS app project (SPM + SwiftUI + CLI build scripts)
#
# Usage:
#   ./scripts/ios-bootstrap.sh <AppName> [bundle-id]
#
# Example:
#   ./scripts/ios-bootstrap.sh MyApp com.example.myapp
#

set -euo pipefail

APP_NAME=${1:-}
BUNDLE_ID=${2:-com.example.${APP_NAME,,}}

if [[ -z "$APP_NAME" ]]; then
    echo "Usage: $0 <AppName> [bundle-id]" >&2
    echo "" >&2
    echo "Scaffolds an iOS project with:" >&2
    echo "  - Package.swift (executableTarget)" >&2
    echo "  - SwiftUI entry point" >&2
    echo "  - Info.plist" >&2
    echo "  - Build/run scripts for Docker-on-Mac workflow" >&2
    exit 1
fi

if [[ -d "$APP_NAME" ]]; then
    echo "Error: Directory '$APP_NAME' already exists." >&2
    exit 1
fi

echo "▸ Creating iOS project: $APP_NAME (${BUNDLE_ID})"

mkdir -p "$APP_NAME/Sources/$APP_NAME"
mkdir -p "$APP_NAME/Resources"
mkdir -p "$APP_NAME/scripts"

# --- Package.swift ---
cat > "$APP_NAME/Package.swift" << EOF
// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "$APP_NAME",
    platforms: [.iOS(.v17)],
    targets: [
        .executableTarget(
            name: "$APP_NAME",
            path: "Sources/$APP_NAME"
        )
    ]
)
EOF

# --- App Entry Point ---
cat > "$APP_NAME/Sources/$APP_NAME/${APP_NAME}App.swift" << EOF
import SwiftUI

@main
struct ${APP_NAME}App: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
EOF

# --- ContentView ---
cat > "$APP_NAME/Sources/$APP_NAME/ContentView.swift" << EOF
import SwiftUI

struct ContentView: View {
    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "swift")
                .font(.system(size: 60))
                .foregroundStyle(.orange)

            Text("$APP_NAME")
                .font(.largeTitle)
                .fontWeight(.bold)

            Text("Built from the CLI")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding()
    }
}

#Preview {
    ContentView()
}
EOF

# --- Info.plist ---
cat > "$APP_NAME/Resources/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleDisplayName</key>
    <string>$(PRODUCT_NAME)</string>
    <key>CFBundleExecutable</key>
    <string>$(PRODUCT_NAME)</string>
    <key>CFBundleIdentifier</key>
    <string>$(PRODUCT_BUNDLE_IDENTIFIER)</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>$(PRODUCT_NAME)</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSRequiresIPhoneOS</key>
    <true/>
    <key>UIApplicationSceneManifest</key>
    <dict>
        <key>UIApplicationSupportsMultipleScenes</key>
        <true/>
    </dict>
    <key>UILaunchScreen</key>
    <dict/>
    <key>UIRequiredDeviceCapabilities</key>
    <array>
        <string>arm64</string>
    </array>
    <key>UISupportedInterfaceOrientations</key>
    <array>
        <string>UIInterfaceOrientationPortrait</string>
        <string>UIInterfaceOrientationLandscapeLeft</string>
        <string>UIInterfaceOrientationLandscapeRight</string>
    </array>
</dict>
</plist>
EOF

# --- Build Script ---
cat > "$APP_NAME/scripts/build.sh" << 'BUILDEOF'
#!/usr/bin/env bash
set -euo pipefail

TARGET=${1:-simulator}
CONFIG=${2:-debug}

HOST_USER="${HOST_USER:-$(whoami)}"
HOST_IP="${HOST_IP:-host.docker.internal}"
HOST_PROJECT_PATH="${HOST_PROJECT_PATH:?Set HOST_PROJECT_PATH to the project dir on the macOS host}"
BUNDLE_ID="${BUNDLE_ID:-com.example.app}"
TEAM_ID="${TEAM_ID:-}"

SSH_CMD="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 ${HOST_USER}@${HOST_IP}"

info() { echo "▸ $*"; }
error() { echo "✗ $*" >&2; exit 1; }

[[ "$TARGET" == "device" && -z "$TEAM_ID" ]] && error "TEAM_ID required for device builds."

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

APP_NAME=$(basename "$HOST_PROJECT_PATH")

info "Building ${APP_NAME} for iOS ($TARGET, $CONFIG_FLAG)..."

BUILD_CMD="cd '${HOST_PROJECT_PATH}' && xcodebuild \
    -scheme '${APP_NAME}' -destination '${DESTINATION}' \
    -configuration '${CONFIG_FLAG}' -derivedDataPath './build/DerivedData' \
    PRODUCT_BUNDLE_IDENTIFIER='${BUNDLE_ID}' SWIFT_VERSION=5.9 ${CODE_SIGN} \
    -skipPackagePluginValidation -allowProvisioningUpdates build 2>&1 | tail -5"

${SSH_CMD} "${BUILD_CMD}" || error "Build failed."

info "Packaging .app bundle..."
PRODUCTS="${HOST_PROJECT_PATH}/build/DerivedData/Build/Products/${PLATFORM_DIR}"

PACKAGE_CMD="
set -e
mkdir -p '${PRODUCTS}/${APP_NAME}.app'
cp '${PRODUCTS}/${APP_NAME}' '${PRODUCTS}/${APP_NAME}.app/${APP_NAME}'
cp '${HOST_PROJECT_PATH}/Resources/Info.plist' '${PRODUCTS}/${APP_NAME}.app/Info.plist'
sed -i '' 's/\$(PRODUCT_BUNDLE_IDENTIFIER)/${BUNDLE_ID}/g' '${PRODUCTS}/${APP_NAME}.app/Info.plist'
sed -i '' 's/\$(PRODUCT_NAME)/${APP_NAME}/g' '${PRODUCTS}/${APP_NAME}.app/Info.plist'
codesign --force --sign - '${PRODUCTS}/${APP_NAME}.app'
echo '${PRODUCTS}/${APP_NAME}.app'
"

APP_PATH=$(${SSH_CMD} "${PACKAGE_CMD}") || error "Packaging failed."
info "Build succeeded: ${APP_PATH}"
BUILDEOF
chmod +x "$APP_NAME/scripts/build.sh"

# --- Run Script ---
cat > "$APP_NAME/scripts/run.sh" << 'RUNEOF'
#!/usr/bin/env bash
set -euo pipefail

TARGET=${1:-simulator}

HOST_USER="${HOST_USER:-$(whoami)}"
HOST_IP="${HOST_IP:-host.docker.internal}"
HOST_PROJECT_PATH="${HOST_PROJECT_PATH:?Set HOST_PROJECT_PATH}"
BUNDLE_ID="${BUNDLE_ID:-com.example.app}"
DEVICE_ID="${DEVICE_ID:-}"

SSH_CMD="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 ${HOST_USER}@${HOST_IP}"
APP_NAME=$(basename "$HOST_PROJECT_PATH")

info() { echo "▸ $*"; }
error() { echo "✗ $*" >&2; exit 1; }

APP_PATH=$(${SSH_CMD} "find '${HOST_PROJECT_PATH}/build/DerivedData' -name '${APP_NAME}.app' -type d | head -1")
[[ -z "$APP_PATH" ]] && error "${APP_NAME}.app not found. Run ./scripts/build.sh first."

info "Found: ${APP_PATH}"

if [[ "$TARGET" == "simulator" ]]; then
    if [[ -z "$DEVICE_ID" ]]; then
        DEVICE_ID=$(${SSH_CMD} "xcrun simctl list devices available -j | python3 -c \"
import json, sys
data = json.load(sys.stdin)
for runtime, devices in data['devices'].items():
    if 'iOS' in runtime:
        for d in devices:
            if 'iPhone' in d['name'] and d['isAvailable']:
                print(d['udid']); sys.exit(0)
\"")
        [[ -z "$DEVICE_ID" ]] && error "No available iPhone simulator."
    fi

    info "Booting simulator ${DEVICE_ID}..."
    ${SSH_CMD} "xcrun simctl boot '${DEVICE_ID}' 2>/dev/null || true"
    ${SSH_CMD} "xcrun simctl install '${DEVICE_ID}' '${APP_PATH}'"
    ${SSH_CMD} "xcrun simctl launch '${DEVICE_ID}' '${BUNDLE_ID}'"
    ${SSH_CMD} "open -a Simulator"
    info "${APP_NAME} running on simulator ${DEVICE_ID}"
else
    ${SSH_CMD} "xcrun devicectl device install app --device '${DEVICE_ID}' '${APP_PATH}'" || \
    error "Device install failed."
    info "${APP_NAME} installed on device ${DEVICE_ID}"
fi
RUNEOF
chmod +x "$APP_NAME/scripts/run.sh"

# --- .gitignore ---
cat > "$APP_NAME/.gitignore" << 'EOF'
build/
.swiftpm/
.DS_Store
*.xcodeproj
*.xcworkspace
xcuserdata/
EOF

echo "▸ Done! Project created at ./$APP_NAME"
echo ""
echo "Next steps:"
echo "  export HOST_USER=<mac-user>"
echo "  export HOST_IP=host.docker.internal"
echo "  export HOST_PROJECT_PATH=\"/Users/<mac-user>/path/to/$APP_NAME\""
echo "  export BUNDLE_ID=\"$BUNDLE_ID\""
echo "  cd $APP_NAME"
echo "  ./scripts/build.sh simulator debug"
echo "  ./scripts/run.sh simulator"
