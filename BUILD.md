# aeroandroid contributor build

> Everyday installs use the official DMG at [aeroandroid.com](https://aeroandroid.com/#download). This page is for contributors who want to customize the project.


### Requirements
- Apple Silicon or Intel Mac (2018 or newer), macOS 14 or later
- Xcode Command Line Tools: `xcode-select --install`
- `curl`, `unzip`, `tar`, `python3` (shipped with macOS)
- At least 20 GB free disk; about 1.8 GB of downloads

`build.sh` downloads JDK 17, the Android SDK pieces (platform, build-tools, cmdline-tools, platform-tools, emulator, system image for your chip: arm64 or x86_64), Python 3.12 and scrcpy at the versions pinned in `scripts/runtime-lock.json`, checking each SHA-256. No Homebrew or Android Studio needed.

### One command
```bash
./build.sh                 # full edition (default): Android 17, AOSP + Magisk + microG + Aurora Store + Fennec
./build.sh --pure          # pure AOSP only: no Magisk, no microG, no pre-installed apps, no GPL-3.0 parts
./build.sh --with-gpl      # alias of the default full edition
./build.sh --mirror cn     # mainland China: GitHub via proxy, Android SDK via Tencent mirror
./build.sh --android 16    # Android 16 instead of the default Android 17 (API 37)
./build.sh --no-arm-translation   # Intel Macs: skip ARM translation (saves a 2 GB download and 8 GB of disk)
./build.sh --check         # prerequisites only
./build.sh --download-only # only fill ./runtime-cache
```
Environment: `GH_MIRROR` (default `https://gh-proxy.com/`), `SDK_MIRROR` (default `https://mirrors.cloud.tencent.com/AndroidSDK/`), `ANDROID_SUBSYSTEM_CACHE`. Mirrors only change where bytes come from; every file is still checked against its pinned SHA-256, and the official URL is used as a fallback.

Flow: check prerequisites (including the Xcode Command Line Tools) → download runtime → unpack a private JDK and build-tools → compile guest APKs (MacBridge, GraphicsProbe, and, in the full edition, the microG parts) → run `Install.command`, which builds the Mac app and installs it to `~/Applications/Android Subsystem.app`, then opens that copy. Run `Graphics-Acceptance.command` after that. The DMG's `Install aeroandroid.command` does the same thing after copying this tree to `~/aeroandroid`.

### GPL components
This repository is Apache-2.0. The microG signature module (`microg-spoof/`, derived from FakeGApps) and Magisk's `host_patch.sh` are GPL-3.0 and are not included. The default full edition has `build.sh` download them from upstream (SHA-256 checked) and print a license notice; they remain GPL-3.0 and must not be redistributed as Apache-2.0. `--with-gpl` is an alias of that default. `./build.sh --pure` is the pure-AOSP graphics edition, without Magisk or microG.

### Troubleshooting
- **"Requires a Mac"**: only macOS is supported, on Apple Silicon or Intel; not Linux or Windows.
- **Missing Command Line Tools**: `xcode-select --install`, then reopen Terminal.
- **Restricted networks (for example mainland China)**: see "Restricted networks" in the README; `SDK_MIRROR`, `GH_MIRROR` and `FDROID_MIRROR` point the three kinds of download anywhere.
- **Slow or failing downloads**: use `--mirror cn` or set `GH_MIRROR=https://ghfast.top/`. Re-running resumes; verified files are skipped.
- **SHA-256 mismatch**: the mirror served a bad file; the script retries from the official URL. If it still fails, delete that file from `runtime-cache` and re-run.
- **SDK license**: the installer shows the Android SDK license for you to accept.
- **Disk space**: 20 GB minimum; the full edition needs more for guest data.
- **Logs**: `~/Library/Application Support/AndroidSubsystem/logs/`; diagnostics via `scripts/collect-diagnostics.py`.
- **Normal install**: download the official macOS DMG at https://aeroandroid.com/#download and run `Install aeroandroid.command`. It still needs `xcode-select --install`; the script downloads the runtime and builds the app.
