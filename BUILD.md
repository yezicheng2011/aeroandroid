# aeroandroid 自主编译 / Self-build

> 中文 | [English](#english)

## 中文

### 环境要求
- Apple Silicon Mac（M1–M5），macOS 14 或更新
- Xcode Command Line Tools：`xcode-select --install`
- 系统自带的 `curl`、`unzip`、`tar`、`python3`
- 至少 20 GB 可用空间，下载约 1.8 GB

JDK 17、Android SDK（platform、build-tools、cmdline-tools、platform-tools、emulator、arm64 系统镜像）、Python 3.12 和 scrcpy 都由 `build.sh` 按 `scripts/runtime-lock.json` 里锁定的版本下载，并逐个校验 SHA-256，不需要另外安装 Homebrew 或 Android Studio。

### 一条命令编译
```bash
./build.sh                 # 自动选择下载源，编译并安装纯 AOSP 版本
./build.sh --mirror cn     # 中国大陆：GitHub 走代理，Android SDK 走腾讯云镜像
./build.sh --with-gpl      # 完整版：额外从上游下载 GPL-3.0 组件，安装 Magisk + microG
./build.sh --check         # 只检查环境
./build.sh --download-only # 只下载到 ./runtime-cache
```
可用环境变量：`GH_MIRROR`（默认 `https://gh-proxy.com/`）、`SDK_MIRROR`（默认 `https://mirrors.cloud.tencent.com/AndroidSDK/`）、`ANDROID_SUBSYSTEM_CACHE`。镜像只是下载地址，文件仍按锁定的 SHA-256 校验，镜像失败时自动回退到官方地址。

流程：检查环境 → 下载运行时 → 解出私有 JDK 和 build-tools → 编译 Android 端 APK（MacBridge、GraphicsProbe，`--with-gpl` 时再加 microG 组件）→ 运行 `Install.command` 编译 Mac 应用并安装。完成后打开 `dist/Android Subsystem.app`，再运行 `Graphics-Acceptance.command` 验收图形。

### 关于 GPL 组件
本仓库为 Apache-2.0。microG 签名兼容模块（`microg-spoof/`，派生自 FakeGApps）和 Magisk 的 `host_patch.sh` 是 GPL-3.0，所以不在包里。只有加 `--with-gpl` 时，`build.sh` 才会从上游下载它们（校验 SHA-256），并在终端显示许可证提示；它们保持 GPL-3.0，不能当作 Apache-2.0 再分发。不加这个参数时安装的是纯 AOSP 图形版本，不含 Magisk 和 microG。

### 常见问题
- **“需要 Apple Silicon Mac”**：只支持 arm64 的 macOS，Intel Mac 和 Linux 不行。
- **Xcode Command Line Tools 缺失**：运行 `xcode-select --install`，装完重开终端。
- **下载慢或失败**：用 `--mirror cn`，或设置 `GH_MIRROR=https://ghfast.top/`；中断后重跑会断点续传，已校验的文件会跳过。
- **SHA-256 不匹配**：镜像返回了错误文件，脚本会自动换官方地址重试；仍失败就删除 `runtime-cache` 里对应的文件再跑。
- **SDK 许可证**：安装时会显示 Android SDK 许可证，需要你确认。
- **空间不足**：至少要 20 GB，完整版需要更多给 Guest 数据。
- **安装日志**：在 `~/Library/Application Support/AndroidSubsystem/logs/`。诊断用 `scripts/collect-diagnostics.py`。
- **不想自己编译**：到 https://aeroandroid.com/releases.html 下载带离线依赖的完整包。

---

## English

### Requirements
- Apple Silicon Mac (M1–M5), macOS 14 or later
- Xcode Command Line Tools: `xcode-select --install`
- `curl`, `unzip`, `tar`, `python3` (shipped with macOS)
- At least 20 GB free disk; about 1.8 GB of downloads

`build.sh` downloads JDK 17, the Android SDK pieces (platform, build-tools, cmdline-tools, platform-tools, emulator, arm64 system image), Python 3.12 and scrcpy at the versions pinned in `scripts/runtime-lock.json`, checking each SHA-256. No Homebrew or Android Studio needed.

### One command
```bash
./build.sh                 # auto-pick mirror, build and install the pure-AOSP edition
./build.sh --mirror cn     # mainland China: GitHub via proxy, Android SDK via Tencent mirror
./build.sh --with-gpl      # full edition: also fetch GPL-3.0 parts, install Magisk + microG
./build.sh --check         # prerequisites only
./build.sh --download-only # only fill ./runtime-cache
```
Environment: `GH_MIRROR` (default `https://gh-proxy.com/`), `SDK_MIRROR` (default `https://mirrors.cloud.tencent.com/AndroidSDK/`), `ANDROID_SUBSYSTEM_CACHE`. Mirrors only change where bytes come from; every file is still checked against its pinned SHA-256, and the official URL is used as a fallback.

Flow: check prerequisites → download runtime → unpack a private JDK and build-tools → compile guest APKs (MacBridge, GraphicsProbe, plus the microG parts with `--with-gpl`) → run `Install.command`, which builds the Mac app and installs. Then open `dist/Android Subsystem.app` and run `Graphics-Acceptance.command`.

### GPL components
This repository is Apache-2.0. The microG signature module (`microg-spoof/`, derived from FakeGApps) and Magisk's `host_patch.sh` are GPL-3.0 and are not included. Only with `--with-gpl` does `build.sh` download them from upstream (SHA-256 checked) and print a license notice; they remain GPL-3.0 and must not be redistributed as Apache-2.0. Without the flag you get the pure-AOSP graphics edition, without Magisk or microG.

### Troubleshooting
- **"Requires an Apple Silicon Mac"**: only arm64 macOS is supported; not Intel Macs or Linux.
- **Missing Command Line Tools**: `xcode-select --install`, then reopen Terminal.
- **Slow or failing downloads**: use `--mirror cn` or set `GH_MIRROR=https://ghfast.top/`. Re-running resumes; verified files are skipped.
- **SHA-256 mismatch**: the mirror served a bad file; the script retries from the official URL. If it still fails, delete that file from `runtime-cache` and re-run.
- **SDK license**: the installer shows the Android SDK license for you to accept.
- **Disk space**: 20 GB minimum; the full edition needs more for guest data.
- **Logs**: `~/Library/Application Support/AndroidSubsystem/logs/`; diagnostics via `scripts/collect-diagnostics.py`.
- **Don't want to build**: download the full offline package at https://aeroandroid.com/releases.html.
