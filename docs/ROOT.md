# Android 16 · Magisk Root and microG Setup

By default this uses pure AOSP Android 16 ARM64, Magisk v30.7 and open-source microG. All dependencies are pinned in `runtime-lock.json`; this version installs no GApps or proprietary Google system components. See the [microG notes](MICROG.md) for microG capabilities, self-check and commercial distribution caveats.

## Magisk implementation

1. Boot this project's pure AOSP AVD and confirm API 36 / ARM64 and AVD ownership.
2. Inside the Guest, patch the ramdisk with Magisk v30.7's official `host_patch.sh`; the script and its license are kept in `third_party/Magisk`.
3. Save a private `images/16/default/ramdisk.magisk.img`, record the SHA256 of the original, the patched image and the Magisk APK, and bind it to `image_tag=default`. The original SDK ramdisk is not rewritten, and the patched ramdisk from the old Google image is never reused.
4. Cold-boot with that ramdisk and the parameters used by Magisk's official AVD test specified explicitly.
5. Verify Magisk, su and the manager app, then restore ADB as the shell UID so the graphics service keeps its permission ownership.
6. In the microG stage, enable Zygisk, install the official Vector and our own system module, check the enabled state, scope and Android's actual signature queries, then restore the ADB shell.

What was completed on the server is install orchestration, host-side APK build / signature verification and controlled flow tests; no new ARM64 AOSP Guest was booted. The real patching, authorization, mounting and cold-boot results on the M5 are checked by the install script and need user acceptance.

## Running standalone

From the source directory, run the full root setup and then the microG setup:

```bash
"$HOME/Library/Application Support/AndroidSubsystem/runtime/python/bin/python3" scripts/provision-mac.py /your/runtime-cache
"$HOME/Library/Application Support/AndroidSubsystem/runtime/python/bin/python3" scripts/provision-microg.py /your/runtime-cache
```

Re-check:

```bash
"$HOME/Library/Application Support/AndroidSubsystem/runtime/python/bin/python3" scripts/provision-mac.py --verify-only
"$HOME/Library/Application Support/AndroidSubsystem/runtime/python/bin/python3" scripts/provision-microg.py --verify-only
```

Remove the private Magisk ramdisk boot override:

```bash
"$HOME/Library/Application Support/AndroidSubsystem/runtime/python/bin/python3" scripts/provision-mac.py --rollback-root
```

Rollback stops the subsystem and removes the boot override; it does not delete the AVD userdata or the SDK image. It disables the microG signature-compatibility path that depends on Magisk / Zygisk, and does not claim to have removed all app updates or restored all userdata.

## M5 acceptance

- After fully stopping / starting twice, Magisk still shows as installed.
- su requests from ordinary Android apps are authorized through Magisk, rather than only proving that adb root works.
- The automated microG signature check and the UI Self-Check pass before testing the apps you need.
- After root and microG setup, multi-window graphics, IME, focus and notifications still work.

Android 17 will need a new ARM64 image and separate root / microG acceptance; the current pinned configuration is for Android 16 only.

Sources: [Magisk v30.7 host_patch.sh](https://github.com/topjohnwu/Magisk/blob/v30.7/scripts/host_patch.sh), [official AVD test script](https://github.com/topjohnwu/Magisk/blob/v30.7/scripts/avd.sh).
