aeroandroid 1.1.0 · Android Subsystem for Apple Silicon and Intel Macs
Lightweight DMG: manager app + installer + source. The Android runtime (about 1.8 GB) is downloaded during installation from official sources and each file is checked with SHA-256.

Requirements: Apple Silicon, or an Intel Mac from 2018 on, macOS 14 or later, the Xcode Command Line Tools (xcode-select --install), and at least 20 GB of free disk.

Install
1. If you have not already, install the Xcode Command Line Tools: xcode-select --install
   The installer builds the Mac app with Swift, so this step is required.
2. Control-click "Install aeroandroid.command" and choose Open, then Open again.
   On macOS 15, if macOS reports that it could not be opened: System Settings → Privacy & Security → Open Anyway (at the bottom).
   Or, in Terminal: bash "/Volumes/aeroandroid 1.1.0/Install aeroandroid.command"
3. The script copies the source to ~/aeroandroid (the DMG is read-only), then runs build.sh: download the runtime, build, and install.
   In mainland China, type y at the prompt to use mirrors there (the same as ./build.sh --mirror cn).
   You will be asked to read and accept the Android SDK license. Type YES to continue.
   Running it again resumes; files that already passed their checksum are not downloaded again.
4. When it finishes it opens ~/Applications/Android Subsystem.app. You can then run ~/aeroandroid/Graphics-Acceptance.command for a graphics check.

The Android Subsystem.app inside this DMG
That copy is prebuilt in CI and ad-hoc signed, so you can look at the interface and confirm the app opens on your Mac.
For actual use, open the copy the installer places in ~/Applications. That copy signs the Android-side components with a key generated on your Mac.
Do not mix the two. Their Android-side bridge components are signed differently, and mixing them fails with "Guest bridge install failed".

First-open prompt
This software is ad-hoc signed. It has no Apple Developer certificate, so Gatekeeper does not say the file is damaged. It says it cannot verify the developer.
Control-click the installer and choose Open, as in step 2.

The default install is Android 17, AOSP only, without Magisk, microG or pre-installed apps. Android camera apps can use the Mac camera.
./build.sh --pure explicitly selects the same default. The optional ./build.sh --with-gpl downloads GPL extensions.
The external Android runtime and JDK also have their own licenses, including GPL parts; see docs/LICENSING.md.
New installs choose a memory budget at each start. Adjust Automatic bounds or select Manual in Settings; running VMs do not resize live.

After installing
Double-click any .apk. A Mac app of the same name is created in ~/Applications. It appears in Launchpad and the Dock and shows only that app's window.
At the end of the install a Quick Boot snapshot is saved (disk use about equal to the memory setting), so the first time you open an app takes seconds instead of a cold boot.

Clear quarantine in Terminal (optional)
If macOS still blocks the installed app: xattr -dr com.apple.quarantine "$HOME/Applications/Android Subsystem.app"

Logs: ~/Library/Application Support/AndroidSubsystem/logs/
License: Apache-2.0, Copyright 2026 daniel.ye. See LICENSE and NOTICE.
Project: https://github.com/yezicheng2011/aeroandroid
