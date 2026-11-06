## aeroandroid 1.1.0 · macOS DMG (Apple Silicon + Intel)

**Download:** `aeroandroid-1.1.0-macOS-universal.dmg` — Apple Silicon and Intel Macs (Intel: 2018 or newer), macOS 14+. Not Windows.

### What's new
- **English installer and docs.** The disk-image installer is `Install aeroandroid.command`. Its prompts and the install notes are English. Copyright is daniel.ye (Apache-2.0). See `NOTICE` and `docs/LICENSING.md`.
- **The Mac app is English by default.** It no longer follows the system language into Chinese. The Dock and Finder name is "Android Subsystem". Chinese remains available if you choose it in Settings.
- **Old installs upgrade when you run the installer once.** A Mac that still has saved Android 16 settings, or a legacy Google image, keeps its settings. Old apps and data are left as a backup. The Magisk ramdisk patched from the old image is dropped. Until you run the installer, the app explains what to do instead of failing.
- **Android 17 (API 37) is the only Android version.** Android 16 support, the Settings version picker, and helper `--android` for other versions are gone. `./build.sh --android 17` still works. Settings shows a fixed "Android 17 · API 37" row.
- **A new logo that follows light and dark mode.** The Dock and Finder icon is the light look.
- **Fixes:**
  - Installing an app the CPU cannot run (arm64-only code on an Intel Mac) shows the ARM-translation explanation. That failure used to appear as raw adb text.
  - Two Android apps with the same name get separate Mac apps, such as `Notes.app` and `Notes (notes2).app`, instead of an error.
  - APKs opened while the installer is busy are queued. They used to be dropped when the helper quit after the first install.
  - The guest screen no longer drops the last frame of a burst, so the last typed letter or the end of a scroll is not left off the Mac window.
  - A bad boot-timeout setting no longer crashes the controller. An empty `PATH` entry no longer adds the current folder to `PATH`. The graphics token file is private from the start. An unreadable config is reported, and the installer writes it in one step. If Android stops while starting, the error includes the end of `emulator.log`. One Mac app that cannot be refreshed no longer stops the others. Messages that told you to run `setup-mac.sh` now say to run the installer again.

Lightweight DMG: the manager (`Android Subsystem.app`) + `Install aeroandroid.command` + source + `README-FIRST.txt`. The Android runtime (about 1.8 GB) is downloaded during installation from official sources and each file is checked with SHA-256 (`--mirror cn` uses mirrors).

### Install
1. Install the Xcode Command Line Tools if you have not already: `xcode-select --install`. The installer builds the Mac app with Swift, so this is required.
2. Open the DMG, Control-click `Install aeroandroid.command` → **Open** (macOS 15: **System Settings → Privacy & Security → Open Anyway**).
3. The script copies the source to `~/aeroandroid` and runs `build.sh`. When it finishes, use `~/Applications/Android Subsystem.app`. The `Android Subsystem.app` inside the DMG is a prebuilt sample, not the install.
4. See `README-FIRST.txt` in the DMG.

The default is the full edition (AOSP + Magisk + microG, with Aurora Store and Fennec) on Android 17. Pure AOSP is `./build.sh --pure`.

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
