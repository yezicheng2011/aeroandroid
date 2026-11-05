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
cp "$project_root/assets/AppIcon.icns" "$app/Contents/Resources/AppIcon.icns"
cat > "$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>dev.dan.androidsubsystem</string>
<key>CFBundleName</key><string>Android Subsystem</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>CFBundleDisplayName</key><string>安卓子系统</string>
<key>CFBundleExecutable</key><string>AndroidSubsystem</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.2.1</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>NSCameraUsageDescription</key><string>Android apps in the subsystem use the Mac camera when you open a camera app.</string>
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
# Hidden helper that owns the .apk file type: double-clicking an APK installs it and opens it
# as its own Mac app, without showing the manager window. Same executable, different role.
helper="$app/Contents/Helpers/APK Installer.app"
mkdir -p "$helper/Contents/MacOS" "$helper/Contents/Resources"
cp "$bin_path/AndroidSubsystem" "$helper/Contents/MacOS/AndroidSubsystem"
cp "$project_root/assets/AppIcon.icns" "$helper/Contents/Resources/AppIcon.icns"
cat > "$helper/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>dev.dan.androidsubsystem.installer</string>
<key>CFBundleName</key><string>APK Installer</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>CFBundleExecutable</key><string>AndroidSubsystem</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.2.1</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>LSUIElement</key><true/>
<key>NSCameraUsageDescription</key><string>Android apps in the subsystem use the Mac camera when you open a camera app.</string>
<key>AndroidMode</key><string>install</string>
<key>UTImportedTypeDeclarations</key><array><dict>
<key>UTTypeIdentifier</key><string>com.android.package-archive</string>
<key>UTTypeDescription</key><string>Android Package</string>
<key>UTTypeConformsTo</key><array><string>public.data</string><string>public.archive</string></array>
<key>UTTypeTagSpecification</key><dict>
<key>public.filename-extension</key><array><string>apk</string></array>
<key>public.mime-type</key><array><string>application/vnd.android.package-archive</string></array></dict>
</dict></array>
<key>CFBundleDocumentTypes</key><array><dict>
<key>CFBundleTypeName</key><string>Android Package</string>
<key>CFBundleTypeRole</key><string>Editor</string><key>LSHandlerRank</key><string>Owner</string>
<key>LSItemContentTypes</key><array><string>com.android.package-archive</string></array>
<key>CFBundleTypeExtensions</key><array><string>apk</string></array>
</dict></array>
</dict></plist>
PLIST
codesign --force --sign - "$helper"
codesign --force --sign - "$app"
codesign --verify --strict "$app"
echo "Built: $app"
echo 'Move this app to ~/Applications, then open it. Runtime dependencies remain external in this development build.'
