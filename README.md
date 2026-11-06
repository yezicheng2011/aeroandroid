<p align="center"><img src="assets/logo.svg" width="128" alt="aeroandroid logo"></p>

<h1 align="center">aeroandroid</h1>
<p align="center"><b>Run Android apps on your Mac as if they were Mac apps.</b><br>
Double-click an <code>.apk</code>. It installs, gets its own icon in Launchpad and the Dock,<br>
and opens in its own window. Works on Apple Silicon and Intel Macs.</p>

---

## What it does

aeroandroid runs a real Android system (Android 17 by default, or 16) in the background on your Mac and shows each
Android app in its own native window, so you never see an emulator, a phone frame or a manager window while you use an app.

**Install apps**
- Double-click any `.apk` file. A small installer puts it into Android and saves a Mac app for it in `~/Applications`.
- Or drag APKs onto the manager window, choose **Install APK…** (⌘I), or use the pre-installed
  [Aurora Store](https://auroraoss.com) and [Fennec](https://f-droid.org/packages/org.mozilla.fennec_fdroid/)
  (Firefox) inside Android.

**Use them like Mac apps**
- Every Android app has its own Dock icon, Launchpad and Spotlight entry, ⌘-Tab, ⌘-H and ⌘-Q, and opens only its own window.
- Resize the window and the app resizes with it. Several apps can run side by side, each in its own window.
- The installer saves a snapshot of the started system, which is meant to make the first app start in seconds instead of minutes.

**Input and devices**
- Mouse and trackpad act as touch: click and drag, scroll wheel to scroll, right-click for **Back** (Esc also goes back).
- Keyboard input, including Chinese, Japanese and other languages typed through macOS input methods.
- Copy and paste text between Mac and Android (⌘C/⌘X in Android puts the text on the Mac clipboard; ⌘V sends yours).
- Your Mac's camera is available to Android camera apps (macOS asks for permission the first time).
- Game controllers: Xbox, PlayStation, Switch Pro and MFi pads work in the window you are playing in, with remappable buttons.
- Graphics are drawn by your Mac's GPU, with a frame rate of up to 60 FPS.

**Moving things between Mac and Android**
- **File exchange** page: import Mac files into Android's `Download/MacBridge` folder and export files back out.
  Android apps see them through their normal file picker.
- **Notifications** from Android apps can appear in macOS Notification Center; click one to open the app.
  Turn this on once in Settings and grant access in Android.

**Manager and menu bar**
- The manager has an **app library** (search, open, close, uninstall, create a Mac app), **file exchange** and **settings**
  (language English/中文, memory, CPU cores, frame rate, graphics, controller buttons, a self-check, logs).
- A menu bar item starts and stops Android and opens your apps.

**Full edition extras** (the default install)
- Root access (Magisk) and microG, an open-source stand-in for Google Play services, so more apps can sign in and
  run when they expect Google's APIs. microG is not Google's software and does not make every app work.

**Intel Macs**
- Many Android apps and games contain only ARM code. On an Intel Mac the full install adds an ARM-to-x86 translator
  so they can run, more slowly than native. Skip it with `--no-arm-translation` if you do not need it.

## Using it

1. Install aeroandroid (below). The first launch of **Android Subsystem** makes it the default app for `.apk` files.
2. Get an `.apk` (for example from F-Droid), or open Aurora Store or Fennec from the library and install apps there.
3. Double-click the `.apk`. When it finishes, the app opens in its own window and is saved in `~/Applications`.
4. Next time, open it from Launchpad, Spotlight or the Dock. Android starts in the background on demand and keeps
   running until you choose **Stop subsystem** in the manager or the menu bar.

## Install

Download the official macOS installer from [aeroandroid.com](https://aeroandroid.com/#download)
(`aeroandroid-1.0.1-macOS-universal.dmg`). You do not need to build anything yourself.

You need a Mac (Apple Silicon, or an Intel Mac from 2018 on), macOS 14 or later, the Xcode Command Line Tools
(`xcode-select --install`), about 20 GB of free disk and an internet connection. The DMG itself is small; Android
(about 1.8 GB, plus about 2 GB more on Intel for ARM translation) is downloaded during installation from official
sources, because Google's Android SDK license does not allow it to be redistributed.

1. Run `xcode-select --install` if you have not already.
2. Open the DMG, Control-click **安装 aeroandroid.command** ("Install aeroandroid"), choose **Open**
   (on macOS 15: **System Settings → Privacy & Security → Open Anyway**).
3. Accept the Android SDK license when asked and wait for setup to finish. It opens `Android Subsystem.app`.

The release is signed ad hoc, free, with no Apple Developer account, so macOS says it cannot verify the developer. Control-click and
**Open**, or run `xattr -dr com.apple.quarantine "/Applications/Android Subsystem.app"`. The Mac apps made for your Android
apps are created and signed on your own Mac, so they open without a prompt.

**Slow or blocked downloads** (for example in mainland China): the installer picks mirrors by itself when Google or GitHub
does not answer, or you can force it with `--mirror cn`. Every download is checked against a pinned SHA-256, so a mirror
cannot swap a file. See [Restricted networks](#restricted-networks).

## What works, and what does not

- **Works well:** most apps that do not depend on Google's own services, including ordinary apps, browsers, readers,
  tools and many games.
- **No sound yet.** Audio from Android apps is not sent to the Mac in the app windows.
- **Google services.** There is no Google Play Store (Aurora Store and F-Droid are included instead). microG covers
  many Google APIs, but apps that need Play Integrity, banking apps, DRM video and games with anti-cheat may refuse to run.
- **Intel Macs:** ARM-only apps need the translator and run more slowly.
- **Camera:** front and back cameras both use your Mac's one camera.
- Android 17 root, microG and the Intel translator are new and have not been verified end to end on a Mac. If the Android 17
  install fails, the installer offers to retry on Android 16.
- Mac only (macOS 14+). Not Windows or Linux.

<a id="restricted-networks"></a>
## Restricted networks

| Download | Where it goes instead |
|----------|-----------------------|
| Android SDK, emulator, system images | `mirrors.cloud.tencent.com/AndroidSDK` (`SDK_MIRROR`) |
| GitHub releases (Magisk, microG, JDK, scrcpy, Python) | a GitHub proxy (`GH_MIRROR`) |
| Pre-installed apps (F-Droid) | Tsinghua and NJU F-Droid mirrors (`FDROID_MIRROR`) |

Set the three variables to point anywhere in the world. A mirror only changes where bytes come from; every file is checked
against its pinned SHA-256 and the official address is the fallback.

## Privacy

Everything runs on your Mac. The app talks to Android over a local connection, notifications and clipboard text stay on your Mac, and no
account is created. Nothing is uploaded; `scripts/collect-diagnostics.py` writes a report only to a file you can read first.
The installer and apps you add can reach the internet like any app.

## For developers

Building from source, how each part works and the test notes are documented separately in
[`BUILD.md`](BUILD.md) and [`docs/`](docs/).
In short, one executable plays three roles chosen by its `Info.plist` (the manager, the hidden APK installer that owns `.apk`
files, and one Mac app per Android app), on top of the official Android Emulator running an AOSP system image, with a
native Metal window per app and a small Android-side bridge for input, clipboard, notifications and app icons.

```bash
./build.sh                # Android 17: AOSP + Magisk root + microG + pre-installed apps
./build.sh --android 16   # Android 16 instead
./build.sh --pure         # AOSP only: no Magisk, no microG, no GPL-3.0 parts
./build.sh --mirror cn    # mainland China mirrors
```

## License

Apache-2.0, Copyright 2026 daniel.ye叶子诚. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE) for third-party components,
and [`docs/LICENSING.md`](docs/LICENSING.md) for what you must do if you redistribute a build that contains them.
Android, the emulator and the GPL parts (Magisk and others) are downloaded onto your Mac, not shipped by this project.
