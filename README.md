<p align="center"><img src="assets/logo.svg" width="128" alt="aeroandroid logo"></p>

<h1 align="center">aeroandroid</h1>
<p align="center"><b>Android apps as real Mac apps, on Apple Silicon and Intel Macs.</b><br>
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

Under the hood it is the official Android Emulator running the AOSP Android image for your Mac's chip, with a native Metal
window per app, plus an Android-side bridge for input, clipboard and notifications.

## Install

**Download the official macOS installer** from [aeroandroid.com](https://aeroandroid.com/#download)
(`aeroandroid-1.0.1-macOS-universal.dmg`). You do not package a release yourself: the installer downloads the runtime and builds the Mac app on your machine.

Requires a Mac (Apple Silicon, or an Intel Mac from 2018 on), macOS 14+, the Xcode Command Line Tools
(`xcode-select --install`), about 20 GB of free disk and an internet connection. The DMG is about 1.3 MB;
the Android runtime (about 1.8 GB) is fetched during installation from official sources, because the Android
SDK license does not allow redistribution.

The default install is the full edition: Android 17, AOSP, Magisk, microG, Aurora Store, and Fennec.
`./build.sh --pure` is pure AOSP only (no Magisk, no microG, no pre-installed apps, no GPL-3.0 parts).

1. Run `xcode-select --install` if you have not already. The installer builds the Mac app with Swift, so the
   Command Line Tools are required.
2. Open the DMG, Control-click `Install aeroandroid.command` and choose **Open**, then **Open** again.
   On macOS 15, if it was blocked: **System Settings → Privacy & Security → Open Anyway**.
3. Accept the Android SDK license when asked (type `YES`) and wait. The script copies the source to
   `~/aeroandroid` and runs `build.sh`. In mainland China, type `y` at the mirror prompt, or press Return
   and let it choose. When it finishes it opens `~/Applications/Android Subsystem.app`.

Use that installed copy. The `Android Subsystem.app` inside the DMG is a prebuilt sample so you can confirm
the app opens on your Mac. Do not use it as your install: its Android-side bridge is signed differently from
the copy built on your Mac, and mixing the two fails with `Guest bridge install failed`.

The installer saves a Quick Boot snapshot at the end, so the first app you open starts in seconds instead of
cold booting (the snapshot takes disk space about equal to the memory setting). Open the installed Android
Subsystem once: that makes the APK installer the default app for `.apk` files. From then on, double-clicking
any APK is all it takes.

**Android 17** (API 37) is the default: Google's stable `android-37.0` image (arm64 or x86_64) and emulator 37.2.13, pinned in
`scripts/runtime-lock-17.json` (`-x86_64` for Intel). Root uses Magisk v31.0, the first release with Zygisk for API 37; Vector and microG
are the same pinned builds as on 16. The microG signature module hooks `ComputerEngine`, whose methods are unchanged
in Android 17 (checked against `android-17.0.0_r1`).

### From source (optional, contributors)

Everyday installs use the DMG above. A source zip is also on the site if you want to inspect or customize the project;
see [`BUILD.md`](BUILD.md) for contributor flags. Examples:

```bash
./build.sh                # Android 17: AOSP + Magisk root + microG + pre-installed apps
./build.sh --android 16   # Android 16 instead
./build.sh --pure         # AOSP only: no Magisk, no microG, no GPL-3.0 parts
./build.sh --mirror cn    # mainland China: GitHub via proxy, Android SDK via Tencent mirror
```

## Signing and downloads

Release builds are ad-hoc signed (free, no Apple Developer ID), including the installer and the DMG. Gatekeeper
says it cannot verify the developer. It does not say the file is damaged. Control-click `Install aeroandroid.command`
(and, if macOS still blocks the installed app, `~/Applications/Android Subsystem.app`) and choose **Open**.
On macOS 15 use **System Settings → Privacy & Security → Open Anyway**. If it still blocks the installed app:

```bash
xattr -dr com.apple.quarantine "$HOME/Applications/Android Subsystem.app"
```

Mac apps the subsystem creates for your Android apps are made and signed on your own Mac, so they open without that prompt.

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

## Intel Macs

An Intel Mac gets everything above. `build.sh` detects the chip (also in a Rosetta shell on Apple Silicon) and installs
the x86_64 emulator, system image, JDK, scrcpy and Python, each pinned by SHA-256 in `scripts/runtime-lock-x86_64.json`
and `runtime-lock-17-x86_64.json`. The release DMG is a universal binary.

**ARM translation.** Many Android apps, and most games, ship only arm64 code. The stock x86_64 Android image cannot
run them, so the full install adds a translator:

- It is AOSP's own open-source ARM-to-x86 binary translator (`libndk_translation`, "berberis", Apache-2.0).
- Google's "Google APIs" x86_64 image contains it, so `build.sh` downloads that image (about 2 GB, once) and
  `scripts/arm_translation.py` copies out only the translator and the system properties that turn it on. None of
  Google's apps or services are installed; the image is then discarded.
- It is installed as a Magisk module, so it needs the full edition (root). After a cold boot,
  `scripts/provision-arm-translation.py` runs a real arm64 program through it and refuses to report success otherwise.
- Skip it with `./build.sh --no-arm-translation` (saves the 2 GB download and 8 GB of disk). With `--pure` or
  `--no-arm-translation`, arm64-only apps are refused with a plain explanation.
- Apps translated this way are slower than native ones. Apps with x86_64 code, and the pre-installed Fennec
  (an x86_64 build is chosen automatically), run natively.

**Not run end to end on a Mac.** I checked the pieces against Google's real Android 16 and 17 images and booted
the result in an emulator: the translator files and the 14 properties were identical to Google's image, root and
the module installed, and Android listed `arm64-v8a`. The emulator available to me has no hardware acceleration, so an
arm64 program crashed inside the translator there, exactly as on Google's own image; only a Mac can show it running.
On an Intel Mac, the first run prints a notice, and Settings → Check runtime environment lists the CPU types.

## Restricted networks (for example mainland China)

Google's download servers are slow or unreachable in some countries, which would make the install fail. Pass
`--mirror cn`, or let `build.sh` choose: when `dl.google.com` or GitHub does not answer within a few seconds, it picks
mirrors itself.

| Source | Where it goes instead |
|--------|-----------------------|
| Android SDK, emulator, system images (including the translator image) | `mirrors.cloud.tencent.com/AndroidSDK` (`SDK_MIRROR`) |
| GitHub releases (Magisk, Vector, microG, JDK, scrcpy, Python) | a GitHub proxy (`GH_MIRROR`) |
| Pre-installed apps (F-Droid) | Tsinghua and NJU F-Droid mirrors (`FDROID_MIRROR`) |

A mirror only changes where the bytes come from: every file is checked against its pinned SHA-256, and the official
address is tried as a fallback, so a bad mirror cannot slip in a different file. Set the three variables to point
anywhere else in the world. Mirrors that serve identical files were checked for the Android SDK and F-Droid.

## Gaming

- **Controllers.** Plug in or pair an Xbox, PlayStation, Switch Pro or MFi controller. The window you are playing in
  sends it to Android as a gamepad: buttons as gamepad keys, sticks, triggers and the D-pad as joystick axes.
  Settings → Game controller lets you remap each button or switch controller input off. Games that read the input
  event see a gamepad; a game that lists connected input devices at startup may not, because Android here has no
  real controller hardware.
- **Graphics.** Android runs on the Apple Silicon hypervisor and renders with the Mac's GPU: "Automatic" already picks it,
  and Settings → Graphics acceleration can force it. Up to 60 FPS can be selected.
- **Limits.** Frames still reach the Mac as raw pixels over a local connection, which is the ceiling for fast games, so
  60 FPS is a cap and not a promise. Hardware video encoding would lift it but is not built yet.

## Pre-installed apps

microG (Services, Companion, GSFProxy) is provisioned by `scripts/provision-microg.py`. Aurora Store and Fennec
come from `scripts/preinstall.json`, pinned by APK and signing-certificate SHA-256; nothing unpinned is installed.
Add more with `python3 scripts/preinstall-apps.py --pin <https APK url>` and paste the printed entry.

microG is an open-source compatibility layer, not Google Play services: a successful install does not guarantee
that every Google API, Play Integrity or banking app works. See [docs/MICROG.md](docs/MICROG.md).

## Known limits

- macOS 14+ on Apple Silicon or Intel. Android 17 (default) or 16, AOSP. Android 17 root and microG, and Intel ARM translation, are new and untested on a Mac.
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

Apache-2.0, Copyright 2026 daniel.ye. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE) for third-party components,
and [`docs/LICENSING.md`](docs/LICENSING.md) for what you must do if you redistribute a build that contains them
(the Android SDK components and the GPL parts are downloaded onto your Mac, not shipped by this project).
