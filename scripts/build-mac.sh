#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
# One place for the version (the VERSION file) and the copyright line; both Info.plists are rendered from them.
version="$(tr -d '[:space:]' < "$project_root/VERSION")"
copyright='Copyright © 2026 daniel.ye'
render() { sed -e "s|@VERSION@|$version|g" -e "s|@COPYRIGHT@|$copyright|g"; }
[[ "$(uname -s)" == Darwin ]] || { echo 'Build on a Mac.' >&2; exit 1; }
# Local builds target this Mac. AEROANDROID_UNIVERSAL=1 builds arm64 + x86_64 in one binary (releases).
archs=()
if [[ "${AEROANDROID_UNIVERSAL:-0}" == 1 ]]; then archs=(--arch arm64 --arch x86_64); fi
xcrun --find swift >/dev/null
if [[ ! -f "$project_root/artifacts/MacBridge.apk" ]]; then "$project_root/scripts/build-guest.sh"; fi
(cd "$project_root/macos" && swift build -c release -Xlinker -dead_strip ${archs[@]+"${archs[@]}"})
bin_path="$(cd "$project_root/macos" && swift build -c release ${archs[@]+"${archs[@]}"} --show-bin-path)"
app="$project_root/dist/Android Subsystem.app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources/backend"
cp "$bin_path/AndroidSubsystem" "$app/Contents/MacOS/AndroidSubsystem"
strip -x "$app/Contents/MacOS/AndroidSubsystem"   # smaller download; the app has no use for local symbols
cp "$project_root/backend/subsystem.py" "$app/Contents/Resources/backend/"
cp "$project_root/backend/storage_service.py" "$app/Contents/Resources/backend/"
# The first-run Android download lives in the app. Users do not run an external installer script.
mkdir -p "$app/Contents/Resources/scripts"
cp "$project_root/scripts/install-runtime.py" \
   "$project_root/scripts/mirror.py" \
   "$project_root/scripts/setup-offline-mac.py" \
   "$project_root/scripts/runtime-lock.json" \
   "$project_root/scripts/runtime-lock-x86_64.json" \
   "$app/Contents/Resources/scripts/"
cp "$project_root/artifacts/MacBridge.apk" "$app/Contents/Resources/"
cp "$project_root/assets/AppIcon.icns" "$app/Contents/Resources/AppIcon.icns"
render > "$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleDevelopmentRegion</key><string>en</string>
<key>CFBundleIdentifier</key><string>dev.dan.androidsubsystem</string>
<key>CFBundleName</key><string>Android Subsystem</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>CFBundleDisplayName</key><string>Android Subsystem</string>
<key>CFBundleExecutable</key><string>AndroidSubsystem</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>@VERSION@</string>
<key>CFBundleVersion</key><string>@VERSION@</string>
<key>NSHumanReadableCopyright</key><string>@COPYRIGHT@</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>NSCameraUsageDescription</key><string>Android apps in the subsystem use the Mac camera when you open a camera app.</string>
<key>NSMicrophoneUsageDescription</key><string>SIP calls in Android use the Mac microphone.</string>
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
cp "$app/Contents/MacOS/AndroidSubsystem" "$helper/Contents/MacOS/AndroidSubsystem"
cp "$project_root/assets/AppIcon.icns" "$helper/Contents/Resources/AppIcon.icns"
render > "$helper/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleDevelopmentRegion</key><string>en</string>
<key>CFBundleIdentifier</key><string>dev.dan.androidsubsystem.installer</string>
<key>CFBundleName</key><string>APK Installer</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>CFBundleExecutable</key><string>AndroidSubsystem</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>@VERSION@</string>
<key>CFBundleVersion</key><string>@VERSION@</string>
<key>NSHumanReadableCopyright</key><string>@COPYRIGHT@</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>LSUIElement</key><true/>
<key>NSCameraUsageDescription</key><string>Android apps in the subsystem use the Mac camera when you open a camera app.</string>
<key>NSMicrophoneUsageDescription</key><string>SIP calls in Android use the Mac microphone.</string>
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
