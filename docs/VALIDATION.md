# Build and Validation Record

This record distinguishes controlled tests, a real Android Guest, and real macOS / M5 testing, so that simulated results are never mistaken for end-to-end results.

| Item | Status | Environment and scope |
|---|---|---|
| Controller, archives, migration, Magisk / microG install flow | Controlled checks passed | Linux: 18 controller, 8 offline-install, 6 Magisk, 12 microG and 4 safe-migration checks; uses a fake Guest / external processes, so it cannot prove the install and signature hook ran on the M5 |
| Ports and shutdown handling after memory changes | Controlled checks passed | Real TCP on Linux reproducing TIME_WAIT; verified rejection of live listeners, whole-port-pair selection, locking when the old instance hasn't confirmed exit, delayed ADB exit, and the new memory launch parameters; not verified on a Mac |
| Java → Swift frame protocol interop | Passed | Java actually generates RGBA packets, Swift actually compiles and decodes them; includes 7 invalid-frame rejection checks |
| Native Mac source syntax | Passed | Parsed with the official Swift 6.2 compiler; no macOS SDK type checking or linking |
| Android 16 Guest bridge APK | Build, signing and verification passed | Real Android SDK API 36, Java, D8, aapt2, apksigner |
| Offline SDK install-record fix | Passed | cmdline-tools 23.0 Java libraries of the same version; reproduced the missing-emulator error, and after adding package.xml for the six pinned packages, both list_installed and AVD creation passed; VM not booted |
| Install script exit handling on Bash 3.2 | Passed | Official GNU Bash 3.2; exit codes 0 / 1 / 42 preserved under three locales, Chinese output and log paths correct; still needs re-verification on a Mac |
| Real Android 16 x86_64 Guest | Booted; testing stopped at the user's request | API 36, bridge APK installed, SurfaceServer ready, real VirtualDisplay created; no passing frame-capture report yet |
| Real Android Surface / input / dual-display test | Pending | Uses tests/guest_smoke.py; results will be saved separately |
| SwiftUI / Metal build and display on the M5 | Old version reported working by the user | User reported it runs normally after the gray-screen patch; the new pure AOSP image and microG still need re-acceptance on the M5 |
| microG, GSFProxy, signature-compatibility APK and Vector archives | Host checks passed | Pinned SHA256; real aapt2 package names, manifest permissions, versions and apksigner signature verification; Vector module id and official CLI data format cross-checked. Signature hook not run in the Guest |
| M5 pure AOSP, Magisk / Vector mounting, microG and cold boot | Pending | The install actually performs root / package / scope / both PackageInfo and certificate query checks; the server did not boot a new ARM64 AOSP Guest, so this cannot be marked as passed in advance |
| Cross-VM shared memory / zero-copy / native audio | Not implemented | Currently an RGBA-over-TCP graphics path |

## Reproducing the protocol test

In an environment with Java and Swift compilers:

```bash
javac -d work/protocol-java guest/src/dev/dan/androidsubsystem/SurfaceWire.java tests/GenerateSurfaceFrame.java
java -cp work/protocol-java GenerateSurfaceFrame work/frame.bin
swiftc macos/Sources/AndroidSubsystem/GraphicsProtocol.swift tests/GraphicsProtocolTests.swift -o work/graphics-protocol-tests
work/graphics-protocol-tests work/frame.bin
```

## Real Guest test

Once the subsystem is running on the M5, you can obtain a local session with native-session. That file contains the local graphics token; keep it in a private working directory and never upload or publish it.

```bash
mkdir -p work
chmod 700 work
umask 077
python3 backend/subsystem.py native-session '{"package":"com.android.settings"}' > work/session.json
python3 tests/guest_smoke.py --session work/session.json --output work/guest-smoke
```

The test launches two different apps, Settings and Mac Bridge, compares their displayIds, and checks frame size, resize, whether input injection is accepted, and whether one display still receives frames after the other is closed. It does not test actual Metal display, nor does it prove that text / touch input is correct in every third-party app.
