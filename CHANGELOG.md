# Changelog

## 1.0.1

- Fix `build.sh` exiting on every run except `--help` with `lock_file: unbound variable` under `set -u`. The lock path is assigned before it is exported. Introduced in 0288525.
- The release workflow no longer ignores a failing `build.sh --check`.
- Pull requests and pushes run unit tests, `bash -n`, shellcheck, and a macOS `swift build`.
- Controller port tests bind a port that is actually free, and skip when the emulator port range is busy. `ports_available` uses `SO_REUSEADDR`, so a port left in TIME_WAIT used to look free and the next plain bind raised `Address already in use`.

## Unreleased

- The DMG installer is `Install aeroandroid.command`. Its prompts, the other `.command` scripts, and the install notes are English. The installed app is `~/Applications/Android Subsystem.app`; the copy in the DMG is only a sample. Gatekeeper reports that it cannot verify the developer (ad-hoc signature).
- `tests/test_build_script.py` runs `build.sh` for real (every option, the lock chosen per chip and Android version, the Intel notice, the translation switch). `bash -n` only checks syntax, which is how the unbound variable got through.
- One `VERSION` file and one copyright line render both Info.plists. Mac apps made for Android apps carry the manager's version, and the manager refreshes them on start (`refresh-launchers`), so an update reaches the apps it made. Release builds fail if the tag and `VERSION` differ.
- Controller errors are English with a code; the Mac app shows its own translation for known codes (it was Chinese-only before).
- `ANDROID_SUBSYSTEM_BOOT_TIMEOUT` (240 s, 480 s off Apple Silicon); a process that exits just after starting is reported.
- `.gitignore` listed `work/` twice.

## 1.0.0

First official release. See `docs/RELEASE_NOTES.md`.
