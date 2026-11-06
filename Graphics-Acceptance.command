#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")" && pwd)"
python_bin="$HOME/Library/Application Support/AndroidSubsystem/runtime/python/bin/python3"
[[ -x "$python_bin" ]] || { echo 'Run Graphics-Install.command first.'; read -r -p 'Press Return to quit…' _; exit 1; }
if ! "$python_bin" "$project_root/scripts/validate-graphics-mac.py"; then
  echo 'Acceptance did not pass. Keep this terminal output and the diagnostics.'
  read -r -p 'Press Return to quit…' _; exit 1
fi
read -r -p 'Press Return to close this terminal window…' _
