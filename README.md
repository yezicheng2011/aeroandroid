# aeroandroid

> 中文 | [English](#english)

aeroandroid 是一个在 Apple Silicon Mac（M 系列芯片）上运行 Android 16 的“Android 子系统”。它基于官方 Android 模拟器和 AOSP arm64 系统镜像，自带：

- macOS 端原生应用（Swift，`macos/`），把 Android 应用窗口显示为独立的 Mac 窗口；
- Android 端桥接应用（Java，`guest/`），负责画面传输、输入法、通知和剪贴板；
- Python 后端控制器（`backend/subsystem.py`）以及安装、配置、诊断脚本（`scripts/`、`*.command`）；
- microG 支持（`third_party/GSFProxy`）。

## 构建与运行

需要 Apple Silicon Mac、macOS 14+，以及联网下载约 1.8 GB 的运行时（Android 模拟器、系统镜像、JDK 等）。

1. 双击 `Build.command`（或在终端运行），它会调用 `scripts/setup-mac.sh` 下载运行时并构建 macOS 应用和 guest APK。
2. 运行 `Install.command` 安装；`Graphics-Acceptance.command` 做图形验收。
3. 离线安装：从 https://aeroandroid.com/releases.html 下载 `M5-Android16-*.zip` 完整包，里面的 `runtime-cache/` 已包含所有运行时。

详见 `docs/`。

## 本仓库未包含的内容

- `microg-spoof/` 签名兼容模块和 Magisk `host_patch.sh`：二者为 GPL-3.0，单独分发，请从上游获取。
- 预编译 APK（`artifacts/`）和运行时缓存（`runtime-cache/`）：由构建脚本生成或下载。

## 许可证

Apache-2.0，Copyright 2026 daniel.ye。第三方组件见 `NOTICE`。

---

## English

aeroandroid is an "Android subsystem" that runs Android 16 on Apple Silicon Macs. It is built on the official Android Emulator with an AOSP arm64 system image and adds a native macOS app (Swift, `macos/`) that shows each Android app as its own Mac window, an Android-side bridge app (Java, `guest/`) for frame transport, IME, notifications and clipboard, a Python controller (`backend/subsystem.py`), install/diagnostic scripts (`scripts/`, `*.command`), and microG support (`third_party/GSFProxy`).

### Build and run

Requires an Apple Silicon Mac with macOS 14+ and about 1.8 GB of runtime downloads.

1. Run `Build.command`; it calls `scripts/setup-mac.sh` to fetch the runtime and build the macOS app and guest APKs.
2. Run `Install.command`, then `Graphics-Acceptance.command` to verify graphics.
3. For an offline install, download the full `M5-Android16-*.zip` from https://aeroandroid.com/releases.html; its `runtime-cache/` contains every runtime component.

See `docs/` for details.

### Not included

- `microg-spoof/` and Magisk's `host_patch.sh` are GPL-3.0 and distributed separately; get them upstream.
- Prebuilt APKs (`artifacts/`) and the runtime cache are produced or downloaded by the build scripts.

### License

Apache-2.0, Copyright 2026 daniel.ye. See `NOTICE` for third-party components.
