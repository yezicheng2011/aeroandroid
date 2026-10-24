#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
[[ "$(uname -s)" == Darwin && "$(uname -m)" == arm64 ]] || { echo 'Build on an Apple Silicon Mac.' >&2; exit 1; }
xcrun --find swift >/dev/null
if [[ ! -f "$project_root/artifacts/MacBridge.apk" ]]; then "$project_root/scripts/build-guest.sh"; fi
(cd "$project_root/macos" && swift build -c release)
bin_path="$(cd "$project_root/macos" && swift build -c release --show-bin-path)"
app="$project_root/dist/Android Subsystem.app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources/backend"
cp "$bin_path/AndroidSubsystem" "$app/Contents/MacOS/AndroidSubsystem"
cp "$project_root/backend/subsystem.py" "$app/Contents/Resources/backend/"
cp "$project_root/artifacts/MacBridge.apk" "$app/Contents/Resources/"
xcrun clang -arch arm64 -mmacosx-version-min=14.0 -fobjc-arc -framework Cocoa \
  "$project_root/macos/AndroidEntry.m" -o "$app/Contents/Resources/AndroidEntry"
cat > "$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>dev.dan.androidsubsystem</string>
<key>CFBundleName</key><string>Android Subsystem</string>
<key>CFBundleDisplayName</key><string>安卓子系统</string>
<key>CFBundleExecutable</key><string>AndroidSubsystem</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.2.1</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>NSHighResolutionCapable</key><true/>
<key>CFBundleURLTypes</key><array><dict><key>CFBundleURLName</key><string>Android app launcher</string>
<key>CFBundleURLSchemes</key><array><string>android-subsystem</string></array></dict></array>
<key>CFBundleDocumentTypes</key><array><dict>
<key>CFBundleTypeName</key><string>Android Package</string>
<key>CFBundleTypeRole</key><string>Viewer</string><key>LSHandlerRank</key><string>Alternate</string>
<key>CFBundleTypeExtensions</key><array><string>apk</string></array>
</dict></array>
</dict></plist>
PLIST
codesign --force --sign - "$app/Contents/Resources/AndroidEntry"
codesign --force --sign - "$app"
codesign --verify --strict "$app"
echo "Built: $app"
echo 'Move this app to ~/Applications, then open it. Runtime dependencies remain external in this development build.'
