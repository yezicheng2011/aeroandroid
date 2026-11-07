# Contributing

Issues and pull requests are welcome.

## Installers and defaults

Most people should use the official macOS DMG from the
[GitHub releases](https://github.com/yezicheng2011/aeroandroid/releases) or
https://aeroandroid.com/releases.html.
`Install aeroandroid.command` in that DMG downloads the runtime and builds the app.
It still needs the Xcode Command Line Tools (`xcode-select --install`).

`./build.sh` and `./build.sh --pure` install Android 17 AOSP only by default.
`--with-gpl` explicitly opts into the full edition, including GPL extensions. Android 17 is the only Android version.
Do not add GPL dependencies to aeroandroid's original code; keep its Apache-2.0 license and third-party notices.
The external Android runtime and JDK retain their upstream licenses (see `docs/LICENSING.md`).
All new UI text, messages and documentation must be English.

## Checks

```bash
python3 -m unittest discover -s tests
bash -n build.sh
```

GitHub Actions also runs shellcheck, builds and verifies the full guest APK with pinned Android tools,
and runs `swift build --package-path macos` on macOS. Storage integration tests use actual local HTTP requests;
see `docs/STORAGE.md` for the Mac/Android acceptance steps.
Desktop widget changes must also build `scripts/build-widget-probe.sh`; the probe checklist is in
`tests/widget_probe/README.md`, with host architecture and limits in `docs/WIDGETS.md`.

Do not commit `artifacts/`, `runtime-cache/`, `microg-spoof/`, or `third_party/Magisk/`.
Those are downloaded and verified by the build.
