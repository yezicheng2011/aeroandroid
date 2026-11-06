# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/). The version lives in the `VERSION` file.

## [Unreleased]

### Fixed
- `build.sh` exited with `lock_file: unbound variable` on every run except `--help`; a regression test now executes it.
- `magisk --install-module` failed with "Incomplete Magisk install" because Magisk's tools were never set up; they are now.
- Four controller tests failed on a clean checkout: two needed a built `MacBridge.apk`, two took a port with a socket
  option the product's own probe already uses.
- `BUILD.md` described the old default (pure AOSP); `.gitignore` listed `work/` twice.
- The version and copyright now come from one place (`VERSION`, `scripts/build-mac.sh`) and Mac apps made for Android
  apps carry the manager's version and are refreshed when the manager is updated.
- Controller errors are English with a code; the Mac app shows its own translation for known codes.

### Added
- CI on every push and pull request (Python tests, shell lint, `build.sh`, Swift build for Apple Silicon and Intel).
- `ANDROID_SUBSYSTEM_BOOT_TIMEOUT` (default 240 s, 480 s on Intel); a process that exits just after starting is reported.

## [0.3.0]

### Added
- Double-click an `.apk`: it is installed and opens as its own Mac app with its own Dock icon.
- Android 17 (default) and 16; Magisk root, microG and pre-installed apps (Aurora Store, Fennec).
- Game controller support and a 60 FPS option.
- Intel Mac support, including ARM-to-x86 translation for arm64-only apps.
- Mirrors for restricted networks; a new logo; Apache-2.0 licensing review.

### Fixed
- Mac apps exported for Android apps had no icon.
