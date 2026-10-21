#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")" && pwd)"
python_bin="$HOME/Library/Application Support/AndroidSubsystem/runtime/python/bin/python3"
[[ -x "$python_bin" ]] || { echo '请先运行 Graphics-Install.command。'; read -r -p '按回车退出…' ignored; exit 1; }
if ! "$python_bin" "$project_root/scripts/validate-graphics-mac.py"; then
  echo '验收没有通过，请保留终端错误和诊断记录。'
  read -r -p '按回车退出…' ignored; exit 1
fi
read -r -p '按回车关闭此终端窗口…' ignored
