# Changelog

## 1.0.1

- Fix `build.sh` exiting on every run except `--help` with `lock_file: unbound variable` under `set -u`. The lock path is assigned before it is exported. Introduced in 0288525.
- The release workflow no longer ignores a failing `build.sh --check`.
- Pull requests and pushes run unit tests, `bash -n`, shellcheck, and a macOS `swift build`.
- Controller port tests bind a port that is actually free, and skip when the emulator port range is busy. `ports_available` uses `SO_REUSEADDR`, so a port left in TIME_WAIT used to look free and the next plain bind raised `Address already in use`.

## 1.0.0

First official release. See `docs/RELEASE_NOTES.md`.
