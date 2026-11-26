#!/usr/bin/env bash
# Build aeroandroid's macOS installer package (.pkg).
# Copyright 2026 daniel.ye — Apache-2.0
#
# The app is ad-hoc signed with codesign --sign -. The package is ad-hoc signed
# the same way when codesign accepts a flat package. There is no notarization
# and no paid signing identity. Gatekeeper is expected to report an
# unidentified or unsafe developer; the user allows it in Privacy & Security.
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
version="$(tr -d '[:space:]' < "$project_root/VERSION")"
app="$project_root/dist/Android Subsystem.app"
out="$project_root/out"
pkg="$out/aeroandroid-${version}-macOS-universal.pkg"

[[ "$(uname -s)" == Darwin ]] || { echo 'Build the package on a Mac.' >&2; exit 1; }
[[ -d "$app" ]] || { echo "Missing $app — run scripts/build-mac.sh first." >&2; exit 1; }
command -v pkgbuild >/dev/null
command -v productbuild >/dev/null

mkdir -p "$app/Contents/Resources/scripts"
cp "$project_root/scripts/install-runtime.py" \
   "$project_root/scripts/mirror.py" \
   "$project_root/scripts/setup-offline-mac.py" \
   "$project_root/scripts/runtime-lock.json" \
   "$project_root/scripts/runtime-lock-x86_64.json" \
   "$app/Contents/Resources/scripts/"

for needed in \
  "$app/Contents/Resources/scripts/install-runtime.py" \
  "$app/Contents/Resources/scripts/mirror.py" \
  "$app/Contents/Resources/scripts/setup-offline-mac.py" \
  "$app/Contents/Resources/scripts/runtime-lock.json" \
  "$app/Contents/Resources/scripts/runtime-lock-x86_64.json"
do
  [[ -f "$needed" ]] || { echo "App is missing bundled installer file: $needed" >&2; exit 1; }
done

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/root" "$stage/resources" "$out"

xattr -cr "$app"
codesign --force --timestamp=none --sign - "$app/Contents/Helpers/APK Installer.app"
codesign --force --deep --timestamp=none --sign - "$app"
codesign --verify --deep --strict "$app"
# Capture the whole codesign report, then search it. grep -q on a pipe exits
# early, codesign gets SIGPIPE, and set -o pipefail turns that into exit 141.
codesign -dv --verbose=2 "$app" >"$stage/codesign-app.txt" 2>&1
grep -q 'Signature=adhoc' "$stage/codesign-app.txt"

ditto "$app" "$stage/root/Android Subsystem.app"

pkgbuild \
  --identifier dev.dan.androidsubsystem \
  --version "$version" \
  --install-location /Applications \
  --component-plist "$project_root/packaging/pkg/component.plist" \
  --root "$stage/root" \
  "$stage/app.pkg"

sed "s/@VERSION@/$version/g" "$project_root/packaging/pkg/resources/welcome.html" > "$stage/resources/welcome.html"
sed "s/@VERSION@/$version/g" "$project_root/packaging/pkg/resources/conclusion.html" > "$stage/resources/conclusion.html"
sed "s/@VERSION@/$version/g" "$project_root/packaging/pkg/distribution.xml" > "$stage/distribution.xml"

productbuild \
  --distribution "$stage/distribution.xml" \
  --resources "$stage/resources" \
  --package-path "$stage" \
  "$pkg"

# Ad-hoc sign the package when codesign accepts it. A rejection leaves the
# package unsigned, which is still the unidentified-developer path.
if codesign --force --timestamp=none --sign - "$pkg" && codesign --verify --verbose=2 "$pkg"; then
  echo "Ad-hoc signed $pkg"
else
  echo "codesign did not ad-hoc sign the pkg; the app inside is still ad-hoc signed."
  echo "Opening the pkg is expected to require Privacy & Security approval."
fi

echo "Built: $pkg"
