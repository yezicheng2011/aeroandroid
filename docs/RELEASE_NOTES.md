## aeroandroid 1.0.1 · macOS DMG (Apple Silicon + Intel)

**Download:** `aeroandroid-1.0.1-macOS-universal.dmg` — Apple Silicon and Intel Macs (Intel: 2018 or newer), macOS 14+. Not Windows.

### What's new
- **Installer no longer crashes on startup:** `build.sh` exported `lock_file` before assigning it, so with `set -u` every run except `--help` exited immediately (`unbound variable`). 1.0.1 assigns the lock path first.
- **1.0.0 is the first stable release.** It is no longer marked a developer preview. 1.0.1 is the install fix on top of that release.
- **ARM-to-x86 translation on Intel Macs:** the full edition builds a Magisk module from AOSP's libndk_translation / berberis (Apache-2.0) so most arm64 APKs can run on the x86_64 system image. Skip it with `--no-arm-translation`. The pure edition does not download the Google APIs image.
- **Magisk module install fix:** `/data/adb/magisk` is filled in before the Magisk app is opened the first time, which fixes "Incomplete Magisk install" (microG and the later steps use the same path).
- **Mirrors on restricted networks:** F-Droid downloads try the Tsinghua and NJU mirrors first (`--mirror cn` / `FDROID_MIRROR`). A mirror whose file does not match the pinned SHA-256 is skipped.
- **Pre-installed apps follow the CPU:** on Intel, a native x86_64 build is preferred (Fennec, for example).
- **Signing:** the app and the DMG are ad-hoc signed. Gatekeeper says it cannot verify the developer. It does not say the file is damaged. Control-click → Open.
- **Copyright:** Copyright © 2026 daniel.ye (Apache-2.0). See `NOTICE` and `docs/LICENSING.md`.

Lightweight DMG: the manager (`Android Subsystem.app`) + `Install aeroandroid.command` + source + `README-FIRST.txt`. The Android runtime (about 1.8 GB) is downloaded during installation from official sources and each file is checked with SHA-256 (`--mirror cn` uses mirrors).

### Install
1. Install the Xcode Command Line Tools if you have not already: `xcode-select --install`. The installer builds the Mac app with Swift, so this is required.
2. Open the DMG, Control-click `Install aeroandroid.command` → **Open** (macOS 15: **System Settings → Privacy & Security → Open Anyway**).
3. The script copies the source to `~/aeroandroid` and runs `build.sh`. When it finishes, use `~/Applications/Android Subsystem.app`. The `Android Subsystem.app` inside the DMG is a prebuilt sample, not the install.
4. See `README-FIRST.txt` in the DMG.

The default is the full edition (AOSP + Magisk + microG, with Aurora Store and Fennec). Pure AOSP is `./build.sh --pure`.

### Signing
Ad-hoc signature (no Apple Developer certificate): Gatekeeper says it cannot verify the developer, and does not say the file is damaged. Control-click → Open. Check the download with `SHA256SUMS.txt`.

### Why there is no fully offline DMG
The Android Emulator, platform-tools, build-tools, cmdline-tools, platform, and system image are under the *Android Software Development Kit License Agreement*. Section 3.4 forbids redistribution, so they cannot be packed into the release. The installer downloads them on your Mac from Google (or a mirror) and asks you to accept that license.

### Third-party components and licenses
Inside the DMG:
- aeroandroid source, the manager app, and the MacBridge APK — Apache-2.0
- third_party/GSFProxy (microG GsfProxy) — Apache-2.0 (some docs and icons are CC-BY-SA-4.0 / CC0-1.0)

Downloaded at install time (not inside the DMG; each keeps its own license):
- Android SDK emulator / platform / build-tools / cmdline-tools / platform-tools / arm64 or x86_64 system image — Android SDK License Agreement
- OpenJDK 17 (Eclipse Temurin) — GPL-2.0 with Classpath Exception
- CPython 3.12 (python-build-standalone) — PSF License
- scrcpy v5.0.1 — Apache-2.0
- The full edition also downloads: Magisk, host_patch.sh, Vector, microg-spoof — GPL-3.0; microG GmsCore / Companion, Aurora Store, Fennec — see each upstream license
- The Intel full edition also downloads Google's x86_64 "Google APIs" system image, copies out only AOSP's ARM translator (libndk_translation / berberis, Apache-2.0), and discards the image — see `NOTICE` and `docs/LICENSING.md`
