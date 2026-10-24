# Android Subsystem for Mac · Development Acceptance Build 0.2.0

Goal: provide a WSA-like desktop experience for Android apps on M5 / Apple Silicon Macs. The default runtime configuration is pure AOSP Android 16 (API 36) ARM64 + persistent Magisk root + open-source microG. The new image, root and microG need to be accepted on the M5. Android 17 (API 37) is enabled only when the corresponding ARM64 system image is available, and the system never silently downgrades to Android 15 or earlier.

This version switches to the `default` pure AOSP image and does not include or install GApps, the Google Play Store, Google Play services or Google Chrome. microG Services and Companion use compatible package names, but they are open-source implementations; Companion is not a Google Play Store where you can browse and download apps. No Google account is signed in automatically, device registration and push messaging are not enabled automatically, and Google's proprietary DroidGuard is not included. Commercial distribution still requires separately handling the official SDK terms, GPL / LGPL corresponding source and license notices; using AOSP and microG does not automatically clear licensing for the whole distribution.

**This is currently an engineering prototype that needs real testing on an M5, not a finished product equivalent to WSA.** The current server is Linux x86_64 and cannot perform the macOS SwiftUI / Metal build or real graphics acceptance.

## Current main path

```text
ARM64 Android VM (official Android Emulator / HVF, existing graphics runtime)
  └─ In-house SurfaceServer (shell UID, app_process)
       ├─ App A → VirtualDisplay A → ImageReader / Surface A
       ├─ App B → VirtualDisplay B → ImageReader / Surface B
       └─ Authenticated TCP protocol over a local ADB forward
            ├─ RGBA8 raw frames → macOS IOSurface / CVPixelBufferPool → Metal → native NSWindow
            └─ Mouse / scroll wheel / keys / input method / focus / visibility / resize / close
```

Opening an app from the main UI goes through `native-session`; scrcpy is never used to create app windows. scrcpy is kept only as a development comparison tool and as a fallback for the app list when the companion is missing.

Each window has its own Guest VirtualDisplay; a single Android desktop image is never cropped into multiple windows. Closing the connection releases the display; minimizing removes that display's Surface, and restoring reattaches it. Destroying, pausing and resuming Android Activities is still managed by Android, and per-app behaviour needs verification.

**Pixels are currently copied across the VM boundary. IOSurface is used only for CPU / Metal shared buffers inside the Mac; cross-VM shared memory, virtio-gpu blob export and zero-copy are not implemented yet.** Components such as gfxstream inside the existing emulator are not a GPU virtualization backend implemented by this project. Raw frames are capped at 30 FPS by default, with resolution and buffer limits; no performance commitments are made yet.

## Installation and migrating an existing version

The delivery package contains the source code and `runtime-cache`. After unzipping, double-click `AndroidSubsystem/Build.command`: it automatically prepares the pure AOSP runtime, builds the Mac app, patches the private Magisk ramdisk, installs microG, and runs module configuration and signature-compatibility checks. `Install.command` and `Migrate-to-AOSP.command` also perform the full install; the migration entry point is for existing Google-image versions.

```text
M5-Android16-0.2.0-AOSP-microG/
  AndroidSubsystem/
    Build.command
    Install.command
    Migrate-to-AOSP.command
    artifacts/                  # bridge APK, GSFProxy, package-scoped signature-compatibility module
  runtime-cache/
    android16-macos/             # official SDK archives, pure AOSP ARM64 image, repository metadata
    mac-tools/                  # pinned ARM64 Python, Java, scrcpy
    provision/                  # Magisk, official microG APKs, official Vector module
```

1. The Mac needs macOS 14 or later, at least 20 GB of free space, and the Xcode Command Line Tools. If the developer tools are missing, run `xcode-select --install` first; this package does not include the Apple SDK.
2. For a first install, double-click `Build.command`; for an existing version, double-click `Migrate-to-AOSP.command`. The script verifies dependencies and shows the Android SDK terms you need to accept; no preinstalled Python, Java or Homebrew is required.
3. When upgrading, it first quits the manager app and calls the installed old backend to stop the old VM, and only changes the configuration after confirming a full exit. If the existing private Python is missing, the script stops before changing anything. Existing memory, CPU and other settings are kept.
4. Pure AOSP uses a separate `MacAndroid_16_AOSP_arm64` AVD and does not directly reuse the old Google system's userdata. Old userdata is kept as an offline backup, and the old private Google image is removed only after the new runtime has been fully configured. Old Android apps need to be reinstalled; in-app data is not migrated automatically.
5. The build is installed to `~/Applications/Android Subsystem.app`. Run the [microG self-check](docs/MICROG.md), then follow the [acceptance checklist](docs/ACCEPTANCE.md) to check display, input, cold boot and the apps you need.

Full logs are saved to `~/Library/Application Support/AndroidSubsystem/logs/install-<date>-<time>-<pid>.log`; on success or failure, Terminal shows the log location and waits for Enter. The SDK, Python, Java and runtime data live in the same private runtime directory, and logs are never uploaded automatically.

`Graphics-Install.command` only prepares the pure AOSP graphics environment, skipping root and microG. It is for troubleshooting graphics on its own; you can run `Build.command` afterwards to complete the full setup. `Graphics-Acceptance.command` automatically captures real frames from two different apps, saves PNGs, checks displays and close isolation, and opens native windows for manual observation; the existence of these files does not mean Metal or all apps have passed acceptance.

The cache can sit next to the source code or inside `AndroidSubsystem/runtime-cache`; the built-in directory takes precedence. If it is somewhere else:

```bash
ANDROID_SUBSYSTEM_CACHE='/your/runtime-cache' ./Build.command
```

Developers can use `scripts/setup-mac.sh 16` to prepare pure AOSP and the native bridge online. This developer entry point downloads tools on the Mac and does not include the full pinned Magisk / microG install; delivery and migration should use the offline `Build.command`.

## Implemented

- Native SwiftUI app library, app icons, search, APK install (including split APKs selected together) and uninstall.
- In-house per-app displays, frame protocol, native Metal windows, and window-size feedback.
- Mouse-to-touch mapping, scroll wheel, navigation keys, Mac input-method text commit, and the Mac Bridge IME.
- Cmd+V text commit, and reading the Android text clipboard after Cmd+C / Cmd+X; actual authorization and focus behaviour pending acceptance.
- Launcher export: saves an `.app` to a chosen folder that opens the corresponding Android app via the main app's URL scheme.
- File import / export using Android's `Download/MacBridge` as the exchange folder, refusing to overwrite existing exported files.
- Android notification listening and forwarding to macOS notifications, requiring authorization on both sides; currently the manager app must stay running.
- Runtime isolation, ownership checks, PID-reuse protection, graphics connection authentication, a concurrent operation queue, and diagnostic reports.
- Persistent Magisk ramdisk configuration, orchestration of the official patch script, cold-boot root / manager checks, and binding of the ramdisk hash to the image tag.
- Pure AOSP migration, pinned microG APK install, a privapp allowlist generated from the actual manifest and AOSP permission definitions, and read-back verification of Zygisk / Vector module enablement and the restricted `system/0` scope.
- Signature compatibility restricted to Services / Companion with the real microG signature; checks both PackageInfo queries, certificate queries and rejection of wrong certificates, without opening signature spoofing to arbitrary APKs.

## Not yet done

- Cross-VM shared memory / shared GPU buffers, and a complete in-house virtio-gpu / gfxstream-style backend.
- Audio bridging for the native graphics path.
- A separate Dock process identity and icon per app window; currently what's exported is a launcher, and windows belong to the manager app process.
- Deep integration of microphone, camera, location, notification actions, file pickers and Finder.
- A system-level persistent bridge and power-saving strategy, and a signed / notarized installer that needs no developer tools.
- Full runtime, app adaptation, self-check and cold-boot verification of the new pure AOSP image and microG on the M5; DRM, anti-cheat and compatibility with all third-party apps. microG does not guarantee that Play Integrity, banking apps or every Google API will work.
- An installable Android 17 ARM64 image and real runtime verification.

"Builds from source" and "protocol tests pass" must not be taken to mean the items above are done.

## Validation

```bash
python3 -m unittest discover -s tests -v
```

These tests simulate the runtime with controlled external processes and cover lifecycle, the dual-window comparison path, APK / file operations, version checks, ownership isolation, in-house service reuse and authentication, and archive path checks. **They do not replace real Android / Metal testing.**

The Guest APK is compiled, signed and verified with the real Android 16 SDK and Java. A real frame sequence output by Java goes through protocol-interop testing with the Swift decoder. The Mac UI source passes Swift syntax parsing; full SDK type checking, linking and display must be done on a Mac.

See the [runtime configuration notes](docs/ROOT.md) for Magisk root, and the [microG notes](docs/MICROG.md) for microG's scope, automated verification and manual self-check.

For more details see the [graphics path notes](docs/GRAPHICS.md), the [acceptance checklist](docs/ACCEPTANCE.md) and the [build validation record](docs/VALIDATION.md).

## References and third-party dependencies

- [Hardware acceleration for the Android Emulator](https://developer.android.com/studio/run/emulator-acceleration)
- [Android 16 SDK](https://developer.android.com/about/versions/16/setup-sdk)
- [Android DisplayManager](https://developer.android.com/reference/android/hardware/display/DisplayManager)
- [Apple IOSurface](https://developer.apple.com/documentation/iosurface)
- [scrcpy official repository](https://github.com/Genymobile/scrcpy) (development comparison tool, Apache 2.0)
- [Eclipse Temurin](https://adoptium.net/) and [Python Build Standalone](https://github.com/astral-sh/python-build-standalone)
- [microG Services / Companion](https://github.com/microg/GmsCore), [GSFProxy](https://github.com/microg/GSFProxy)
- [Vector](https://github.com/JingMatrix/Vector), with our own scope-restricted compatibility module configured via the official CLI

The cloud-drive archive is the user's own private dependency cache; each third-party component is used under its own license.
