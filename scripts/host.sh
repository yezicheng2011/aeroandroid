# shellcheck shell=bash
# Sourced by build.sh and Install.command (needs $project_root).
# HOST_ARCH is arm64 on Apple Silicon (also in a Rosetta shell) and x86_64 on an Intel Mac.
HOST_ARCH="$(uname -m)"
if [[ "$HOST_ARCH" != arm64 && "$(sysctl -in hw.optional.arm64 2>/dev/null || true)" == 1 ]]; then HOST_ARCH=arm64; fi

# lock_for ANDROID: runtime-lock.json (16), runtime-lock-17.json, with a -x86_64 suffix on Intel.
lock_for() {
  local name=runtime-lock
  if [[ "$1" != 16 ]]; then name="$name-$1"; fi
  if [[ "$HOST_ARCH" != arm64 ]]; then name="$name-$HOST_ARCH"; fi
  : "${project_root:?project_root is not set}"
  printf '%s/scripts/%s.json\n' "$project_root" "$name"
}
