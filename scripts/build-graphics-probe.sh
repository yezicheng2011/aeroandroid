#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
sdk_root="${ANDROID_SUBSYSTEM_SDK:-${ANDROID_HOME:-$HOME/Library/Android/sdk}}"
tools="$sdk_root/build-tools/36.0.0"
android_jar="$sdk_root/platforms/android-36/android.jar"
[[ -n "${JAVA_HOME:-}" ]] && export PATH="$JAVA_HOME/bin:$PATH"
build="$project_root/work/graphics-probe"
key_dir="${ANDROID_SUBSYSTEM_SIGNING_DIR:-$HOME/Library/Application Support/AndroidSubsystem/signing}"
[[ -f "$key_dir/companion.jks" ]] || "$project_root/scripts/build-guest.sh"
mkdir -p "$build/classes" "$build/dex" "$project_root/artifacts"
javac --release 8 -encoding UTF-8 -classpath "$android_jar" -d "$build/classes" "$project_root/tests/guest_probe/ProbeActivity.java"
jar cf "$build/classes.jar" -C "$build/classes" .
"$tools/d8" --lib "$android_jar" --min-api 36 --output "$build/dex" "$build/classes.jar"
"$tools/aapt2" link -I "$android_jar" --manifest "$project_root/tests/guest_probe/AndroidManifest.xml" -o "$build/unsigned.apk"
"${PYTHON:-python3}" - "$build/unsigned.apk" "$build/dex/classes.dex" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], 'a', compression=zipfile.ZIP_DEFLATED) as archive:
    archive.write(sys.argv[2], 'classes.dex')
PY
"$tools/zipalign" -f 4 "$build/unsigned.apk" "$build/aligned.apk"
"$tools/apksigner" sign --ks "$key_dir/companion.jks" --ks-key-alias companion --ks-pass pass:android --key-pass pass:android --out "$project_root/artifacts/GraphicsProbe.apk" "$build/aligned.apk"
"$tools/apksigner" verify "$project_root/artifacts/GraphicsProbe.apk"
echo "Built: $project_root/artifacts/GraphicsProbe.apk"
