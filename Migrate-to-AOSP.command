#!/bin/bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")" && pwd)"
# Install.command stops the old backend before rewriting runtime settings.
# Source + cache must already be available; no running VM data is reset.
export ANDROID_SUBSYSTEM_GRAPHICS_ONLY=0
exec /bin/bash "$project_root/Install.command"
