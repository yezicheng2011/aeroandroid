# Licensing

This is a plain-language review of how aeroandroid fits under the Apache License 2.0. It is **not legal advice**;
have a lawyer confirm it before a commercial release.

## Short answer

The code and assets in this repository can be released under Apache-2.0, because:

- everything the project wrote itself (Swift, C, Java, Python, shell, the logo and `AppIcon.icns`) is original and is
  licensed by its copyright holder under Apache-2.0. A scan of the tracked sources found no copied third-party code
  (no foreign copyright, SPDX or "derived from" markers outside `third_party/`); scrcpy, adb and the emulator are only
  run as separate programs. The maintainer should still confirm that older code was written by them;
- the only third-party code tracked in git is `third_party/GSFProxy` (Apache-2.0, with its license files kept);
- everything under a stronger or different license is **downloaded onto the user's own Mac at build time**, from its
  upstream, and is never copied into this repository or into the release DMG.

## What is in this repository

| Item | License | Notes |
|------|---------|-------|
| `macos/`, `guest/`, `backend/`, `scripts/`, `tests/`, `docs/`, `*.command`, `build.sh` | Apache-2.0 | Original work (see above) |
| `assets/` (logo, `AppIcon.icns`) | Apache-2.0 | Drawn by `scripts/make-logo.py`; no third-party artwork or fonts |
| `third_party/GSFProxy` (microG GsfProxy) | Apache-2.0 code | Its launcher icons (`mipmap-*/*.png`) are CC-BY-SA-4.0 and some docs CC0-1.0; keep `.reuse/` and `LICENSES/` with it |

The repository contains no GPL code, no Google code and no prebuilt binaries other than the generated icon files.

## Downloaded at build or run time (not distributed by this project)

| Component | License | Used for |
|-----------|---------|----------|
| Android SDK emulator, platform, build-tools, cmdline-tools, system image | Android SDK License, AOSP (Apache-2.0 and others) | The Android runtime; the user accepts Google's SDK license in the installer |
| OpenJDK 17 (Temurin) | GPL-2.0 with Classpath Exception | Building the guest APKs |
| CPython (python-build-standalone) | PSF | Running the backend |
| scrcpy | Apache-2.0 | Fallback display path |
| Magisk, its `host_patch.sh` | GPL-3.0 | Root (full edition only) |
| Vector | GPL-3.0 | Module framework for microG (full edition only) |
| microG GmsCore, Companion | Apache-2.0 | Google API compatibility (full edition only) |
| microg-spoof (from aeroandroid.com source zip) | GPL-3.0-only | Signature compatibility (full edition only) |
| Aurora Store | GPL-3.0-or-later | Pre-installed app, pinned F-Droid APK |
| Google APIs x86_64 system image (Intel Macs, full edition) | Android SDK License | Source of AOSP's ARM translator; only the translator files are copied out, the rest is discarded |
| Fennec F-Droid | MPL-2.0 | Pre-installed app, pinned F-Droid APK |

Because these arrive on the user's machine straight from their upstreams, this project is not redistributing them,
and a GPL component sitting next to Apache-2.0 code on one disk is a mere aggregate, not a combined work.
`build.sh` prints a GPL notice before fetching the GPL parts and verifies every file against a pinned SHA-256.
`build.sh` changes one line of `microg-spoof` after download (it admits Android 17); that modified file is still
GPL-3.0 and stays on the user's machine.

### The ARM translator on Intel Macs

`scripts/arm_translation.py` reads Google's image on the user's own Mac and copies a fixed set of files out of it: the
translator (`libndk_translation`, "berberis", Apache-2.0), its proxy libraries, and the arm64 builds of AOSP system
libraries it runs against (bionic, ICU, BoringSSL, zlib and others, under their own open-source licenses, listed in the
image's `NOTICE.txt`). No Google app or service is copied and the image is not kept. The result is a private
Magisk module on that Mac. This project does not host or redistribute it.

If you decide to host a prebuilt module (the installer accepts one through `ARM_TRANSLATION_MODULE`), that is a
redistribution: ship the relevant licenses from the image's `NOTICE.txt`, keep the Apache-2.0 notices, and check that
Google's Android SDK License allows it for your case. Building it on the user's machine, as the installer does, avoids the question.

## What you must do if you redistribute a build

The Apache-2.0 grant covers this repository only. If you publish anything that **contains** the downloaded
components, you take on their terms:

1. **Android SDK components** (emulator, system image, build-tools): the Android SDK License does not allow you to
   redistribute them. The release DMG leaves them out for this reason. Do not put them in an "offline package".
2. **GPL components** (Magisk, Vector, microg-spoof, Aurora Store, Temurin): if you ship them, you must ship their
   license text and offer their corresponding source under GPL, and must not describe them as Apache-2.0.
3. **Aurora Store and microG APKs**: the same, per each project's license; keep their notices.
4. **`NOTICE`**: Apache-2.0 requires you to keep it, with the attribution lines, in any redistribution.

> **Maintainer action:** the README points to an "offline package" at aeroandroid.com whose `runtime-cache/` holds
> these components. If it still contains Android SDK archives, it conflicts with point 1, and with Magisk, Vector or
> Aurora Store inside it, point 2 applies. Either remove those from the package, or make sure it is built and
> published within those terms.

## Other points

- **Trademarks.** Android is a trademark of Google LLC; Magisk, microG, Fennec, Firefox and Aurora are their owners'
  marks. They are used only to name the software. The logo is original and does not use the Android robot.
- **AI-assisted code.** Part of this repository was written with an AI assistant. As the licensor, the maintainer
  should review it and be comfortable granting the Apache-2.0 license over it; copyright in machine-written code is
  unsettled in some countries.
- **Pre-installed apps and Google services.** microG is a separate open-source implementation. No Google
  proprietary code or services are distributed here.
- **Design-time tools.** `scripts/make-logo.py` needs Pillow and numpy; they are not shipped.
