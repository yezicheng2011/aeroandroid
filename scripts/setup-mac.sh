#!/usr/bin/env bash
# Online developer setup. Prefer cached SDK archives via setup-offline-mac.py when available.
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
version="${1:-16}"
[[ "$version" == 16 || "$version" == 17 ]] || { echo 'Choose Android 16 or 17.' >&2; exit 1; }
[[ "$(uname -s)" == Darwin ]] || { echo 'Requires a Mac.' >&2; exit 1; }
command -v brew >/dev/null || { echo 'Install Homebrew from https://brew.sh, then run this script again.' >&2; exit 1; }
xcrun --find swift >/dev/null || { echo 'Install Xcode Command Line Tools with xcode-select --install.' >&2; exit 1; }
brew install python scrcpy openjdk@17
brew install --cask android-commandlinetools
JAVA_HOME="$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home"
export JAVA_HOME
sdk_root="${ANDROID_SUBSYSTEM_SDK:-$HOME/Library/Android/sdk}"
manager="$(brew --prefix)/share/android-commandlinetools/cmdline-tools/latest/bin/sdkmanager"
mkdir -p "$sdk_root"
# Interactive SDK license review, rather than silently accepting SDK terms.
"$manager" --sdk_root="$sdk_root" --licenses
available="$("$manager" --sdk_root="$sdk_root" --list --channel=0)"
host_arch="$(uname -m)"
if [[ "$host_arch" != arm64 && "$(sysctl -in hw.optional.arm64 2>/dev/null || true)" == 1 ]]; then host_arch=arm64; fi
abi=x86_64; [[ "$host_arch" == arm64 ]] && abi=arm64-v8a
api="$((version + 20))"; [[ "$version" == 17 ]] && api="37.0"   # Android 17 is published as android-37.0
image="system-images;android-$api;default;$abi"
if ! printf '%s\n' "$available" | grep -F "$image" >/dev/null; then
  echo "The SDK does not currently offer the stable $abi image: $image" >&2
  echo 'Android 16 remains supported; no older system will be installed automatically.' >&2
  exit 1
fi
"$manager" --sdk_root="$sdk_root" 'platform-tools' 'emulator' 'platforms;android-36' 'build-tools;36.0.0' "$image"
export ANDROID_SUBSYSTEM_SDK="$sdk_root"
python3 - "$project_root/backend/subsystem.py" "$version" "$sdk_root" <<'PYSETUP'
import json, subprocess, sys
subprocess.run([sys.executable, sys.argv[1], 'configure', json.dumps({'android': int(sys.argv[2]), 'image_tag': 'default', 'sdk': sys.argv[3]})], check=True)
PYSETUP
"$project_root/scripts/build-guest.sh"
"$project_root/scripts/build-mac.sh"
echo 'Setup complete. Open dist/Android Subsystem.app.'
