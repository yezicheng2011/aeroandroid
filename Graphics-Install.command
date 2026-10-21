#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")" && pwd)"
export ANDROID_SUBSYSTEM_GRAPHICS_ONLY=1
exec /bin/bash "$project_root/Install.command"
