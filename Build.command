#!/bin/bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")" && pwd)"
# Download, compile and install AOSP by default. Pass --with-gpl explicitly
# to opt into the existing root, compatibility and pre-installed app extensions.
exec /bin/bash "$project_root/build.sh" ${1+"$@"}
