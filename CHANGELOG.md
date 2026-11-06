# Changelog

## Unreleased

- **Old installs are upgraded instead of stopping.** A Mac with the old Google-image setup (from the 0.2 releases: saved settings with `"android": 16` and no image type) used to fail with "Legacy Google image is retained only for migration". The app now switches to the newest installed AOSP runtime (Android 17, else 16), keeps the old apps and data as a backup, and keeps your settings. If the new runtime is not installed yet it says to run the installer once, instead of showing a dead end.
- **English by default.** The app no longer follows the system language: it is English unless Chinese is chosen in Settings, and a missing string falls back to English (it used to fall back to Chinese, and also chose Chinese for any language other than English). The Dock and Finder name is "Android Subsystem" (it used to be a Chinese name), the app's base language is pinned to English, and the notification-settings screen inside Android is English.
- Android 17 is the default in the remaining helper scripts too (`scripts/setup-mac.sh`, `scripts/cache-runtime.py`), and the Settings picker lists it first.
- A test fails the build if the English text is missing a string the Chinese text has, or if Chinese is left in a user-facing file or file name.

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
