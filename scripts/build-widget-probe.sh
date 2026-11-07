#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
sdk_root="${ANDROID_SUBSYSTEM_SDK:-${ANDROID_HOME:-$HOME/Library/Android/sdk}}"
tools="$sdk_root/build-tools/36.0.0"
android_jar="$sdk_root/platforms/android-36/android.jar"
if [[ -n "${JAVA_HOME:-}" ]]; then export PATH="$JAVA_HOME/bin:$PATH"; fi
if [[ ! -f "$android_jar" || ! -x "$tools/aapt2" ]]; then
  echo 'Android SDK platform 36 and Build Tools 36.0.0 are required.' >&2; exit 1
fi
build="$project_root/work/widget-probe"
fixture="$project_root/tests/widget_probe"
key_dir="${ANDROID_SUBSYSTEM_SIGNING_DIR:-$HOME/Library/Application Support/AndroidSubsystem/signing}"
[[ -f "$key_dir/companion.jks" ]] || "$project_root/scripts/build-guest.sh"
rm -rf "$build/classes" "$build/dex" "$build/generated"
mkdir -p "$build/classes" "$build/dex" "$build/generated" "$project_root/artifacts"
"$tools/aapt2" compile --dir "$fixture/res" -o "$build/resources.zip"
"$tools/aapt2" link -I "$android_jar" --manifest "$fixture/AndroidManifest.xml" \
  --java "$build/generated" --version-code 1 --version-name 0.1.0 \
  -o "$build/unsigned.apk" "$build/resources.zip"
sources=()
while IFS= read -r -d '' source; do sources+=("$source"); done < <(find "$fixture" "$build/generated" -name '*.java' -print0)
javac --release 8 -encoding UTF-8 -classpath "$android_jar" -d "$build/classes" "${sources[@]}"
jar cf "$build/classes.jar" -C "$build/classes" .
"$tools/d8" --lib "$android_jar" --min-api 31 --output "$build/dex" "$build/classes.jar"
"${PYTHON:-python3}" - "$build/unsigned.apk" "$build/dex/classes.dex" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], 'a', compression=zipfile.ZIP_DEFLATED) as archive:
    archive.write(sys.argv[2], 'classes.dex')
PY
"$tools/zipalign" -f 4 "$build/unsigned.apk" "$build/aligned.apk"
"$tools/apksigner" sign --ks "$key_dir/companion.jks" --ks-key-alias companion \
  --ks-pass pass:android --key-pass pass:android \
  --out "$project_root/artifacts/WidgetProbe.apk" "$build/aligned.apk"
"$tools/apksigner" verify "$project_root/artifacts/WidgetProbe.apk"
echo "Built: $project_root/artifacts/WidgetProbe.apk"
