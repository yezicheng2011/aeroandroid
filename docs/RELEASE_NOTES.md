> Release notes for 1.2.1. Changes since 1.1.0 are also listed in [CHANGELOG.md](../CHANGELOG.md).

## aeroandroid 1.2.1 · macOS package (Apple Silicon + Intel)

**Download:** `aeroandroid-1.2.1-macOS-universal.pkg` — Apple Silicon and Intel Macs (Intel: 2018 or newer), macOS 14+. Not Windows.

### Fixed in 1.2.1
- **Android setup no longer fails at 93% on macOS's built-in Python.** 1.2.0 stopped while unpacking the JDK with `TypeError: extractall() got an unexpected keyword argument 'filter'`, because `/usr/bin/python3` (3.9.6) has no tarfile extraction filters. 1.2.1 unpacks safely on that Python. Files already downloaded are reused; install 1.2.1 over 1.2.0 and open the app again.

### What's new in 1.2
- **The download is a `.pkg`, not a disk image.** It installs Android Subsystem into `/Applications`. The Android installer is inside the app. There is no separate install script to run.
- **Android downloads show a progress bar.** The first launch of the app fetches the runtime (about 1.8 GB), checks each file, and installs it. The Android SDK license is shown in the app before the download starts.
- **The mirror is chosen from your public location.** Mainland China uses the existing China mirrors (Tencent Android SDK mirror, a GitHub proxy, and the Tsinghua and NJU F-Droid mirrors for the optional full edition). Every other country uses the official source. If the location lookup fails, the official source is used. You are not asked to pick a mirror.
- **Ad-hoc signature only.** No Apple Developer account, no Developer ID, and no notarization. Gatekeeper reports the package as unsafe or from an unidentified developer. Allow it in **System Settings → Privacy & Security**. That warning is expected.

### Install
1. Install the Xcode Command Line Tools if you have not already: `xcode-select --install`.
2. Open the `.pkg`. When macOS says it is unsafe or cannot verify the developer, allow it in **System Settings → Privacy & Security**, then open it again.
3. Install. The app is `/Applications/Android Subsystem.app`. If macOS blocks the app, allow it in the same Privacy & Security pane.
4. Open the app, accept the Android SDK license, and wait for the progress bar to finish.

The default is Android 17, AOSP only. Optional GPL extensions are `./build.sh --with-gpl` from a source checkout.

### Signing
Ad-hoc signature (no paid Apple certificate): Gatekeeper says it cannot verify the developer, or that the package is unsafe. It does not say the file is damaged. Allow the package in System Settings → Privacy & Security. Check the download with `SHA256SUMS.txt`.

### Why the Android runtime is not inside the package
The Android Emulator, platform-tools, build-tools, cmdline-tools, platform, and system image are under the *Android Software Development Kit License Agreement*. Section 3.4 forbids redistribution, so they cannot be packed into the release. The app downloads them on your Mac from Google (or a mirror, when your public location is mainland China) and asks you to accept that license.

### Third-party components and licenses
Inside the package:
- aeroandroid and the MacBridge APK — Apache-2.0

Downloaded when you first open the app (not inside the package; each keeps its own license):
- Android SDK emulator / platform / build-tools / cmdline-tools / platform-tools / arm64 or x86_64 system image — Android SDK License Agreement
- OpenJDK 17 (Eclipse Temurin) — GPL-2.0 with Classpath Exception
- CPython 3.12 (python-build-standalone) — PSF License
- scrcpy v5.0.1 — Apache-2.0
- A source build with `--with-gpl` also downloads: Magisk, host_patch.sh, Vector, microg-spoof — GPL-3.0; microG GmsCore / Companion, Aurora Store, Fennec — see each upstream license
- The Intel full edition also downloads Google's x86_64 "Google APIs" system image, copies out only AOSP's ARM translator (libndk_translation / berberis, Apache-2.0), and discards the image — see `NOTICE` and `docs/LICENSING.md`
