# Contributing

Thanks for helping. Bug reports with a log (`~/Library/Application Support/AndroidSubsystem/logs/`) are the most
useful contribution; `python3 scripts/collect-diagnostics.py` gathers one locally and uploads nothing.

## Before you open a pull request

```bash
python3 -m unittest discover -s tests -p "test_*.py"     # needs e2fsprogs for the image tests
shellcheck --severity=warning -s bash build.sh *.command scripts/*.sh
cd macos && swift build -c release                       # on a Mac
```

CI runs the same on every pull request. A change to `build.sh` or another script needs a test that **runs** it;
`bash -n` only checks syntax.

## Rules

- **Licensing.** The project is Apache-2.0. Do not add GPL, Google or other third-party code or binaries to the
  repository; things like that are downloaded onto the user's Mac by the build and pinned by SHA-256. Read
  `docs/LICENSING.md` first, and add anything new to `NOTICE`.
- **Pins.** Every download has a SHA-256 in `scripts/runtime-lock*.json` or `scripts/preinstall.json`. Never add one
  you have not computed from the real file.
- **Say what was and was not run.** Much of this project cannot be exercised without a Mac; state clearly in the pull
  request what you ran.
