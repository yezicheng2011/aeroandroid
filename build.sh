#!/usr/bin/env bash
# aeroandroid self-build: one command to check prerequisites, download the
# pinned runtime (SHA-256 verified) into ./runtime-cache and run the installer.
# Copyright 2026 daniel.ye — Apache-2.0
set -euo pipefail

project_root="$(cd "$(dirname "$0")" && pwd)"
source "$project_root/scripts/host.sh"
cache="${ANDROID_SUBSYSTEM_CACHE:-$project_root/runtime-cache}"
mirror="auto"          # auto | cn | global
with_gpl=0
android=17
download_only=0
check_only=0
arm_translation=1
gh_mirror="${GH_MIRROR:-https://gh-proxy.com/}"
sdk_mirror="${SDK_MIRROR:-https://mirrors.cloud.tencent.com/AndroidSDK/}"
google_base="https://dl.google.com/android/repository/"
gpl_source_url="https://aeroandroid.com/releases/AndroidSubsystem-source.zip"
gpl_source_sha256="6129306d2423245f7dc74906f3a39d51927934f7e845b2d050c5698f34d39ade"
magisk_patch_url="https://raw.githubusercontent.com/topjohnwu/Magisk/v31.0/scripts/host_patch.sh"
magisk_patch_sha256="1720669a684f75fe90a7318868dd4528f2e736a5ad5363f92a3c51c848d79703"

usage() {
  cat <<'USAGE'
Usage: ./build.sh [options]

  --mirror cn|global|auto  Download source. cn uses a GitHub proxy and the
                           Tencent Android SDK mirror. auto (the default) reads
                           this Mac's public country code: mainland China uses
                           that mirror, and every other country uses the official
                           source. If the country cannot be determined, the
                           official source is used.
  --pure                  AOSP-only edition (default): no Magisk, microG or
                           pre-installed apps. No optional GPL extensions.
  --with-gpl              Explicitly opt into Magisk, microG, Aurora Store and
                           Fennec, including GPL-3.0 extensions from upstream.
  --no-arm-translation     Intel Macs only: skip ARM translation (saves a 2 GB download and
                           8 GB of disk) and with it support for arm64-only apps.
  --download-only          Only fill ./runtime-cache, do not install.
  --check                  Only check prerequisites.
  -h, --help               Show this help.

Environment: GH_MIRROR, SDK_MIRROR, FDROID_MIRROR, ANDROID_SUBSYSTEM_CACHE.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mirror) mirror="${2:-}"; shift 2 ;;
    --mirror=*) mirror="${1#*=}"; shift ;;
    --with-gpl) with_gpl=1; shift ;;
    --pure) with_gpl=0; shift ;;
    --no-arm-translation) arm_translation=0; shift ;;
    --android) android="${2:-}"; shift 2 ;;
    --android=*) android="${1#*=}"; shift ;;
    --download-only) download_only=1; shift ;;
    --check) check_only=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done
# Android 17 is the only version. --android stays accepted so that old command lines keep working.
[[ "$android" == 17 ]] || { echo "Android $android is no longer supported: aeroandroid runs Android 17." >&2; exit 2; }
lock_file="$(lock_for)"
export ANDROID_SUBSYSTEM_LOCK="$lock_file" AEROANDROID_ARM_TRANSLATION="$arm_translation"
case "$mirror" in auto|cn|global) ;; *) echo "--mirror must be cn, global or auto" >&2; exit 2 ;; esac

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

sha256_of() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
  else sha256sum "$1" | awk '{print $1}'; fi
}

check_prereqs() {
  local ok=1
  say 'Checking prerequisites'
  if [[ "$(uname -s)" != Darwin ]]; then
    echo '  ✗ Requires a Mac (Apple Silicon or Intel)'; ok=0
  else
    local ver; ver="$(sw_vers -productVersion)"
    if [[ "${ver%%.*}" -lt 14 ]]; then echo "  ✗ macOS $ver < 14"; ok=0; else echo "  ✓ macOS $ver $HOST_ARCH"; fi
    if xcrun --find swift >/dev/null 2>&1; then echo '  ✓ Xcode Command Line Tools'
    else echo '  ✗ Xcode Command Line Tools — run: xcode-select --install'; ok=0; fi
  fi
  for tool in curl unzip tar python3; do
    if command -v "$tool" >/dev/null 2>&1; then echo "  ✓ $tool"; else echo "  ✗ $tool"; ok=0; fi
  done
  echo '  · JDK 17, Android SDK/emulator, Python 3.12 and scrcpy are downloaded into runtime-cache (pinned versions); no system install needed.'
  local free_gb
  free_gb="$(df -Pk "$project_root" | awk 'NR==2{print int($4/1048576)}')"
  if [[ "$free_gb" -lt 20 ]]; then echo "  ✗ free disk space ${free_gb} GB < 20 GB"; ok=0; else echo "  ✓ ${free_gb} GB free"; fi
  [[ "$ok" == 1 ]]
}

pick_mirror() {
  [[ "$mirror" != auto ]] && return
  # scripts/mirror.py prints cn or global. A failed lookup, or a failed script, stays on the official source.
  local selected
  selected="$(python3 "$project_root/scripts/mirror.py" --choose)" || selected=global
  case "$selected" in
    cn|global) mirror="$selected" ;;
    *) mirror=global ;;
  esac
  say "Auto-selected mirror: $mirror"
}

# Rewrite an upstream URL for the chosen mirror. Integrity is always enforced
# by the pinned SHA-256, so a mirror cannot alter what gets installed.
mirror_url() {
  local url="$1"
  if [[ "$mirror" == cn ]]; then
    case "$url" in
      "$google_base"*) printf '%s%s\n' "$sdk_mirror" "${url#"$google_base"}"; return ;;
      https://github.com/*|https://raw.githubusercontent.com/*) printf '%s%s\n' "$gh_mirror" "$url"; return ;;
    esac
  fi
  printf '%s\n' "$url"
}

fetch() { # url dest sha256
  local url="$1" dest="$2" want="$3" try
  if [[ -f "$dest" && "$(sha256_of "$dest")" == "$want" ]]; then echo "  ✓ cached $(basename "$dest")"; return; fi
  mkdir -p "$(dirname "$dest")"
  for try in "$(mirror_url "$url")" "$url"; do
    echo "  ↓ $(basename "$dest")  ($try)"
    if curl -fL --retry 3 --retry-delay 2 -C - -o "$dest.part" "$try"; then
      if [[ "$(sha256_of "$dest.part")" == "$want" ]]; then mv "$dest.part" "$dest"; return; fi
      echo '    SHA-256 mismatch, retrying'; rm -f "$dest.part"
    fi
  done
  die "download failed: $url"
}

fetch_runtime() {
  say "Downloading runtime into $cache"
  local lock="$lock_file"
  migrate_old_cache "$cache" "$lock"
  local line url rel sha
  while IFS=$'\t' read -r url rel sha; do
    line="$rel"; fetch "$url" "$cache/$line" "$sha"
  done < <(python3 - "$project_root" "$lock" "$with_gpl" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location('installer', sys.argv[1] + '/scripts/setup-offline-mac.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
lock = json.load(open(sys.argv[2]))
for a in installer.selected_archives(lock, graphics_only=sys.argv[3] != '1'):
    print(a['url'], a['relative_path'], a['sha256'], sep='\t')
PY
)
  # SDK catalogs are read by setup-offline-mac.py; they are unsigned metadata.
  for cat in repository2-3.xml:repository2-3.xml sys-img/android/sys-img2-3.xml:images2-3.xml; do
    local src="${cat%%:*}" name="${cat##*:}"
    curl -fsSL --retry 3 -o "$cache/sdk-macos/$name" "$(mirror_url "$google_base$src")" \
      || curl -fsSL --retry 3 -o "$cache/sdk-macos/$name" "$google_base$src" \
      || die "cannot fetch $src"
  done
}

fetch_gpl() {
  cat <<'NOTICE'

  ──────────────────────────────────────────────────────────────────────
  GPL-3.0 NOTICE
  The following components are licensed under GPL-3.0, NOT Apache-2.0,
  and are downloaded from upstream because you are building the full edition (use --pure to skip):
    · microg-spoof/  (MicroG Signature Compatibility, derived from FakeGApps)
    · third_party/Magisk/host_patch.sh  (topjohnwu/Magisk v31.0)
  They stay under their own license. Do not redistribute them as Apache-2.0.
  ──────────────────────────────────────────────────────────────────────

NOTICE
  local tmp; tmp="$(mktemp -d)"
  fetch "$gpl_source_url" "$tmp/source.zip" "$gpl_source_sha256"
  unzip -q "$tmp/source.zip" 'AndroidSubsystem/microg-spoof/*' -d "$tmp"
  rm -rf "$project_root/microg-spoof"
  mv "$tmp/AndroidSubsystem/microg-spoof" "$project_root/microg-spoof"
  # The module's hooks exist unchanged in Android 17 (checked against android-17.0.0_r1);
  # only its Android-16-only SDK_INT gate needs to admit API 37. A modified GPL-3.0 file stays GPL-3.0.
  python3 - "$project_root/microg-spoof/src/dev/dan/androidsubsystem/microgspoof/SignatureCompat.java" <<'PY'
import sys
path = sys.argv[1]
text = open(path).read()
old = 'Build.VERSION.SDK_INT != 36) return;'
new = 'Build.VERSION.SDK_INT != 36 && Build.VERSION.SDK_INT != 37) return;'
if old not in text and new not in text:
    sys.exit('microg-spoof changed upstream: SDK_INT gate not found; refusing to continue')
open(path, 'w').write(text.replace(old, new))
PY
  mkdir -p "$project_root/third_party/Magisk"
  fetch "$magisk_patch_url" "$project_root/third_party/Magisk/host_patch.sh" "$magisk_patch_sha256"
  rm -rf "$tmp"
}

# Unpack a private JDK + build-tools + android.jar from the verified cache so
# the guest APKs can be compiled before the installer runs.
bootstrap_toolchain() {
  local tc="$cache/toolchain" lock="$lock_file" rel tmp top
  say "Preparing build toolchain in $tc"
  mkdir -p "$tc/sdk/build-tools" "$tc/sdk/platforms"
  for kind in jdk build-tools platform; do
    rel="$(python3 - "$lock" "$kind" <<'PY'
import json, sys
k = sys.argv[2]
for a in json.load(open(sys.argv[1]))['archives']:
    r = a['relative_path']
    if (k == 'jdk' and 'OpenJDK' in r) or (k == 'build-tools' and 'build-tools' in r) or (k == 'platform' and '/platform-3' in r):
        print(r); break
PY
)"
    [[ -n "$rel" ]] || die "$(basename "$lock") has no $kind entry"
    case "$kind" in
      jdk) [[ -d "$tc/jdk" ]] && continue ;;
      build-tools) [[ -d "$tc/sdk/build-tools/36.0.0" ]] && continue ;;
      platform) [[ -d "$tc/sdk/platforms/android-36" ]] && continue ;;
    esac
    tmp="$(mktemp -d)"
    if [[ "$rel" == *.tar.gz ]]; then tar -xzf "$cache/$rel" -C "$tmp"; else unzip -q "$cache/$rel" -d "$tmp"; fi
    top="$(find "$tmp" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
    case "$kind" in
      jdk) mv "$top" "$tc/jdk" ;;
      build-tools) mv "$top" "$tc/sdk/build-tools/36.0.0" ;;
      platform) mv "$top" "$tc/sdk/platforms/android-36" ;;
    esac
    rm -rf "$tmp"
  done
  local java_home="$tc/jdk"
  [[ -d "$java_home/Contents/Home" ]] && java_home="$java_home/Contents/Home"
  say 'Building guest APKs'
  (
    export JAVA_HOME="$java_home" ANDROID_SUBSYSTEM_SDK="$tc/sdk"
    /bin/bash "$project_root/scripts/build-guest.sh"
    /bin/bash "$project_root/scripts/build-graphics-probe.sh"
    if [[ "$with_gpl" == 1 ]]; then /bin/bash "$project_root/microg-spoof/build-microg-tools.sh"; fi
  )
}

intel_notice() {
  cat <<'NOTICE'

  ──────────────────────────────────────────────────────────────────────
  Intel Mac detected
  Android runs here as x86_64. Many Android apps, especially most 3D games,
  ship only arm64 code and need ARM translation to run. The optional
  --with-gpl edition adds it (one extra ~2 GB download from Google, slower
  than native). The default AOSP edition and --no-arm-translation cannot
  install those apps. Plain Java/Kotlin apps
  and apps with x86_64 code are not affected.
  ──────────────────────────────────────────────────────────────────────

NOTICE
}

main() {
  if [[ "$HOST_ARCH" != arm64 ]]; then intel_notice; fi
  check_prereqs || { [[ "$check_only" == 1 ]] && exit 1; die 'prerequisites missing'; }
  [[ "$check_only" == 1 ]] && { say 'All prerequisites OK'; exit 0; }
  pick_mirror
  # Pre-installed apps come from F-Droid; these mirrors carry identical files, and every APK is SHA-256 pinned.
  if [[ "$mirror" == cn ]]; then export FDROID_MIRROR="${FDROID_MIRROR:-https://mirrors.tuna.tsinghua.edu.cn/fdroid/repo/ https://mirror.nju.edu.cn/fdroid/repo/}"; fi
  fetch_runtime
  if [[ "$with_gpl" == 1 ]]; then fetch_gpl; fi
  if [[ "$download_only" == 1 ]]; then say "Runtime cache ready: $cache"; exit 0; fi
  bootstrap_toolchain
  export ANDROID_SUBSYSTEM_CACHE="$cache"
  if [[ "$with_gpl" == 1 ]]; then export ANDROID_SUBSYSTEM_GRAPHICS_ONLY=0
  else export ANDROID_SUBSYSTEM_GRAPHICS_ONLY=1; fi
  say 'Building and installing'
  /bin/bash "$project_root/Install.command"
}

main
