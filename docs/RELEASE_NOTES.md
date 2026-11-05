## aeroandroid 0.3.0 · macOS DMG (Apple Silicon + Intel)

**下载 / Download:** `aeroandroid-0.3.0-macOS-universal.dmg` — Apple 芯片与 Intel Mac（Intel 需 2018 年及以后机型）通用，macOS 14+。不支持 Windows。 / Universal: Apple Silicon and Intel (2018+), macOS 14+. Not Windows.

### 本版新内容 / What's new
- **双击 `.apk` 即装成 Mac 应用**：隐藏安装助手会安装应用，并在 `~/Applications` 生成带真实图标的独立 `.app`（自己的 Dock 图标，只显示该应用窗口）。
- **默认 Android 17**（API 37）完整版：Magisk root + microG + 预装 Aurora Store / Fennec；`./build.sh --android 16` 或 `--pure` 可选。
- **游戏**：Mac 手柄映射为 Android 游戏手柄；GPU / 60 FPS 等性能选项。
- **Intel Mac 支持**：universal 二进制；Intel 首次打开会提示部分 arm64-only 应用无法运行。
- **签名**：应用与 DMG 均 ad-hoc 签名；打开时提示「无法验证开发者」，不会显示「已损坏」。右键 → 打开即可。
- **版权 / Copyright：** Copyright © 2026 daniel.ye叶子诚（Apache-2.0）。详见 `NOTICE` 与 `docs/LICENSING.md`。

轻量版：管理程序（Android Subsystem.app）+ 安装脚本 + 源码 + 首次安装说明。安卓运行环境（约 1.8 GB）在安装时从官方源下载，逐个校验 SHA-256（`--mirror cn` 可用国内镜像）。

### 安装
1. 打开 DMG，右键「安装 aeroandroid.command」→「打开」（macOS 15+：系统设置 → 隐私与安全性 →「仍要打开」）。
2. 脚本把源码复制到 `~/aeroandroid` 并运行 `build.sh`，完成后安装到 `~/Applications/Android Subsystem.app`。
3. 详见 DMG 内「首次安装说明 README-FIRST.txt」。

### 签名
免费 ad-hoc 签名（无苹果开发者证书）：打开时不会显示「已损坏」，会提示「无法验证开发者」，右键「打开」即可。用 `SHA256SUMS.txt` 校验下载。

### 为什么没有「完整离线版」DMG
Android Emulator、platform-tools、build-tools、cmdline-tools、platform 和系统镜像均采用 *Android Software Development Kit License Agreement*，其第 3.4 条禁止再分发，因此不能打包进 Release。安装脚本在你本机从 Google 官方（或镜像）下载，并要求你接受该许可。

### 第三方组件及许可证
DMG 内包含：
- aeroandroid 源码、管理程序、MacBridge 桥接 APK — Apache-2.0
- third_party/GSFProxy（microG GsfProxy）— Apache-2.0（部分文档/图标 CC-BY-SA-4.0 / CC0-1.0）

安装时下载（不在 DMG 内，各自保持原许可证）：
- Android SDK emulator / platform / build-tools / cmdline-tools / platform-tools / arm64 或 x86_64 系统镜像 — Android SDK License Agreement
- OpenJDK 17（Eclipse Temurin）— GPL-2.0 with Classpath Exception
- CPython 3.12（python-build-standalone）— PSF License
- scrcpy v5.0.1 — Apache-2.0
- 完整版默认还会下载：Magisk、host_patch.sh、Vector、microg-spoof — GPL-3.0；microG GmsCore / Companion、Aurora Store、Fennec — 见各自上游许可证
