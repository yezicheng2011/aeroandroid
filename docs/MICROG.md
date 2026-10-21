# 纯 AOSP Android 16 与 microG

本版本使用 `system-images;android-36;default;arm64-v8a` 纯 AOSP 镜像。microG Services / Companion 是开源 Google API 兼容实现，使用 `com.google.android.gms` 和 `com.android.vending` 兼容包名。它们不是 Google 官方 Play 服务或 Play 商店，也不提供商店的应用目录。GSFProxy 转发旧版 GSF 广播接口。

不附带 GApps、Google Chrome 或专有 DroidGuard。不会自动登录账号、启用 Google 设备注册或云端推送。需要网络服务时，由用户在 microG 设置中明确选择；安装成功不会代表 Play Integrity、DRM、银行软件、游戏反作弊或所有 Google API 可用。

## 安装配置

`Build.command` / `Install.command` 按顺序完成纯 AOSP 安装、Mac 编译、Magisk 和 microG。已有 Google 镜像版本可运行 `Migrate-to-AOSP.command`。迁移前退出旧管理应用，并使用旧后端停止旧 VM，之后才修改配置。6 GB 等现有内存设置保留。新 AVD 隔离旧 userdata，旧应用需重新安装，旧数据保留为离线备份；不会把旧 Google 系统的包数据库混入纯 AOSP。

依赖归档和源码产物均按 SHA256 锁定。microG APK 用实际 `aapt2` manifest、版本和 `apksigner` 证书检查；已安装的同名包也检查真实 APK 证书，拒绝与专有 Google 包混装。

`mac_microg_api36` Magisk 模块安装 Services、Companion、GSFProxy 到 `system/priv-app`。权限 XML 仅允许 APK 实际申请且运行中 AOSP 定义为 privileged 的权限。普通危险权限仍由 Android 用户授权，安装器不自动打开设备注册、推送或账号。

Zygisk 配置通过 Magisk SQLite 写入并读取确认。官方 Vector 模块启用自有 `dev.dan.androidsubsystem.microgspoof`，scope 固定为 `system/0`。使用官方 JSON CLI 检查具体 `Failed`、启用状态和 scope，再冷启动。兼容模块只对具有真实 microG 证书的 Services / Companion 返回所需兼容签名，保留原包可见性与权限检查，不允许任意应用伪装成 Google 包。

## 自动检查能证明什么

本机 `microg-report.json` 分开记录：

- `installed`：已安装 APK 路径、真实签名证书和版本。
- `modules_verified`：Magisk 模块存在且未禁用、Vector 启用状态和精确 scope。
- `signature_checked`：只有 Android 里真正运行 SignatureProbe、两包所有检查通过时才为 true。
- `signature_check`：GET_SIGNATURES、GET_SIGNING_CERTIFICATES、原始及 SHA256 证书查询、错误证书拒绝的结果。
- `m5_self_check_required`：仍需界面自检与真实应用验收。signature_checked 不表示所有 Google API 已实现。

如果签名检查失败，安装器写出失败报告并退出，不会只凭包存在报告成功。报告位置：

```text
~/Library/Application Support/AndroidSubsystem/microg-report.json
```

在项目目录重新运行检查：

```bash
"$HOME/Library/Application Support/AndroidSubsystem/runtime/python/bin/python3" scripts/provision-microg.py --verify-only
```

## M5 上的手动自检

1. 打开安卓子系统，启动后从应用库打开 microG 设置，进入“自检 / Self-Check”。检查 Services 安装、系统权限和签名兼容项。先保留结果，不要为消除可选项提示自动打开账号、注册或推送。
2. 若提示定位、通知或联系人权限，按所需应用的功能在 Android 设置中选择授权。不同 AOSP 版本可能显示不同检查项。
3. 完全停止并重新启动两次，检查 Magisk、Vector 和 microG 仍生效，重新运行自动检查。
4. 安装你实际需要的 ARM64 / Java APK，分别测试登录、网络、通知、定位及独立窗口。纯 AOSP 不预装 Chrome 和 Google Play；可安装所需的合法 APK或开源浏览器。
5. 若应用依赖 microG 尚未实现的接口或需要 Play Integrity，记录具体应用和错误，避免把“安装成功”当作兼容性保证。

Mac 图形窗口继续使用现有 SurfaceServer → RGBA → Metal 通路。新的镜像和签名钩子必须在 M5 上实测；Linux mock 和主机 APK 检查不能代替这些结果。

## 许可与来源

- [microG GmsCore](https://github.com/microg/GmsCore)：Services / Companion 对应源码与许可证。
- [microG GSFProxy](https://github.com/microg/GSFProxy)：本包保留所用源码与 Apache 2.0 许可证。
- [Magisk v30.7](https://github.com/topjohnwu/Magisk/tree/v30.7)：官方修补与模块工具，GPLv3。
- [Vector v2.2](https://github.com/JingMatrix/Vector/tree/v2.2)：官方 Zygisk / Xposed 框架及 CLI；分发时须按其许可证提供对应源码。
- [Android SDK 协议](https://developer.android.com/studio/terms)和各运行时组件的许可证仍需分别遵守。移除 GApps 并不等于已经完成商业再分发授权审查。
