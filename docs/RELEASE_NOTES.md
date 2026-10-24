## aeroandroid 0.2.1 · macOS DMG (Apple Silicon)

**下载 / Download:** `aeroandroid-0.2.1-macOS-arm64.dmg` — 仅 Apple Silicon（M1–M5），macOS 14+。不支持 Intel Mac / Windows。

轻量版：管理程序（Android Subsystem.app）+ 安装脚本 + 源码 + 首次安装说明。安卓运行环境（约 1.8 GB）在安装时从官方源下载，逐个校验 SHA-256（`--mirror cn` 可用国内镜像）。

### 安装
1. 打开 DMG，右键「安装 aeroandroid.command」→「打开」（macOS 15：系统设置 → 隐私与安全性 →「仍要打开」）。
2. 脚本把源码复制到 `~/aeroandroid` 并运行 `build.sh`，完成后安装到 `~/Applications/Android Subsystem.app`。
3. 详见 DMG 内「首次安装说明 README-FIRST.txt」。

### 签名
免费 ad-hoc 签名（无苹果开发者证书）：打开时不会显示「已损坏」，会提示「无法验证开发者」，右键「打开」即可。用 `SHA256SUMS.txt` 校验下载。

### 为什么没有「完整离线版」DMG
Android Emulator、platform-tools、build-tools、cmdline-tools、platform 和 arm64-v8a 系统镜像均采用 *Android Software Development Kit License Agreement*，其第 3.4 条禁止再分发，因此不能打包进 Release。安装脚本在你本机从 Google 官方（或镜像）下载，并要求你接受该许可。

### 第三方组件及许可证
DMG 内包含：
- aeroandroid 源码、管理程序、MacBridge 桥接 APK — Apache-2.0
- third_party/GSFProxy（microG GsfProxy）— Apache-2.0（部分文档/图标 CC-BY-SA-4.0 / CC0-1.0）

安装时下载（不在 DMG 内，各自保持原许可证）：
- Android SDK emulator / platform / build-tools / cmdline-tools / platform-tools / arm64-v8a 系统镜像 — Android SDK License Agreement
- OpenJDK 17（Eclipse Temurin）— GPL-2.0 with Classpath Exception
- CPython 3.12（python-build-standalone）— PSF License
- scrcpy v5.0.1 — Apache-2.0
- 仅 `--with-gpl` 时：Magisk v30.7、host_patch.sh、Vector v2.2、microg-spoof — GPL-3.0；microG GmsCore — Apache-2.0；Companion（com.android.vending）— 专有

默认安装纯 AOSP 版，不含任何 GPL 组件。
