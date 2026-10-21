#!/bin/bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")" && pwd)"
# Compile and install the complete AOSP + Magisk + microG runtime.
export ANDROID_SUBSYSTEM_GRAPHICS_ONLY=0
exec /bin/bash "$project_root/Install.command"
