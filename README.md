# aeroandroid

aeroandroid is an "Android subsystem" that runs Android 16 on Apple Silicon Macs (M-series chips). It is built on the official Android Emulator and the AOSP arm64 system image, and includes:

- a native macOS app (Swift, `macos/`) that shows each Android app as its own Mac window;
- an Android-side bridge app (Java, `guest/`) for frame transport, input method, notifications and clipboard;
- a Python backend controller (`backend/subsystem.py`) plus install, provisioning and diagnostic scripts (`scripts/`, `*.command`);
- microG support (`third_party/GSFProxy`).

## Build and run

**Recommended:** run `./build.sh` (one-command self-build; see [BUILD.md](BUILD.md), supports `--mirror cn`).

Requires an Apple Silicon Mac with macOS 14+, and an internet connection to download about 1.8 GB of runtime (Android Emulator, system image, JDK, etc.).

1. Double-click `Build.command` (or run it in Terminal); it calls `scripts/setup-mac.sh` to download the runtime and build the macOS app and guest APKs.
2. Run `Install.command` to install, then `Graphics-Acceptance.command` to verify graphics.
3. Offline install: download the full `M5-Android16-*.zip` package from https://aeroandroid.com/releases.html; its `runtime-cache/` already contains every runtime component.

See `docs/` for details.

## Not included in this repository

- The `microg-spoof/` signature-compatibility module and Magisk's `host_patch.sh`: both are GPL-3.0 and distributed separately; get them from upstream.
- Prebuilt APKs (`artifacts/`) and the runtime cache (`runtime-cache/`): produced or downloaded by the build scripts.

## License

Apache-2.0, Copyright 2026 daniel.ye. See `NOTICE` for third-party components.
