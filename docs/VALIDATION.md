# 构建与验证记录

该记录区分受控测试、真实 Android Guest、macOS / M5 实测，避免把模拟结果当作端到端运行结果。

| 项目 | 状态 | 环境与范围 |
|---|---|---|
| 控制器、归档、迁移、Magisk / microG 安装流程 | 受控检查通过 | Linux，18 项控制器、8 项离线安装、6 项 Magisk、12 项 microG、4 项安全迁移检查；使用 fake Guest / 外部进程，不能证明 M5 上的安装和签名钩子已运行 |
| 内存调整后的端口与停机处理 | 通过受控检查 | Linux 真实 TCP 复现 TIME_WAIT，验证活监听拒绝、整个端口对选择、旧实例未确认退出时锁定、ADB 延迟退出及新内存启动参数；未在 Mac 上验证 |
| Java → Swift 帧协议互操作 | 通过 | Java 实际生成 RGBA 包，Swift 实际编译并解码；含 7 项无效帧拒绝检查 |
| 原生 Mac 源码语法 | 通过 | 官方 Swift 6.2 编译器 parse；没有 macOS SDK 类型检查和链接 |
| Android 16 Guest 桥接 APK | 编译、签名、校验通过 | 真实 Android SDK API 36、Java、D8、aapt2、apksigner |
| 离线 SDK 安装记录修复 | 通过 | 同版本 cmdline-tools 23.0 Java 库；复现缺少 emulator 报错，补齐六个锁定包的 package.xml 后 list_installed 与 AVD 创建均通过；未启动 VM |
| 安装脚本 Bash 3.2 退出处理 | 通过 | 官方 GNU Bash 3.2；三个 locale 下退出码 0 / 1 / 42 保留，中文输出和日志路径正常；Mac 仍需复验 |
| 真实 Android 16 x86_64 Guest | 已启动、测试按用户要求停止 | API 36，桥接 APK 已安装，SurfaceServer 已就绪，真实 VirtualDisplay 已创建；尚未取得通过的抓帧报告 |
| Android Surface / 输入 / 双显示器真实测试 | 尚待完成 | 使用 tests/guest_smoke.py，结果将单独保存 |
| M5 上 SwiftUI / Metal 编译与显示 | 旧版本用户反馈正常 | 用户反馈灰屏补丁后运行正常；新纯 AOSP 镜像和 microG 仍需 M5 上重新验收 |
| microG、GSFProxy、签名兼容 APK 与 Vector 归档 | 主机检查通过 | 锁定 SHA256；真实 aapt2 包名、manifest 权限、版本和 apksigner 签名验证；Vector module id 与官方 CLI 数据格式核对。未在 Guest 中运行签名钩子 |
| M5 纯 AOSP、Magisk / Vector 挂载、microG 与冷启动 | 尚待完成 | 安装时真实执行 root / package / scope / 两种 PackageInfo 与证书查询检查；服务器未启动新 ARM64 AOSP Guest，不能预先标记通过 |
| 跨 VM 共享内存 / 零拷贝 / 原生音频 | 尚未实现 | 当前为 RGBA TCP 图形通路 |

## 复现协议测试

有 Java 与 Swift 编译器的环境中：

```bash
javac -d work/protocol-java guest/src/dev/dan/androidsubsystem/SurfaceWire.java tests/GenerateSurfaceFrame.java
java -cp work/protocol-java GenerateSurfaceFrame work/frame.bin
swiftc macos/Sources/AndroidSubsystem/GraphicsProtocol.swift tests/GraphicsProtocolTests.swift -o work/graphics-protocol-tests
work/graphics-protocol-tests work/frame.bin
```

## 真实 Guest 测试

M5 上的子系统启动后，可以用 native-session 获取本地 session。该文件包含本机图形 token，应放在私有工作目录中，不要上传或公开。

```bash
mkdir -p work
chmod 700 work
umask 077
python3 backend/subsystem.py native-session '{"package":"com.android.settings"}' > work/session.json
python3 tests/guest_smoke.py --session work/session.json --output work/guest-smoke
```

测试会启动设置与 Mac Bridge 两个不同应用，比较 displayId，检查帧尺寸、resize、输入注入是否被接受，以及关闭一个显示器后另一个是否仍能收到帧。它不测试 Metal 实际显示，也不证明文字 / 触点在每个第三方应用中都正确。
