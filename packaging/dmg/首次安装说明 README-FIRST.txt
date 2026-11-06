aeroandroid 1.0.1 · 安卓子系统（Android Subsystem for Apple Silicon and Intel Macs）
轻量版 DMG：管理程序 + 安装脚本 + 源码。安卓运行环境（约 1.8 GB）在安装时从官方源下载并逐个校验 SHA-256。

要求：Apple 芯片或 Intel Mac（Intel 需 2018 年及以后机型），macOS 14+，Xcode 命令行工具（xcode-select --install），至少 20 GB 空闲空间。

【安装步骤】
1. 右键（或按住 Control 点按）「安装 aeroandroid.command」→ 选「打开」→ 再点「打开」。
   macOS 15 若提示「未打开」：系统设置 → 隐私与安全性 → 最下方点「仍要打开」。
   也可以在「终端」里运行：bash "/Volumes/aeroandroid 1.0.1/安装 aeroandroid.command"
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

默认安装完整版（AOSP + Magisk + microG，预装 Aurora Store 和 Fennec 浏览器；Mac 摄像头可在安卓相机中使用）。
只要纯 AOSP：cd ~/aeroandroid && ./build.sh --pure
完整版会从上游下载 GPL-3.0 组件，它们保持各自的许可证。

【安装之后】
双击任意 .apk 文件即可安装：会在 ~/Applications 生成同名 Mac 应用，在启动台和 Dock 中打开，只显示该应用的窗口。
安装结束时会保存一份「快速启动」快照（占用磁盘约等于内存设置），所以第一次打开应用只需几秒，而不是冷启动。

【终端里解除隔离（可选）】
如果 macOS 仍然拦截：xattr -dr com.apple.quarantine "/Applications/Android Subsystem.app"

日志：~/Library/Application Support/AndroidSubsystem/logs/
许可证：Apache-2.0，见 LICENSE / NOTICE。项目主页：https://github.com/yezicheng2011/aeroandroid

----------------------------------------------------------------------
English: Apple Silicon or Intel (2018+), macOS 14+. Right-click "安装 aeroandroid.command" → Open (macOS 15: System
Settings → Privacy & Security → Open Anyway). It copies the source to ~/aeroandroid and runs build.sh,
which downloads the pinned runtime (~1.8 GB, SHA-256 checked), builds and installs
~/Applications/Android Subsystem.app. Use that installed copy; the prebuilt app in this DMG is a preview.
Ad-hoc signed (free): macOS shows "cannot verify developer", not "damaged".
Default is now the full edition (--pure for AOSP only). After installing, double-click any .apk: it becomes a
Mac app in ~/Applications with its own Dock icon. A Quick Boot snapshot is saved at the end of the install
(disk use about the RAM setting) so the first app launch takes seconds.
If macOS still blocks the app: xattr -dr com.apple.quarantine "/Applications/Android Subsystem.app"