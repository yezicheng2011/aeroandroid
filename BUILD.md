# aeroandroid contributor build

> Everyday installs use the official macOS package at [aeroandroid.com](https://aeroandroid.com/#download). This page is for contributors who want to customize the project.


### Requirements
- Apple Silicon or Intel Mac (2018 or newer), macOS 14 or later
- Xcode Command Line Tools: `xcode-select --install`
- `curl`, `unzip`, `tar`, `python3` (shipped with macOS)
- At least 20 GB free disk; about 1.8 GB of downloads

`build.sh` downloads JDK 17, the Android SDK pieces (platform, build-tools, cmdline-tools, platform-tools, emulator, system image for your chip: arm64 or x86_64), Python 3.12 and scrcpy at the versions pinned in `scripts/runtime-lock.json`, checking each SHA-256. No Homebrew or Android Studio needed.

### One command
```bash
./build.sh                 # default: Android 17, AOSP only
./build.sh --pure          # explicitly select the AOSP-only default
./build.sh --with-gpl      # opt in to Magisk, microG, Aurora Store and Fennec (includes GPL components)
./build.sh --mirror cn     # mainland China: GitHub via proxy, Android SDK via Tencent mirror
./build.sh --no-arm-translation   # Intel Macs: skip ARM translation (saves a 2 GB download and 8 GB of disk)
./build.sh --check         # prerequisites only
./build.sh --download-only # only fill ./runtime-cache
```
Environment: `GH_MIRROR` (default `https://gh-proxy.com/`), `SDK_MIRROR` (default `https://mirrors.cloud.tencent.com/AndroidSDK/`), `ANDROID_SUBSYSTEM_CACHE`. Mirrors only change where bytes come from; every file is still checked against its pinned SHA-256, and the official URL is used as a fallback.

Flow: check prerequisites (including the Xcode Command Line Tools) → download runtime → unpack a private JDK and build-tools → compile guest APKs (MacBridge, GraphicsProbe, and, in the full edition, the microG parts) → run `Install.command`, which builds the Mac app and installs it to `~/Applications/Android Subsystem.app`, then opens that copy. Run `Graphics-Acceptance.command` after that.

`./build.sh` with no `--mirror` reads the public country code (`scripts/mirror.py`). Mainland China uses the China mirrors described in the README. Any other result, including a failed lookup, uses the official source.

### macOS package

On a Mac, after the app has been built:

```bash
AEROANDROID_UNIVERSAL=1 ./scripts/build-mac.sh   # release: one binary for Apple Silicon and Intel
./scripts/package-pkg.sh                         # writes out/aeroandroid-<version>-macOS-universal.pkg
```

`package-pkg.sh` ad-hoc signs the app with `codesign --sign -` and builds a `.pkg` that installs it to `/Applications`. It ad-hoc signs the package the same way when `codesign` accepts a flat package. It does not notarize the package. Opening the package is expected to show Gatekeeper's unidentified-developer / unsafe warning; allow it in System Settings → Privacy & Security.

The packaged app contains `scripts/install-runtime.py`. The first launch runs that script and shows a progress bar while Android components download.

### Licenses and optional extensions
This repository remains Apache-2.0. The default build does not download or install optional Magisk,
Vector, microG signature modules, Aurora Store or Fennec. `--pure` explicitly selects that same default.
`--with-gpl` opts into the full edition, including its GPL-licensed components and upstream notices.
Reinstalling an existing full edition as AOSP disables the Magisk boot override but preserves installed APKs
and userdata. It does not automatically uninstall existing GPL applications.
The required external Android runtime includes the GPL Linux kernel, and Temurin OpenJDK is GPL-2.0
with the Classpath Exception. Neither edition is a completely GPL-free runtime. See [docs/LICENSING.md](docs/LICENSING.md).

### Memory
New installs use an automatic memory budget at each boot (2–8 GB by default), with headroom reserved for macOS.
Existing explicit budgets stay in Manual mode. Settings exposes both modes and the automatic bounds.
Changing the selected budget invalidates Quick Boot snapshots, so that boot is cold; userdata is retained.
A running VM does not resize. See [docs/MEMORY.md](docs/MEMORY.md).

### Troubleshooting
- **"Requires a Mac"**: only macOS is supported, on Apple Silicon or Intel; not Linux or Windows.
- **Missing Command Line Tools**: `xcode-select --install`, then reopen Terminal.
- **Restricted networks (for example mainland China)**: see "Restricted networks" in the README; `SDK_MIRROR`, `GH_MIRROR` and `FDROID_MIRROR` point the three kinds of download anywhere.
- **Slow or failing downloads**: use `--mirror cn` or set `GH_MIRROR=https://ghfast.top/`. Re-running resumes; verified files are skipped.
- **SHA-256 mismatch**: the mirror served a bad file; the script retries from the official URL. If it still fails, delete that file from `runtime-cache` and re-run.
- **SDK license**: the installer shows the Android SDK license for you to accept.
- **Disk space**: 20 GB minimum; the full edition needs more for guest data.
- **Logs**: `~/Library/Application Support/AndroidSubsystem/logs/`; diagnostics via `scripts/collect-diagnostics.py`.
- **Normal install**: download the official macOS package at https://aeroandroid.com/#download. Open the `.pkg`. When macOS says it is unsafe or from an unidentified developer, allow it in System Settings → Privacy & Security. The app then downloads Android and shows a progress bar. `xcode-select --install` is still required.
