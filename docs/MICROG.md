# Pure AOSP Android 16 and microG

This version uses the pure AOSP image `system-images;android-36;default;arm64-v8a`. microG Services / Companion are open-source implementations compatible with Google APIs, using the compatible package names `com.google.android.gms` and `com.android.vending`. They are not Google's official Play services or Play Store, and they do not provide the store's app catalogue. GSFProxy forwards the legacy GSF broadcast interface.

GApps, Google Chrome and the proprietary DroidGuard are not included. No account is signed in automatically, and Google device registration and cloud push messaging are not enabled automatically. When network services are needed, the user chooses them explicitly in microG settings; a successful install does not mean Play Integrity, DRM, banking apps, game anti-cheat or every Google API will work.

## Installation and configuration

`Build.command` / `Install.command` perform, in order, the pure AOSP install, the Mac build, Magisk and microG. If you have the earlier Google-image version, run `Migrate-to-AOSP.command`. Before migrating, it quits the old manager app and stops the old VM with the old backend, and only then changes the configuration. Existing memory settings such as 6 GB are kept. The new AVD isolates the old userdata; old apps need to be reinstalled, and old data is kept as an offline backup. The old Google system's package database is never merged into pure AOSP.

Dependency archives and source artifacts are all pinned by SHA256. microG APKs are checked using their actual `aapt2` manifest, version and `apksigner` certificate; already-installed packages with the same name are also checked against their real APK certificate, and mixing with proprietary Google packages is refused.

The `mac_microg_api36` Magisk module installs Services, Companion and GSFProxy into `system/priv-app`. The permissions XML only allows permissions that the APKs actually request and that the running AOSP defines as privileged. Ordinary dangerous permissions are still granted by the Android user; the installer does not automatically turn on device registration, push messaging or accounts.

The Zygisk setting is written via Magisk's SQLite database and read back to confirm. The official Vector module enables our own `dev.dan.androidsubsystem.microgspoof`, with the scope fixed to `system/0`. The official JSON CLI is used to check for specific `Failed` states, the enabled state and the scope, followed by a cold boot. The compatibility module returns the required compatible signature only to Services / Companion that carry the real microG certificate, keeps the original package visibility and permission checks, and does not let arbitrary apps impersonate Google packages.

## What the automated checks prove

The local `microg-report.json` records the following separately:

- `installed`: installed APK paths, real signing certificates and versions.
- `modules_verified`: the Magisk module exists and is not disabled, plus the Vector enabled state and exact scope.
- `signature_checked`: true only when SignatureProbe actually ran inside Android and every check passed for both packages.
- `signature_check`: results of GET_SIGNATURES, GET_SIGNING_CERTIFICATES, raw and SHA256 certificate queries, and rejection of a wrong certificate.
- `m5_self_check_required`: the UI self-check and real-app acceptance are still needed. `signature_checked` does not mean every Google API is implemented.

If the signature check fails, the installer writes a failure report and exits; it never reports success merely because the packages exist. Report location:

```text
~/Library/Application Support/AndroidSubsystem/microg-report.json
```

To rerun the checks from the project directory:

```bash
"$HOME/Library/Application Support/AndroidSubsystem/runtime/python/bin/python3" scripts/provision-microg.py --verify-only
```

## Manual self-check on the M5

1. Open Android Subsystem, and after it starts, open microG Settings from the app library and go to "Self-Check". Check the Services install, system permissions and signature-compatibility items. Keep the results as they are first — don't turn on accounts, registration or push messaging just to clear optional warnings.
2. If it asks for location, notification or contacts permissions, grant them in Android Settings according to what the apps you need actually require. Different AOSP versions may show different check items.
3. Fully stop and restart twice, check that Magisk, Vector and microG still work, and rerun the automated checks.
4. Install the ARM64 / Java APKs you actually need and test sign-in, network, notifications, location and separate windows for each. Pure AOSP has no preinstalled Chrome or Google Play; install the legitimate APKs or an open-source browser you need.
5. If an app depends on interfaces microG hasn't implemented yet or needs Play Integrity, record the specific app and error; don't treat "installed successfully" as a compatibility guarantee.

The Mac graphics windows continue to use the existing SurfaceServer → RGBA → Metal path. The new image and signature hook must be tested on the M5; Linux mocks and host-side APK checks cannot replace those results.

## Licenses and sources

- [microG GmsCore](https://github.com/microg/GmsCore): source code and license for Services / Companion.
- [microG GSFProxy](https://github.com/microg/GSFProxy): this package keeps the source used and its Apache 2.0 license.
- [Magisk v30.7](https://github.com/topjohnwu/Magisk/tree/v30.7): official patching and module tools, GPLv3.
- [Vector v2.2](https://github.com/JingMatrix/Vector/tree/v2.2): the official Zygisk / Xposed framework and CLI; when distributing, the corresponding source must be provided as its license requires.
- The [Android SDK terms](https://developer.android.com/studio/terms) and the licenses of each runtime component must still be followed separately. Removing GApps does not mean a review for commercial redistribution has been completed.
