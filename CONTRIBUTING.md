# Contributing

Issues and pull requests are welcome.

## Installers and defaults

Most people should use the official macOS DMG from the
[GitHub releases](https://github.com/yezicheng2011/aeroandroid/releases) or
https://aeroandroid.com/releases.html. They do not package or compile the app.

`./build.sh` from a checkout installs the full edition by default (Android 17, AOSP + Magisk + microG).
`./build.sh --pure` is AOSP only. `--with-gpl` is an alias of the default. Android 16 is `--android 16`.

## Checks

```bash
python3 -m unittest discover -s tests
bash -n build.sh
```

GitHub Actions also runs shellcheck and, on macOS, `swift build --package-path macos`.

Do not commit `artifacts/`, `runtime-cache/`, `microg-spoof/`, or `third_party/Magisk/`.
Those are downloaded and verified by the build.
