# M5 Acceptance Checklist

This currently needs to be completed on the user's M5. Confirm the build and basic display first — don't use a large game as the first test.

For a full install, run `Build.command` first (use `Migrate-to-AOSP.command` if you have the earlier Google-image version), then run `Graphics-Acceptance.command`. To troubleshoot graphics alone, use `Graphics-Install.command`, which skips root and microG. The automated results and actual-pixel PNGs of the two apps are saved under `acceptance/<date-time>` in the local run directory. The automated report contains no authentication token. The two native windows opened afterwards need a manual check of the actual picture and interaction; the existence of the PNGs does not replace Metal acceptance. When checking pure AOSP / microG, also complete the [microG self-check](MICROG.md).

1. Double-click Install.command and note any Swift / Metal compile errors. On success the app should be in ~/Applications.
2. On the Settings page, click "Check runtime environment" and confirm that Apple Silicon, hardware acceleration, the Android 16 ARM64 image and ADB are all available.
3. Click Start; once startup completes, the app library should show app labels and icons.
4. Open Android Settings (com.android.settings) and confirm it is displayed inside a native Mac window. It should belong to the Android Subsystem process, not a scrcpy window.
5. Open a second Android app and move and resize both windows at the same time. Changing one window must not change the other's content.
6. Check colours: red, blue and transparent areas must not have swapped channels; text and UI must not be flipped upside down.
7. Click buttons and scroll lists in each window. Input must only affect the target display.
8. In a text field, test English and Chinese input methods, Backspace, Return, arrow keys and Cmd+A / C / V. Check that text still goes to the right app after switching focus.
9. Minimize one window and confirm the other keeps responding; after restoring, the picture should reappear.
10. Close one window and confirm the other stays. Reopen the closed app; its saved data must not be lost.
11. Install an ARM64 / Java APK, refresh the app library and open it. For split APKs, select all parts in a single file selection.
12. Import a file, find it in Android's Download/MacBridge, then export it back to the Mac. Verify that a file with the same name is not silently overwritten.
13. Optional: in Android Mac Bridge, open the notification access settings and allow listening, then enable notifications on the Mac Settings page. Trigger a notification and click it to open the corresponding app.
14. Stop the subsystem and confirm all windows close; after restarting, app data in the new AOSP environment should still be there.
15. Open microG settings and check Self-Check, then rerun `provision-microg.py --verify-only`; check that Magisk / Vector still work after a cold boot. Device registration, push messaging and Google accounts are optional per user needs and are not conditions for passing graphics or the basic install.
16. After migration, memory stays at the original setting; the new AVD does not contain the old Google Play / Chrome. Old userdata stays in a separate backup location and is not automatically merged into the new system.

Known items that cannot currently be accepted as complete: native audio, cross-VM zero-copy, a separate Dock process identity, camera / microphone, and compatibility with all apps.

## Collecting diagnostics

In Terminal, go to the project directory and run:

```bash
"$HOME/Library/Application Support/AndroidSubsystem/runtime/python/bin/python3" scripts/collect-diagnostics.py
```

The report is saved to AndroidSubsystem-Diagnostics.json on the Desktop and is not uploaded automatically. It includes runtime checks, app process information and limited logs, and may contain local paths and app names; it does not include the surface-token.

If the install step fails, keep the Terminal output of Install.command. If a graphics window is black, first check surface-bridge.log for VirtualDisplay / InputManager / permission errors.
