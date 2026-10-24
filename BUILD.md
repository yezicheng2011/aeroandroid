# aeroandroid Self-build


### Requirements
- Apple Silicon Mac (M1–M5), macOS 14 or later
- Xcode Command Line Tools: `xcode-select --install`
- `curl`, `unzip`, `tar`, `python3` (shipped with macOS)
- At least 20 GB free disk; about 1.8 GB of downloads

`build.sh` downloads JDK 17, the Android SDK pieces (platform, build-tools, cmdline-tools, platform-tools, emulator, arm64 system image), Python 3.12 and scrcpy at the versions pinned in `scripts/runtime-lock.json`, checking each SHA-256. No Homebrew or Android Studio needed.

### One command
```bash
./build.sh                 # auto-pick mirror, build and install the pure-AOSP edition
./build.sh --mirror cn     # mainland China: GitHub via proxy, Android SDK via Tencent mirror
./build.sh --with-gpl      # full edition: also fetch GPL-3.0 parts, install Magisk + microG
./build.sh --check         # prerequisites only
./build.sh --download-only # only fill ./runtime-cache
```
Environment: `GH_MIRROR` (default `https://gh-proxy.com/`), `SDK_MIRROR` (default `https://mirrors.cloud.tencent.com/AndroidSDK/`), `ANDROID_SUBSYSTEM_CACHE`. Mirrors only change where bytes come from; every file is still checked against its pinned SHA-256, and the official URL is used as a fallback.

Flow: check prerequisites → download runtime → unpack a private JDK and build-tools → compile guest APKs (MacBridge, GraphicsProbe, plus the microG parts with `--with-gpl`) → run `Install.command`, which builds the Mac app and installs. Then open `dist/Android Subsystem.app` and run `Graphics-Acceptance.command`.

### GPL components
This repository is Apache-2.0. The microG signature module (`microg-spoof/`, derived from FakeGApps) and Magisk's `host_patch.sh` are GPL-3.0 and are not included. Only with `--with-gpl` does `build.sh` download them from upstream (SHA-256 checked) and print a license notice; they remain GPL-3.0 and must not be redistributed as Apache-2.0. Without the flag you get the pure-AOSP graphics edition, without Magisk or microG.

### Troubleshooting
- **"Requires an Apple Silicon Mac"**: only arm64 macOS is supported; not Intel Macs or Linux.
- **Missing Command Line Tools**: `xcode-select --install`, then reopen Terminal.
- **Slow or failing downloads**: use `--mirror cn` or set `GH_MIRROR=https://ghfast.top/`. Re-running resumes; verified files are skipped.
- **SHA-256 mismatch**: the mirror served a bad file; the script retries from the official URL. If it still fails, delete that file from `runtime-cache` and re-run.
- **SDK license**: the installer shows the Android SDK license for you to accept.
- **Disk space**: 20 GB minimum; the full edition needs more for guest data.
- **Logs**: `~/Library/Application Support/AndroidSubsystem/logs/`; diagnostics via `scripts/collect-diagnostics.py`.
- **Don't want to build**: download the full offline package at https://aeroandroid.com/releases.html.
