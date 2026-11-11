# adb

The subsystem is a standard Android Emulator instance, so `adb` works with it. Two things made that awkward:
the installer keeps its own `adb` deep inside `~/Library/Application Support/AndroidSubsystem`, and the
device's port, and with it its serial, is not shown anywhere and can change.

## One click

Open **Settings → ADB (for developers)** in the Mac manager and choose **Open Terminal with adb**.
Android is started if it is stopped. Terminal then opens with the subsystem's own `adb` first on `PATH` and
`ANDROID_SERIAL` set to the subsystem's device, so plain commands reach it:

```bash
adb shell
adb install app.apk
adb logcat
```

**Copy adb command** puts the full command on the clipboard, for a script or a terminal you already have open:

```bash
'/Users/you/Library/Application Support/AndroidSubsystem/sdk/platform-tools/adb' -s emulator-5580
```

## Your own adb, Android Studio and other tools

The **Device** row shows two names for the same Android, for example `emulator-5580 · 127.0.0.1:5581`.

- Another adb on this Mac (Android Studio, Homebrew, Flutter and so on) lists the subsystem by itself as
  `emulator-5580`. Nothing has to be connected.
- If it is not listed, connect by address: `adb connect 127.0.0.1:5581`. adb only looks for emulators on
  ports 5554 to 5585 by itself. The subsystem normally uses 5580, and moves to another free port when that
  one is taken.
- Use one of the two, not both. Connected by address as well, the same Android is listed twice and adb
  answers "more than one device/emulator" until you pass `-s`.

**Use one adb version.** An `adb` of a different version restarts the adb server when it runs. The subsystem's
own connections go through that server, so open Android windows can lose their picture; close and reopen them.
The Terminal from **Open Terminal with adb** avoids this, because it uses the subsystem's `adb`.

## Without the manager

`status` reports the same details and never starts Android. `adb-terminal` starts Android when needed, writes
the Terminal script and prints its path:

```bash
python3 backend/subsystem.py status         # "adb": the adb path, serial, address and full command
python3 backend/subsystem.py adb-terminal   # "script": .../AndroidSubsystem/adb-terminal.command
```

## Scope

- Local only. The emulator accepts adb on localhost; this adds no listener and exposes nothing to the network.
- The script is written again each time it is opened, so it always names the current port. A Terminal left
  open across an Android restart on a different port keeps the old serial: open a new one.
- A shell profile that puts another `adb` ahead on `PATH` wins over the subsystem's. `ANDROID_SERIAL` still
  selects the subsystem's device; the version note above applies.
