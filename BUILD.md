# aeroandroid Self-build


### Requirements
- Apple Silicon or Intel Mac (2018 or newer), macOS 14 or later
- Xcode Command Line Tools: `xcode-select --install`
- `curl`, `unzip`, `tar`, `python3` (shipped with macOS)
- At least 20 GB free disk; about 1.8 GB of downloads

`build.sh` downloads JDK 17, the Android SDK pieces (platform, build-tools, cmdline-tools, platform-tools, emulator, system image for your chip: arm64 or x86_64), Python 3.12 and scrcpy at the versions pinned in `scripts/runtime-lock.json`, checking each SHA-256. No Homebrew or Android Studio needed.

### One command
```bash
./build.sh                 # default: full edition (AOSP + Magisk + microG), auto-pick mirror
./build.sh --pure          # AOSP only: no Magisk, no microG, no GPL-3.0 parts
./build.sh --with-gpl      # alias of the default full edition
./build.sh --mirror cn     # mainland China: GitHub via proxy, Android SDK via Tencent mirror
./build.sh --android 16    # Android 16 instead of the default Android 17 (API 37)
./build.sh --no-arm-translation   # Intel Macs: skip ARM translation (saves a 2 GB download and 8 GB of disk)
./build.sh --check         # prerequisites only
./build.sh --download-only # only fill ./runtime-cache
```
Environment: `GH_MIRROR` (default `https://gh-proxy.com/`), `SDK_MIRROR` (default `https://mirrors.cloud.tencent.com/AndroidSDK/`), `ANDROID_SUBSYSTEM_CACHE`. Mirrors only change where bytes come from; every file is still checked against its pinned SHA-256, and the official URL is used as a fallback.

Flow: check prerequisites → download runtime → unpack a private JDK and build-tools → compile guest APKs (MacBridge, GraphicsProbe, and, in the default full edition, the microG parts) → run `Install.command`, which builds the Mac app and installs. Then open `dist/Android Subsystem.app` and run `Graphics-Acceptance.command`.

### GPL components
This repository is Apache-2.0. The microG signature module (`microg-spoof/`, derived from FakeGApps) and Magisk's `host_patch.sh` are GPL-3.0 and are not included in git. The default `./build.sh` (the full edition) downloads them from upstream, checks SHA-256, and prints a license notice. `--with-gpl` is an alias of that default. They remain GPL-3.0 and must not be redistributed as Apache-2.0. `./build.sh --pure` skips them and installs AOSP without Magisk or microG.

### Troubleshooting
- **"Requires a Mac"**: only macOS is supported, on Apple Silicon or Intel; not Linux or Windows.
- **Missing Command Line Tools**: `xcode-select --install`, then reopen Terminal.
- **Restricted networks (for example mainland China)**: see "Restricted networks" in the README; `SDK_MIRROR`, `GH_MIRROR` and `FDROID_MIRROR` point the three kinds of download anywhere.
- **Slow or failing downloads**: use `--mirror cn` or set `GH_MIRROR=https://ghfast.top/`. Re-running resumes; verified files are skipped.
- **SHA-256 mismatch**: the mirror served a bad file; the script retries from the official URL. If it still fails, delete that file from `runtime-cache` and re-run.
- **SDK license**: the installer shows the Android SDK license for you to accept.
- **Disk space**: 20 GB minimum; the full edition needs more for guest data.
- **Logs**: `~/Library/Application Support/AndroidSubsystem/logs/`; diagnostics via `scripts/collect-diagnostics.py`.
- **Don't want to build**: download the official macOS DMG from the latest GitHub release or https://aeroandroid.com/releases.html and run the installer. You do not package the app yourself. The DMG does not contain the Android SDK; the installer downloads that runtime on your Mac.
