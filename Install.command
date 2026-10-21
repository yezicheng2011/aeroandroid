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
    printf '安装未完成（退出码：%s）。\n' "${result}"
  fi
  if [[ -n "${log_file}" ]]; then
    printf '完整构建日志：%s\n' "${log_file}"
  fi
  if [[ -t 0 ]]; then
    read -r -p '按回车关闭此窗口…' ignored
  fi
  exit "${result}"
}
trap finish EXIT
if [[ -f "$root/config.json" && ! -x "$root/runtime/python/bin/python3" ]]; then
  echo '现有安装的私有 Python 缺失，尚未修改配置。请先恢复原来的 runtime，再执行迁移。'
  exit 1
fi
mkdir -p "$root/logs"
log_file="$root/logs/install-$(date +%Y%m%d-%H%M%S)-$$.log"
# Process substitution is supported by the Bash 3.2 supplied with macOS.
# Keep stdout and stderr visible while retaining the complete build output.
exec > >(tee -a "$log_file") 2>&1
echo "源码目录：$project_root"
default_cache="$project_root/runtime-cache"
[[ -d "$default_cache" ]] || default_cache="$project_root/../runtime-cache"
cache="${ANDROID_SUBSYSTEM_CACHE:-$default_cache}"
echo "离线依赖：$cache"
[[ "$(uname -s)" == Darwin && "$(uname -m)" == arm64 ]] || { echo '需要在 M5 或其他 Apple Silicon Mac 上运行。'; exit 1; }
if ! xcrun --find swift >/dev/null 2>&1; then
  echo '需要 Xcode Command Line Tools。请先安装，再重新打开此文件。'
  echo '安装命令：xcode-select --install'
  exit 1
fi
python_archive="$cache/mac-tools/cpython-3.12.15+20261009-aarch64-apple-darwin-install_only.tar.gz"
[[ -f "$python_archive" ]] || { echo "缺少离线缓存：$python_archive"; exit 1; }
echo '正在校验 Python 引导程序…'
actual="$(shasum -a 256 "$python_archive" | awk '{print $1}')"
[[ "$actual" == '83dcb04777c798bd95f3687acf9ae84b09860272ee6bdfb05be8bcf9447f75b8' ]] || { echo 'Python 文件校验失败。'; exit 1; }
if [[ -f "$root/config.json" ]]; then
  echo '先退出管理应用，并使用旧版本后端停止现有子系统…'
  "$root/runtime/python/bin/python3" -u "$project_root/scripts/prepare-runtime-migration.py" --root "$root"
fi
mkdir -p "$root/runtime"
if [[ ! -x "$root/runtime/python/bin/python3" ]]; then tar -xzf "$python_archive" -C "$root/runtime"; fi
if [[ "${ANDROID_SUBSYSTEM_GRAPHICS_ONLY:-0}" == 1 ]]; then
  echo '本次只安装纯 AOSP 图形验收环境。Magisk 和 microG 可随后通过 Build.command 配置。'
  "$root/runtime/python/bin/python3" -u "$project_root/scripts/setup-offline-mac.py" "$cache" --graphics-only
else
  # Bash 3.2 treats an empty array as unset under set -u; keep these branches explicit.
  "$root/runtime/python/bin/python3" -u "$project_root/scripts/setup-offline-mac.py" "$cache"
fi
echo '安装完成。'
