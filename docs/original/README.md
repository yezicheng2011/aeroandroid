# Android Subsystem for Mac · 开发验收版 0.2.0

目标：在 M5 / Apple Silicon Mac 上提供类似 WSA 的安卓应用桌面体验。默认运行配置为纯 AOSP Android 16（API 36）ARM64 + 持久 Magisk root + 开源 microG。新的镜像、root 与 microG 需要在 M5 上验收。Android 17（API 37）仅在对应 ARM64 系统镜像可用时启用，绝不自动降级到 Android 15 或更早版本。

本版本改用 `default` 纯 AOSP 镜像，不附带或安装 GApps、Google Play 商店、Google Play 服务或 Google Chrome。microG Services 和 Companion 使用兼容包名，但它们是开源实现；Companion 不是可浏览和下载应用的 Google Play 商店。不会自动登录 Google 账号、启用设备注册或推送，也不附带 Google 专有 DroidGuard。商业分发仍需分别处理官方 SDK 协议、GPL / LGPL 对应源码和许可通知；使用 AOSP 与 microG 不会自动解决整个发行包的授权。

**当前是需要 M5 实测的工程原型，不是已经完成、与 WSA 等价的产品。** 当前服务器是 Linux x86_64，无法完成 macOS SwiftUI / Metal 构建与实际图形验收。

## 当前主通路

```text
ARM64 Android VM（官方 Android Emulator / HVF，现有图形运行基础）
  └─ 自研 SurfaceServer（shell UID、app_process）
       ├─ 应用 A → VirtualDisplay A → ImageReader / Surface A
       ├─ 应用 B → VirtualDisplay B → ImageReader / Surface B
       └─ 认证 TCP 协议，经本机 ADB forward
            ├─ RGBA8 原始帧 → macOS IOSurface / CVPixelBufferPool → Metal → 原生 NSWindow
            └─ 鼠标 / 滚轮 / 按键 / 输入法 / 焦点 / 可见性 / resize / close
```

主界面打开应用走 `native-session`，不会用 scrcpy 创建应用窗口。scrcpy 只保留为开发对照工具和缺少 companion 时的应用列表回退。

每个窗口有单独的 Guest VirtualDisplay；不会把一个安卓桌面画面裁切成多个窗口。关闭连接释放显示器，最小化时移除该显示器的 Surface，恢复时重新挂接。Android Activity 的销毁、暂停、恢复仍由安卓系统管理，需要验证各应用行为。

**当前 VM 边界会复制像素。IOSurface 只用于 Mac 内部 CPU / Metal 共享缓冲，尚未实现跨 VM 共享内存、virtio-gpu blob 导出或零拷贝。** 现有模拟器内部的 gfxstream 等组件不是本项目自己实现的 GPU 虚拟化后端。原始帧默认最高 30 FPS，有分辨率上限和缓冲上限；尚未做性能承诺。

## 安装与已有版本迁移

交付包内包含源码与 `runtime-cache`。解压后双击 `AndroidSubsystem/Build.command`：它自动准备纯 AOSP 运行时、编译 Mac 应用、修补私有 Magisk ramdisk、安装 microG，并运行模块配置和签名兼容检查。`Install.command` 和 `Migrate-to-AOSP.command` 同样执行完整安装；迁移入口用于已有 Google 镜像版本。

```text
M5-Android16-0.2.0-AOSP-microG/
  AndroidSubsystem/
    Build.command
    Install.command
    Migrate-to-AOSP.command
    artifacts/                  # 桥接 APK、GSFProxy、限定包名的签名兼容模块
  runtime-cache/
    android16-macos/             # 官方 SDK 归档、纯 AOSP ARM64 镜像、仓库元数据
    mac-tools/                  # 锁定的 ARM64 Python、Java、scrcpy
    provision/                  # Magisk、官方 microG APK、官方 Vector 模块
```

1. Mac 需 macOS 14 或更新版本、至少 20 GB 可用空间，以及 Xcode Command Line Tools。若缺少开发工具，先运行 `xcode-select --install`；本包不包含 Apple SDK。
2. 首次安装双击 `Build.command`；已有版本双击 `Migrate-to-AOSP.command`。脚本校验依赖并显示需要接受的 Android SDK 协议，无需预装 Python、Java 或 Homebrew。
3. 升级时先退出管理应用，并调用已安装的旧后端停止旧 VM，确认完全退出后再修改配置。若现有私有 Python 缺失，脚本会在修改前停止。原内存、CPU 等设置保留。
4. 纯 AOSP 使用独立 `MacAndroid_16_AOSP_arm64` AVD，不直接复用旧 Google 系统的 userdata。旧 userdata 保留为离线备份，旧私有 Google 镜像只在新 runtime 完整配置成功后移除。旧安卓应用需要重新安装；应用内部数据不会自动迁入。
5. 编译结果安装到 `~/Applications/Android Subsystem.app`。运行 [microG 自检](docs/MICROG.md)，再按 [验收清单](docs/ACCEPTANCE.md) 检查显示、输入、冷启动和所需应用。

完整日志保存在 `~/Library/Application Support/AndroidSubsystem/logs/install-日期-时间-进程号.log`；终端在成功或失败后显示日志位置并等待回车。SDK、Python、Java 和运行数据放在同一私有运行目录，不自动上传日志。

`Graphics-Install.command` 只准备纯 AOSP 图形环境，跳过 root 和 microG。它用于单独排查图形问题，之后可运行 `Build.command` 完成完整配置。`Graphics-Acceptance.command` 自动抓取两个不同应用的实际帧、保存 PNG、检查显示器和关闭隔离，并打开原生窗口供人工观察；文件存在不代表 Metal 或所有应用已经通过验收。

缓存可以与源码并列，也可以放进 `AndroidSubsystem/runtime-cache`，内置目录优先。放在其他位置时：

```bash
ANDROID_SUBSYSTEM_CACHE='/你的/runtime-cache' ./Build.command
```

开发者可用 `scripts/setup-mac.sh 16` 在线准备纯 AOSP 与原生桥接。这个开发入口会在 Mac 上下载工具，不包含完整的锁定 Magisk / microG 安装；交付和迁移应使用离线 `Build.command`。

## 已实现的代码

- 原生 SwiftUI 应用库、应用图标、搜索、APK 安装（含一起选择的 split APK）、卸载。
- 自研每应用显示器、帧协议、原生 Metal 窗口、窗口大小回传。
- 鼠标触摸映射、滚轮、导航按键、Mac 输入法文字提交、Mac Bridge IME。
- Cmd+V 文字提交，Cmd+C / Cmd+X 后读取安卓文本剪贴板；实际授权与焦点行为待验收。
- 启动入口导出：保存 `.app` 到指定目录，通过主应用 URL scheme 打开对应安卓应用。
- 文件导入 / 导出，交换目录为安卓 `Download/MacBridge`，拒绝覆盖已有导出文件。
- 安卓通知监听与 macOS 通知转发，需要两侧分别授权；当前需管理应用保持运行。
- 运行环境隔离、所有权检查、PID 复用保护、图形连接认证、并发操作队列、诊断报告。
- 持久 Magisk ramdisk 配置、官方修补脚本编排、冷启动 root / 管理器检查，ramdisk 哈希与镜像 tag 绑定。
- 纯 AOSP 迁移、锁定 microG APK 安装、按实际 manifest 与 AOSP 权限定义生成的 privapp allowlist、Zygisk / Vector 模块启用与限定 `system/0` scope 的读回验证。
- 签名兼容限定为真实 microG 签名的 Services / Companion；检查两种 PackageInfo 查询、证书查询及错误证书拒绝，不向任意 APK 开放签名伪装。

## 尚未完成

- 跨虚拟机共享内存 / 共享 GPU buffer、完整自研 virtio-gpu / gfxstream 类后端。
- 原生图形通路的音频桥接。
- 应用窗口独立的 Dock 进程身份和图标；当前导出的是启动入口，窗口属于管理应用进程。
- 麦克风、摄像头、定位、通知动作、文件选择器与 Finder 的深层集成。
- 系统级常驻桥接与省电策略，以及无需开发工具的签名 / 公证安装包。
- 新纯 AOSP 镜像与 microG 在 M5 上的完整运行、应用适配、自检和冷启动验证；DRM、反作弊以及所有第三方应用的兼容性。microG 不保证 Play Integrity、银行软件或所有 Google API 正常。
- Android 17 的可安装 ARM64 镜像和实际运行验证。

不能将“源码编译”和“协议测试通过”视为以上项目已经完成。

## 验证

```bash
python3 -m unittest discover -s tests -v
```

该测试使用受控的外部进程模拟运行时，覆盖生命周期、双窗口对照通路、APK / 文件操作、版本检查、所有权隔离、自研服务复用与认证、归档路径检查。**它不替代真实安卓 / Metal 测试。**

Guest APK 用真实 Android 16 SDK 与 Java 编译、签名并校验。Java 输出的真实帧序列通过 Swift 解码器进行协议互操作测试。Mac UI 源码通过 Swift 语法解析；完整 SDK 类型检查、链接和显示必须在 Mac 上完成。

Magisk root 见 [运行配置说明](docs/ROOT.md)，microG 的功能范围、自动验证及手动自检见 [microG 说明](docs/MICROG.md)。

更多细节见 [图形通路说明](docs/GRAPHICS.md)、[验收清单](docs/ACCEPTANCE.md) 和 [构建验证记录](docs/VALIDATION.md)。

## 参考与第三方依赖

- [Android Emulator 的硬件加速](https://developer.android.com/studio/run/emulator-acceleration)
- [Android 16 SDK](https://developer.android.com/about/versions/16/setup-sdk)
- [Android DisplayManager](https://developer.android.com/reference/android/hardware/display/DisplayManager)
- [Apple IOSurface](https://developer.apple.com/documentation/iosurface)
- [scrcpy 官方仓库](https://github.com/Genymobile/scrcpy)（开发对照工具，Apache 2.0）
- [Eclipse Temurin](https://adoptium.net/) 和 [Python Build Standalone](https://github.com/astral-sh/python-build-standalone)
- [microG Services / Companion](https://github.com/microg/GmsCore)、[GSFProxy](https://github.com/microg/GSFProxy)
- [Vector](https://github.com/JingMatrix/Vector)，通过官方 CLI 配置限定范围的自有兼容模块

云盘归档是用户自己的私有依赖缓存；各第三方组件按其各自许可证使用。
