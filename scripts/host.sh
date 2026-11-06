# shellcheck shell=bash
# Sourced by build.sh and Install.command (needs $project_root).
# HOST_ARCH is arm64 on Apple Silicon (also in a Rosetta shell) and x86_64 on an Intel Mac.
HOST_ARCH="$(uname -m)"
if [[ "$HOST_ARCH" != arm64 && "$(sysctl -in hw.optional.arm64 2>/dev/null || true)" == 1 ]]; then HOST_ARCH=arm64; fi

# migrate_old_cache CACHE LOCK: before Android 16 was removed, the shared SDK downloads lived in CACHE/android16-macos.
# Reuse that folder under its new name, sdk-macos (same files, same SHA-256), so that an update does not download them
# again, and delete what the current lock does not list: the Android 16 emulator and system image.
migrate_old_cache() {
  local old="$1/android16-macos" new="$1/sdk-macos"
  [[ -d "$old" && ! -e "$new" ]] || return 0
  mv "$old" "$new"
  python3 - "$2" "$new" <<'PY'
import json, os, sys
keep = {os.path.basename(a['relative_path']) for a in json.load(open(sys.argv[1]))['archives']}
keep |= {'repository2-3.xml', 'images2-3.xml'}   # the SDK catalogs, fetched again on every run
for name in os.listdir(sys.argv[2]):
    path = os.path.join(sys.argv[2], name)
    if name not in keep and os.path.isfile(path):
        os.remove(path)
PY
}

# lock_for: the pinned runtime for this Mac: runtime-lock.json, or runtime-lock-x86_64.json on an Intel Mac.
lock_for() {
  local name=runtime-lock
  if [[ "$HOST_ARCH" != arm64 ]]; then name="$name-$HOST_ARCH"; fi
  : "${project_root:?project_root is not set}"
  printf '%s/scripts/%s.json\n' "$project_root" "$name"
}
