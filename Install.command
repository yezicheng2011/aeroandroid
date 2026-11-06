#!/bin/bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")" && pwd)"
root="$HOME/Library/Application Support/AndroidSubsystem"
log_file=''
finish() {
  result=$?
  trap - EXIT
  set +e
  if [[ "${result}" != 0 ]]; then
    printf 'Install did not finish (exit code: %s).\n' "${result}"
  fi
  if [[ -n "${log_file}" ]]; then
    printf 'Full build log: %s\n' "${log_file}"
  fi
  if [[ -t 0 ]]; then
    read -r -p 'Press Return to close this window…' _
  fi
  exit "${result}"
}
trap finish EXIT
if [[ -f "$root/config.json" && ! -x "$root/runtime/python/bin/python3" ]]; then
  echo 'The existing installation is missing its private Python. No configuration was changed. Restore the original runtime, then run the migration again.'
  exit 1
fi
mkdir -p "$root/logs"
log_file="$root/logs/install-$(date +%Y%m%d-%H%M%S)-$$.log"
# Process substitution is supported by the Bash 3.2 supplied with macOS.
# Keep stdout and stderr visible while retaining the complete build output.
exec > >(tee -a "$log_file") 2>&1
echo "Source directory: $project_root"
default_cache="$project_root/runtime-cache"
[[ -d "$default_cache" ]] || default_cache="$project_root/../runtime-cache"
cache="${ANDROID_SUBSYSTEM_CACHE:-$default_cache}"
echo "Offline dependencies: $cache"
[[ "$(uname -s)" == Darwin ]] || { echo 'Requires a Mac.'; exit 1; }
source "$project_root/scripts/host.sh"
# build.sh exports the lock for the chosen Android version; run directly, default to Android 17.
export ANDROID_SUBSYSTEM_LOCK="${ANDROID_SUBSYSTEM_LOCK:-$(lock_for 17)}"
echo "Mac architecture: $HOST_ARCH; lock file: $(basename "$ANDROID_SUBSYSTEM_LOCK")"
if ! xcrun --find swift >/dev/null 2>&1; then
  echo 'Xcode Command Line Tools are required. Install them, then open this file again.'
  echo 'Install command: xcode-select --install'
  exit 1
fi
# The pinned Python for this Mac's architecture comes from the lock file.
read -r python_relative python_sha256 < <(/usr/bin/python3 - "$ANDROID_SUBSYSTEM_LOCK" <<'PY'
import json, sys
entry = next(a for a in json.load(open(sys.argv[1]))['archives'] if a.get('kind') == 'python')
print(entry['relative_path'], entry['sha256'])
PY
)
python_archive="$cache/$python_relative"
[[ -f "$python_archive" ]] || { echo "Missing offline cache: $python_archive"; exit 1; }
echo 'Checking the Python bootstrap…'
actual="$(shasum -a 256 "$python_archive" | awk '{print $1}')"
[[ "$actual" == "$python_sha256" ]] || { echo 'Python file checksum failed.'; exit 1; }
if [[ -f "$root/config.json" ]]; then
  echo 'Quit the manager app, and stop the existing subsystem with the previous backend…'
  "$root/runtime/python/bin/python3" -u "$project_root/scripts/prepare-runtime-migration.py" --root "$root"
fi
mkdir -p "$root/runtime"
if [[ ! -x "$root/runtime/python/bin/python3" ]]; then tar -xzf "$python_archive" -C "$root/runtime"; fi
if [[ "${ANDROID_SUBSYSTEM_GRAPHICS_ONLY:-0}" == 1 ]]; then
  echo 'This run installs only the pure AOSP graphics acceptance environment. Magisk and microG can be added later with Build.command.'
  "$root/runtime/python/bin/python3" -u "$project_root/scripts/setup-offline-mac.py" "$cache" --graphics-only
else
  # Bash 3.2 treats an empty array as unset under set -u; keep these branches explicit.
  "$root/runtime/python/bin/python3" -u "$project_root/scripts/setup-offline-mac.py" "$cache"
fi
echo 'Install complete.'
