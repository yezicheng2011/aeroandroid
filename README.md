<p align="center"><img src="assets/logo.svg" width="128" alt="aeroandroid logo"></p>

<h1 align="center">aeroandroid</h1>
<p align="center"><b>Android apps as real Mac apps, on Apple Silicon.</b><br>
Double-click an <code>.apk</code>. It installs like a <code>.dmg</code> app, shows up in Launchpad and the Dock,<br>
and opens in its own window with nothing else on screen.</p>

---

## What you get

1. **Download an `.apk`, double-click it.** A small installer appears, installs the app into the Android subsystem and
   saves a Mac app for it in `~/Applications`. That app then opens by itself.
2. **Every Android app is a normal Mac app.** Own icon, own Dock tile, ⌘-Tab, ⌘-Q, Launchpad and Spotlight.
   Opening it shows only that app's window. No manager window, no emulator window.
3. **Ready out of the box.** The full edition ships with microG, [Aurora Store](https://auroraoss.com) and
   [Fennec](https://f-droid.org/packages/org.mozilla.fennec_fdroid/) (Firefox) installed.
4. **Your Mac's camera works.** Android camera apps use the Mac's physical camera.

Under the hood it is the official Android Emulator running the AOSP Android 16 arm64 image, with a native Metal
window per app, plus an Android-side bridge for input, clipboard and notifications.

## Install

Requires an Apple Silicon Mac (M1 or later), macOS 14+, the Xcode Command Line Tools (`xcode-select --install`),
about 20 GB of free disk and an internet connection (about 1.8 GB of Android runtime plus the apps).

```bash
./build.sh                # full edition: AOSP + Magisk + microG + pre-installed apps
./build.sh --pure         # AOSP only: no Magisk, no microG, no GPL-3.0 parts
./build.sh --mirror cn    # mainland China: GitHub via proxy, Android SDK via Tencent mirror
```

Details and troubleshooting: [BUILD.md](BUILD.md). Every download is checked against a pinned SHA-256.
Prefer not to build? An offline package is at <https://aeroandroid.com/releases.html>.

The installer saves a Quick Boot snapshot at the end, so the first app you open starts in seconds instead of
cold booting (the snapshot takes disk space about equal to the memory setting).

After the build, `Android Subsystem.app` is in `~/Applications`. Open it once: that makes the APK installer
the default app for `.apk` files. From then on, double-clicking any APK is all it takes.

## Signing and downloads

Release builds are signed ad hoc (free, no Apple Developer account), including the installer helper and the DMG,
so macOS does not call the app "damaged". Without a paid Developer ID and notarization macOS still says it cannot
verify the developer: right-click the app and choose Open, or run
`xattr -dr com.apple.quarantine "/Applications/Android Subsystem.app"`. Mac apps the subsystem creates for your
Android apps are made and signed on your own Mac, so they open without any prompt.

## How it fits together

One executable plays three roles, chosen by its `Info.plist`:

| Role | Where | What it does |
|------|-------|--------------|
| Manager | `Android Subsystem.app` | Library, files, settings, menu bar item |
| APK installer | `Android Subsystem.app/Contents/Helpers/APK Installer.app` | Owns `.apk`; installs, builds the Mac app, opens it, quits |
| Android app | `~/Applications/<App name>.app` (one per app) | Starts the subsystem if needed and shows that app's window |

| Path | Role |
|------|------|
| `macos/` | The Swift app: windows, Metal rendering, the three roles (`main.swift`, `AppMode.swift`) |
| `guest/` | Java bridge inside Android: frame transport, input method, notifications, clipboard, app icons |
| `backend/subsystem.py` | Controller: boots the emulator, installs APKs, builds the Mac apps (`install-app`) |
| `scripts/` | Build, provisioning (Magisk, microG), pre-installed apps (`preinstall.json`), logo generator |
| `assets/` | Logo (`logo.svg`, `logo-1024.png`) and `AppIcon.icns` |

## Pre-installed apps

microG (Services, Companion, GSFProxy) is provisioned by `scripts/provision-microg.py`. Aurora Store and Fennec
come from `scripts/preinstall.json`, pinned by APK and signing-certificate SHA-256; nothing unpinned is installed.
Add more with `python3 scripts/preinstall-apps.py --pin <https APK url>` and paste the printed entry.

microG is an open-source compatibility layer, not Google Play services: a successful install does not guarantee
that every Google API, Play Integrity or banking app works. See [docs/MICROG.md](docs/MICROG.md).

## Known limits

- Apple Silicon and macOS 14+ only. Android 16 (AOSP) only.
- The subsystem keeps running in the background after you close an app's window; stop it from the menu bar item.
- Camera: the Mac camera is passed to the emulator as `webcam0` for both the front and back camera.
  macOS asks for camera permission the first time.
- Several `.apk` files opened together are installed as one split-APK set.
- Not GApps: no Google Play Store, Chrome or proprietary DroidGuard.

## Not included in this repository

The `microg-spoof/` module and Magisk's `host_patch.sh` are GPL-3.0 and are fetched by `build.sh` from upstream
for the full edition (checksummed, with a notice); they stay GPL-3.0. Prebuilt APKs and the runtime cache are
produced by the build scripts.

## License

Apache-2.0, Copyright 2026 daniel.ye. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE) for third-party components.
