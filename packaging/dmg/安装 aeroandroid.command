#!/bin/bash
# aeroandroid 0.2.1 lightweight installer (Apache-2.0, Copyright 2026 daniel.ye)
# Copies the source from this disk image to your home folder (the DMG is read-only),
# then runs build.sh: downloads the pinned runtime (SHA-256 verified), builds and installs
# ~/Applications/Android Subsystem.app. Extra arguments go to build.sh, e.g. --mirror cn.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
src="$here/aeroandroid-source"
dest="${AEROANDROID_DIR:-$HOME/aeroandroid}"
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  echo '需要 Apple Silicon Mac（M1–M5）/ Requires an Apple Silicon Mac.'; exit 1
fi
[[ -d "$src" ]] || { echo "找不到源码目录 / missing: $src"; exit 1; }
echo "==> 复制源码到 / Copying source to: $dest"
mkdir -p "$dest"
# ditto merges: existing runtime-cache/ in $dest is kept, so re-runs resume downloads.
ditto "$src" "$dest"
xattr -dr com.apple.quarantine "$dest" 2>/dev/null || true
chmod +x "$dest"/*.command "$dest/build.sh" "$dest"/scripts/*.sh 2>/dev/null || true
cd "$dest"
if [[ $# -eq 0 && -t 0 ]]; then
  echo
  echo '在中国大陆？输入 y 使用国内镜像（GitHub 代理 + 腾讯 Android SDK 镜像），直接回车自动选择。'
  read -r -p 'Use China mirrors? [y/N] ' ans || ans=''
  if [[ "$ans" == [yY]* ]]; then set -- --mirror cn; fi
fi
exec /bin/bash "$dest/build.sh" ${1+"$@"}
