<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="assets/logo-light.svg">
    <img src="assets/logo.svg" width="128" alt="aeroandroid logo">
  </picture>
</p>

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
3. **Automatic memory budgeting.** New installs choose a memory budget for each Android start using your Mac's
   memory and available headroom. Set a minimum and maximum, or choose a manual budget in Settings.
4. **Shared Mac folders.** Choose a folder once and open or save its files directly from Android's system file picker.
   Android and Finder use the same files, with read-only or read/write access.
5. **SIP phone and messages.** Use your own SIP account for voice and text, with no cellular-modem fallback.
   Carrier SMS requires a gateway from your provider.
6. **Android desktop widgets.** Add an app's actual Android widgets to the Mac desktop, with live updates,
   buttons and scrolling. Android handles their original interaction.
7. **Your Mac's camera works.** Android camera apps use the Mac's physical camera.

Under the hood it is the official Android Emulator running the AOSP Android image for your Mac's chip, with a native Metal
window per app, plus an Android-side bridge for input, clipboard and notifications.

## Install

**Download the official macOS installer** from [aeroandroid.com](https://aeroandroid.com/#download)
(`aeroandroid-1.1.0-macOS-universal.dmg`). You do not package a release yourself: the installer downloads the runtime and builds the Mac app on your machine.

Requires a Mac (Apple Silicon, or an Intel Mac from 2018 on), macOS 14+, the Xcode Command Line Tools
(`xcode-select --install`), about 20 GB of free disk and an internet connection. The DMG is about 1.3 MB;
the Android runtime (about 1.8 GB) is fetched during installation from official sources, because the Android
SDK license does not allow redistribution.

A fresh default install is **Android 17, AOSP only**: no Magisk, microG, Aurora Store or other pre-installed apps.
`./build.sh --pure` selects the same edition explicitly. Optional GPL extensions require `--with-gpl`;
see [Licensing](#license) before enabling them. The external Android runtime and JDK have their own licenses.
Reinstalling an existing full edition disables its Magisk boot override but keeps installed third-party APKs
and their data; remove unwanted apps explicitly.

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
cold booting (the snapshot takes disk space roughly equal to the selected memory budget).
A memory-budget change discards the old snapshot and requires a cold boot; app data is retained. Open the installed Android
Subsystem once: that makes the APK installer the default app for `.apk` files. From then on, double-clicking
any APK is all it takes.

**Android 17** (API 37) is the only Android version: Google's stable `android-37.0` image (arm64 or x86_64) and emulator 37.2.13,
pinned in `scripts/runtime-lock.json` (`runtime-lock-x86_64.json` for Intel). Optional root and microG
provisioning is described in [docs/ROOT.md](docs/ROOT.md).

**Coming from Android 16?** Android 16 has been removed. Run the installer once: it installs Android 17, carries your
settings over and (in the full install) deletes the Android 16 system image to free disk space. Your Android 16 apps and data are not copied into
Android 17; they stay as a backup in `~/Library/Application Support/AndroidSubsystem/avd/` (the `MacAndroid_16_*` folders).
Delete them when you no longer need them.

### From source (optional, contributors)

Everyday installs use the DMG above. A source zip is also on the site if you want to inspect or customize the project;
see [`BUILD.md`](BUILD.md) for contributor flags. Examples:

```bash
./build.sh                # default: Android 17, AOSP only
./build.sh --pure         # explicitly select the same AOSP-only edition
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
| `assets/` | Logo in a light and a dark look (`logo.svg` switches by itself with the viewer's theme; `logo-light.svg`, `logo-dark.svg`, `logo-1024.png`) and `AppIcon.icns` |

## Intel Macs

An Intel Mac gets everything above. `build.sh` detects the chip (also in a Rosetta shell on Apple Silicon) and installs
the x86_64 emulator, system image, JDK, scrcpy and Python, each pinned by SHA-256 in `scripts/runtime-lock-x86_64.json`.
The release DMG is a universal binary.

**ARM translation.** Many Android apps, and most games, ship only arm64 code. The stock x86_64 Android image cannot
run them. The default AOSP install supports apps with x86 or x86_64 code.
The optional full edition (`--with-gpl`) adds a translator:

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

**Not run end to end on a Mac.** I checked the pieces against Google's real Android 17 image and booted
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

The default installation does not pre-install third-party apps. In the optional full edition (`--with-gpl`),
microG (Services, Companion, GSFProxy) is provisioned by `scripts/provision-microg.py`. Aurora Store and Fennec
come from `scripts/preinstall.json`, pinned by APK and signing-certificate SHA-256; nothing unpinned is installed.
Add more with `python3 scripts/preinstall-apps.py --pin <https APK url>` and paste the printed entry.

microG is an open-source compatibility layer, not Google Play services: a successful install does not guarantee
that every Google API, Play Integrity or banking app works. See [docs/MICROG.md](docs/MICROG.md).

## Desktop widgets

Start Android, open **Widgets** in the Mac manager, choose an installed widget and select **Add to desktop**.
Complete Android's normal permission/configuration screens. Each widget then runs in its own desktop window;
drag the title bar to move it, resize the window, and click or scroll its original Android controls.
Positions, sizes and widget IDs are saved. Closing the manager window leaves the widgets running; quitting the
manager or stopping Android suspends them until you reopen the manager and start Android.

The host uses real Android AppWidget views. A button that opens an app temporarily raises that surface;
**Back** returns through the app's Android navigation before the window settles onto the desktop again.
Only apps that provide home-screen widgets appear. These are aeroandroid desktop windows, not Apple's WidgetKit
gallery, and provider-specific compatibility still needs testing. See [docs/WIDGETS.md](docs/WIDGETS.md).

## Phone and messages over SIP

The bridge includes **SIP Phone**, **SIP Messages** and local account settings. Open **Mac Bridge → SIP account**,
enter your provider's details, and connect. The client uses TCP or verified TLS signaling and G.711 RTP audio;
account passwords are encrypted with Android Keystore. The bridge install selects the SIP client for the Android
Phone and SMS roles where available; Phone and Messages also include default-app selection buttons.

Messages use **SIP MESSAGE**. A provider SMS gateway is needed to reach ordinary mobile numbers; voice service
alone does not imply SMS support. No third-party SIP dependency is added. Current scope is one call, text messages
and a compatible provider: no MMS, video, ICE, SRTP or emergency calling. TLS protects signaling, not RTP media.
Real provider and Mac audio acceptance is still required. See [docs/SIP.md](docs/SIP.md) for setup and limits.

## Shared storage

Open **Files → Shared Mac folders**, add the folders you want to use, then choose **Connect to Android**.
In an Android app's Open or Save dialog, choose **Mac · <folder name>**. Reads, edits and new files go directly
to that Mac folder, without manual import/export or a synchronized copy. Finder opens the same files.
Sharing restores automatically when Android starts. Each folder can be read-only or read/write; **Stop sharing**
revokes access and leaves the files intact.

Apps must support Android's system document picker. This does not mount Android's private app data in Finder or
make Mac folders appear at raw `/sdcard` paths. Refresh/reopen the Android picker to see external Finder changes.
The existing import/export folder remains available for older apps. See [docs/STORAGE.md](docs/STORAGE.md).

## Memory management

New installations use **Automatic** memory mode with a 2 GB minimum and an 8 GB maximum. At each start,
aeroandroid chooses a budget within those bounds using the Mac's physical memory and available memory,
reserving headroom for macOS and other apps before applying your configured minimum. That minimum wins under
pressure, so an unusually high floor can still cause swapping. If host measurements are unavailable, it uses the minimum.
Settings shows the current allocation and next-start estimate; the estimate can change as other Mac apps use memory.

In **Settings → Runtime**, choose Automatic and adjust its bounds, or select Manual for a fixed budget.
Stop Android before saving runtime settings. Existing installs with an explicit memory setting keep that value
in Manual mode; select Automatic to opt in. Switching modes keeps the saved manual budget.

This is adaptive allocation **at startup**, not live VM memory resizing or ballooning. The Android Emulator's
RAM size stays fixed until it stops. If the selected size changes, aeroandroid updates the AVD and removes its
incompatible Quick Boot snapshots; it preserves Android apps and user data. Stop the subsystem from the menu
bar to release its memory. Closing an app window alone keeps Android and background services running.
See [docs/MEMORY.md](docs/MEMORY.md) for configuration and validation details.

## Known limits

- macOS 14+ on Apple Silicon or Intel. Android 17, AOSP. Optional root, microG and Intel ARM translation still need Mac hardware acceptance.
- Memory is recalculated when Android starts; a running VM does not resize as workload changes.
- Camera: the Mac camera is passed to the emulator as `webcam0` for both the front and back camera.
  macOS asks for camera permission the first time.
- Several `.apk` files opened together are installed as one split-APK set.
- No Google Play Store, Chrome or proprietary DroidGuard is bundled.

## Optional components

`./build.sh --with-gpl` explicitly enables the existing full edition: Magisk root, microG, Aurora Store,
Fennec and, on Intel, ARM translation. It downloads GPL-licensed components that retain their upstream terms.
These extensions are skipped by default, including their archives in a fresh download cache.
The `microg-spoof/` module and Magisk's `host_patch.sh` are fetched from upstream and are not tracked here.

## License

Original aeroandroid code remains **Apache-2.0, Copyright 2026 daniel.ye**. See [`LICENSE`](LICENSE),
[`NOTICE`](NOTICE) and [`docs/LICENSING.md`](docs/LICENSING.md). No new third-party dependency is needed for
automatic memory management.

AOSP-only means no optional root or GPL app extensions; it does **not** mean a GPL-free runtime.
Android includes the GPL Linux kernel, and the existing Temurin JDK is GPL-2.0 with the Classpath Exception.
These are separate upstream components downloaded onto your Mac, not relicensed as Apache-2.0.
The lightweight DMG does not bundle the downloaded Android runtime.
