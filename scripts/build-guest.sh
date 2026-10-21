#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
sdk_root="${ANDROID_SUBSYSTEM_SDK:-${ANDROID_HOME:-$HOME/Library/Android/sdk}}"
tools="$sdk_root/build-tools/36.0.0"
android_jar="$sdk_root/platforms/android-36/android.jar"
java_bin="${JAVA_HOME:+$JAVA_HOME/bin/}"
if [[ -n "${JAVA_HOME:-}" ]]; then export PATH="$JAVA_HOME/bin:$PATH"; fi
if [[ ! -f "$android_jar" || ! -x "$tools/aapt2" ]]; then
  echo 'Android 16 platform and Build Tools 36.0.0 are required.' >&2; exit 1
fi
build="$project_root/work/guest"
mkdir -p "$build/classes" "$build/dex" "$project_root/artifacts"
# Portable to macOS bash 3.2: enumerate sources using an array.
sources=()
while IFS= read -r -d '' source; do sources+=("$source"); done < <(find "$project_root/guest/src" -name '*.java' -print0)
"${java_bin}javac" -encoding UTF-8 --release 8 -classpath "$android_jar" -d "$build/classes" "${sources[@]}"
"${java_bin}jar" cf "$build/classes.jar" -C "$build/classes" .
"$tools/d8" --lib "$android_jar" --min-api 36 --output "$build/dex" "$build/classes.jar"
"$tools/aapt2" compile --dir "$project_root/guest/res" -o "$build/resources.zip"
"$tools/aapt2" link -I "$android_jar" --manifest "$project_root/guest/AndroidManifest.xml" \
  --version-code 1 --version-name 0.1.0 -o "$build/unsigned.apk" "$build/resources.zip"
"${PYTHON:-python3}" - "$build/unsigned.apk" "$build/dex/classes.dex" <<'PYZIP'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], 'a', compression=zipfile.ZIP_DEFLATED) as archive:
    archive.write(sys.argv[2], 'classes.dex')
PYZIP
"$tools/zipalign" -f 4 "$build/unsigned.apk" "$build/aligned.apk"
# Persist this key across builds so -r upgrades preserve the companion's permissions.
# Never distribute the private keystore.
key_dir="${ANDROID_SUBSYSTEM_SIGNING_DIR:-$HOME/Library/Application Support/AndroidSubsystem/signing}"
mkdir -p "$key_dir"
if [[ ! -f "$key_dir/companion.jks" ]]; then
  "${java_bin}keytool" -genkeypair -keystore "$key_dir/companion.jks" -storepass android -keypass android \
    -alias companion -dname 'CN=Android Subsystem Development' -keyalg RSA -keysize 2048 -validity 10000
  chmod 600 "$key_dir/companion.jks"
fi
"$tools/apksigner" sign --ks "$key_dir/companion.jks" --ks-key-alias companion \
  --ks-pass pass:android --key-pass pass:android --out "$project_root/artifacts/MacBridge.apk" "$build/aligned.apk"
"$tools/apksigner" verify "$project_root/artifacts/MacBridge.apk"
echo "Built: $project_root/artifacts/MacBridge.apk"
