# Changelog

## Unreleased

- The package script checks the ad-hoc signature from a saved `codesign -dv` report. Searching that report through a pipe made `package-pkg.sh` exit 141 under `pipefail`.

- Distribute a macOS `.pkg` instead of a disk image. The package is ad-hoc signed when possible, and is not notarized: Gatekeeper reports an unidentified or unsafe developer, and the package is allowed in System Settings → Privacy & Security. The app installs to `/Applications`.
- Run the Android component download from inside the app, with an on-screen progress bar. The installer script is bundled in the app. The Android SDK license is shown before the download.
- Choose the download mirror from the public IP's country. Mainland China uses the existing China mirrors. Every other country, and a failed lookup, uses the official source. There is no mirror prompt.

- Host real Android AppWidgets in retained Mac desktop windows with live updates, standard bind/configuration flows, input, saved positions and size reporting. Add a Widgets picker and independent instances; keep provider app launches in the same live surface with explicit Android Back navigation.
- Build an original interactive widget probe in CI and test Java-to-Swift transport interoperability for small widget frames.

- Add original SIP Phone and SIP Messages using the user's own account, with verified TLS/TCP signaling, G.711 RTP, encrypted account-password storage and Android default-role integration. Messages use SIP MESSAGE; carrier SMS requires a provider gateway. Enable emulator audio input and add Mac microphone usage descriptions. No SIP/codec dependency is added.

- Share selected Mac folders directly through Android's document picker, with read/write or read-only access, seeking, in-place saves and no whole-file staging. Add native folder management, automatic reconnect, immediate revocation and protection against replacing an already open file. Retain the legacy copy exchange for apps without document-picker support.
- Compile the Java guest bridge against the pinned Android SDK in CI, alongside Python/shell and native Swift checks.

- Choose a host-aware Android memory budget at startup, with configurable automatic bounds and a Manual mode. Preserve existing explicit allocations. Show the active budget and next-start estimate, and discard incompatible Quick Boot snapshots without deleting userdata when the budget changes. Live VM resizing is not supported.
- Use English throughout the Mac UI, including installations with an old Chinese preference.
- Default to AOSP only. Optional root, microG and pre-installed apps require explicit `--with-gpl`. Fix fresh-cache AOSP installs requiring skipped provisioning archives.
- Keep the Apache-2.0 license and existing attribution. Add no third-party dependency; document the separate Android and JDK licenses without claiming a GPL-free runtime.

## 1.1.0

- The DMG installer is `Install aeroandroid.command`. Its prompts, the other `.command` scripts, and the install notes are English. Copyright attribution is daniel.ye. The installed app is `~/Applications/Android Subsystem.app`; the copy in the DMG is only a sample. Gatekeeper reports that it cannot verify the developer (ad-hoc signature).
- **Old installs are upgraded instead of stopping.** A Mac with the old Google-image setup (from the 0.2 releases: saved settings with `"android": 16` and no image type) used to fail with "Legacy Google image is retained only for migration". The app now switches to Android 17, keeps the old apps and data as a backup, and keeps your settings. If Android 17 is not installed yet it says to run the installer once, instead of showing a dead end.
- **English by default.** The app no longer follows the system language: it is English unless Chinese is chosen in Settings, and a missing string falls back to English (it used to fall back to Chinese, and also chose Chinese for any language other than English). The Dock and Finder name is "Android Subsystem" (it used to be a Chinese name), the app's base language is pinned to English, and the notification-settings screen inside Android is English.
- **Android 16 is removed; Android 17 is the only version.** Settings shows "Android 17 · API 37" instead of a picker; `build.sh --android 16` is refused (`--android 17` still works) and the "retry on Android 16" prompt is gone; the Android 16 locks and the `--android` option of the helper scripts are gone; `scripts/runtime-lock-17.json` and `runtime-lock-17-x86_64.json` became `runtime-lock.json` and `runtime-lock-x86_64.json`. A Mac that still has Android 16 is upgraded by running the installer once: it installs Android 17, keeps your settings, deletes the Android 16 system image, and keeps the Android 16 apps and data as a backup in `~/Library/Application Support/AndroidSubsystem/avd/`. Until then the app says what to do instead of failing, and the old install can still be stopped. The shared SDK downloads moved from `runtime-cache/android16-macos/` to `runtime-cache/sdk-macos/`: the installer renames your existing folder (nothing is downloaded again) and deletes the Android 16 emulator and system image zips from it.
- A test fails the build if the English text is missing a string the Chinese text has, or if Chinese is left in a user-facing file or file name.
- **A more modern logo that follows dark and light mode.** The "a" is frosted glass with a soft shadow, trailing three streaks of wind that fade in like motion trails, on a squircle tile (the shape of a macOS app icon). Light look: white glass on a blue-to-mint tile. Dark look: a glowing azure-to-mint "a" on a deep navy tile with soft corner glows and a thin lit rim. `assets/logo.svg` switches by itself with the viewer's theme (a `prefers-color-scheme` rule inside the file); `logo-light.svg` and `logo-dark.svg` are the two fixed looks, and the README picks between them with `<picture>`, which GitHub switches with its own theme setting. The Dock/Finder icon (`AppIcon.icns`, `logo-1024.png`) is the new light look; it stays one image because macOS does not switch a classic `.icns` between light and dark. The manager window draws the same logo in SwiftUI (`Logo.swift`) instead of a generic symbol. `scripts/make-logo.py` writes the SVGs (standard library only) and, with `--raster`, the PNG and ICNS (Pillow and numpy) from the same numbers; tests fail if any of them, or the SwiftUI drawing, drift from the generator.
- **Fixes from a full review of the app:**
  - Installing an app the CPU cannot run (arm64-only code on an Intel Mac) now shows the ARM-translation explanation. `adb` reports a failed install with a non-zero exit code and the reason on stderr, so the old check for `NO_MATCHING_ABIS` never saw it and the raw adb text was shown.
  - Two Android apps with the same name get separate Mac apps (`Notes.app`, `Notes (notes2).app`) instead of an error.
  - A bad `ANDROID_SUBSYSTEM_BOOT_TIMEOUT` no longer crashes the controller, and an empty `PATH` entry (no JDK configured) no longer puts the current folder on `PATH`.
  - The graphics token file is created private from the start; before, it was world-readable for a moment.
  - When Android stops while starting, the error ends with the end of `emulator.log`, which is usually the reason (for example no hardware acceleration).
  - One Mac app that cannot be refreshed after an update no longer stops the others from being refreshed.
  - The installer writes `config.json` in one step (a crash cannot leave a torn file), drops a stale Magisk ramdisk when the Android version changes, and reports an unreadable config instead of a traceback.
  - Error messages that told people to run `setup-mac.sh` now say to run the installer again.
  - APKs opened while the APK installer is busy are queued; they used to be dropped when the helper quit at the end of the first install.
  - The Android-side screen bridge no longer throws away the last picture of a burst: a change that landed inside the frame interval (the last typed letter, the end of a scroll) was never sent, so the Mac window could stay on a stale picture until something else changed. The newest picture now waits for its turn.

## 1.0.1

- Fix `build.sh` exiting on every run except `--help` with `lock_file: unbound variable` under `set -u`. The lock path is assigned before it is exported. Introduced in 0288525.
- The release workflow no longer ignores a failing `build.sh --check`.
- Pull requests and pushes run unit tests, `bash -n`, shellcheck, and a macOS `swift build`.
- Controller port tests bind a port that is actually free, and skip when the emulator port range is busy. `ports_available` uses `SO_REUSEADDR`, so a port left in TIME_WAIT used to look free and the next plain bind raised `Address already in use`.
- `tests/test_build_script.py` runs `build.sh` for real (every option, the lock chosen per chip and Android version, the Intel notice, the translation switch). `bash -n` only checks syntax, which is how the unbound variable got through.
- One `VERSION` file and one copyright line render both Info.plists. Mac apps made for Android apps carry the manager's version, and the manager refreshes them on start (`refresh-launchers`), so an update reaches the apps it made. Release builds fail if the tag and `VERSION` differ.
- Controller errors are English with a code; the Mac app shows its own translation for known codes (it was Chinese-only before).
- `ANDROID_SUBSYSTEM_BOOT_TIMEOUT` (240 s, 480 s off Apple Silicon); a process that exits just after starting is reported.
- `.gitignore` listed `work/` twice.

## 1.0.0

First official release. See `docs/RELEASE_NOTES.md`.
