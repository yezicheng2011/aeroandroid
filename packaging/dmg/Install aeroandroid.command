#!/bin/bash
# aeroandroid lightweight installer (Apache-2.0, Copyright 2026 daniel.ye)
# Copies the source from this disk image to your home folder (the DMG is read-only),
# then runs build.sh: downloads the pinned runtime (SHA-256 verified), builds and installs
# ~/Applications/Android Subsystem.app. Extra arguments go to build.sh, e.g. --mirror cn.
# Open the installed copy in ~/Applications. The Android Subsystem.app in this disk image
# is only a prebuilt sample.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
src="$here/aeroandroid-source"
dest="${AEROANDROID_DIR:-$HOME/aeroandroid}"
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Requires a Mac (Apple Silicon or Intel).'; exit 1
fi
[[ -d "$src" ]] || { echo "Missing source directory: $src"; exit 1; }
echo "==> Copying source to: $dest"
mkdir -p "$dest"
# ditto merges: existing runtime-cache/ in $dest is kept, so re-runs resume downloads.
ditto "$src" "$dest"
xattr -dr com.apple.quarantine "$dest" 2>/dev/null || true
chmod +x "$dest"/*.command "$dest/build.sh" "$dest"/scripts/*.sh 2>/dev/null || true
cd "$dest"
if [[ $# -eq 0 && -t 0 ]]; then
  echo
  echo 'In mainland China? Type y to use mirrors there (a GitHub proxy and the Tencent Android SDK mirror).'
  echo 'Press Return to let the installer choose.'
  read -r -p 'Use China mirrors? [y/N] ' ans || ans=''
  if [[ "$ans" == [yY]* ]]; then set -- --mirror cn; fi
fi
exec /bin/bash "$dest/build.sh" ${1+"$@"}
