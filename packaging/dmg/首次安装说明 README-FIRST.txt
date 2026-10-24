aeroandroid 0.2.1 · 安卓子系统（Android Subsystem for Apple Silicon Macs）
轻量版 DMG：管理程序 + 安装脚本 + 源码。安卓运行环境（约 1.8 GB）在安装时从官方源下载并逐个校验 SHA-256。

要求：Apple Silicon Mac（M1–M5，不支持 Intel），macOS 14+，Xcode 命令行工具（xcode-select --install），至少 20 GB 空闲空间。

【安装步骤】
1. 右键（或按住 Control 点按）「安装 aeroandroid.command」→ 选「打开」→ 再点「打开」。
   macOS 15 若提示「未打开」：系统设置 → 隐私与安全性 → 最下方点「仍要打开」。
   也可以在「终端」里运行：bash "/Volumes/aeroandroid 0.2.1/安装 aeroandroid.command"
2. 脚本把源码复制到 ~/aeroandroid（DMG 是只读的），然后运行 build.sh：下载运行环境 → 编译 → 安装。
   中国大陆可在提示时输入 y 使用国内镜像（等同 ./build.sh --mirror cn）。
   过程中需要阅读并接受 Android SDK 许可协议。中断后重新运行会续传，已校验的文件不会重下。
3. 完成后自动打开 ~/Applications/Android Subsystem.app，并可运行 ~/aeroandroid/Graphics-Acceptance.command 做图形验收。

【关于 DMG 里的 Android Subsystem.app】
这是 CI 预编译、ad-hoc 签名的管理程序，用于查看界面/确认能在你的 Mac 上打开。
正式使用请用安装脚本装到 ~/Applications 的那一份（它用你本机生成的密钥签名安卓端组件）。
不要同时混用两份：两份里的安卓端桥接组件签名不同，混用会导致「Guest bridge install failed」。

【首次打开提示】
本软件使用免费的 ad-hoc 签名，没有苹果开发者证书，所以不会显示「已损坏」，但会提示「无法验证开发者」。
按上面第 1 步右键「打开」即可。

默认安装纯 AOSP 版（不含 Magisk / microG）。完整版：cd ~/aeroandroid && ./build.sh --with-gpl
（会从上游下载 GPL-3.0 组件，它们保持各自的许可证。）

日志：~/Library/Application Support/AndroidSubsystem/logs/
许可证：Apache-2.0，见 LICENSE / NOTICE。项目主页：https://github.com/yezicheng2011/aeroandroid

----------------------------------------------------------------------
English: Apple Silicon only, macOS 14+. Right-click "安装 aeroandroid.command" → Open (macOS 15: System
Settings → Privacy & Security → Open Anyway). It copies the source to ~/aeroandroid and runs build.sh,
which downloads the pinned runtime (~1.8 GB, SHA-256 checked), builds and installs
~/Applications/Android Subsystem.app. Use that installed copy; the prebuilt app in this DMG is a preview.
Ad-hoc signed (free): macOS shows "cannot verify developer", not "damaged".
