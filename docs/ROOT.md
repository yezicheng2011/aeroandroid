# Android 16 · Magisk root 与 microG 配置

默认使用纯 AOSP Android 16 ARM64、Magisk v30.7 和开源 microG。所有依赖固定在 `runtime-lock.json`，本版本不安装 GApps 或 Google 专有系统组件。microG 的能力、自检和商业分发注意事项见 [microG 说明](MICROG.md)。

## Magisk 实现

1. 启动本项目的纯 AOSP AVD，确认 API 36 / ARM64 与 AVD 所有权。
2. 在 Guest 中使用 Magisk v30.7 官方 `host_patch.sh` 修补 ramdisk；脚本及许可证保留在 `third_party/Magisk`。
3. 保存私有 `images/16/default/ramdisk.magisk.img`，记录原始、修补后和 Magisk APK 的 SHA256，并绑定 `image_tag=default`。原 SDK ramdisk不改写，旧 Google 镜像的 patched ramdisk不会复用。
4. 冷启动显式指定该 ramdisk 和 Magisk 官方 AVD 测试所用参数。
5. 验证 Magisk、su 和管理器，再恢复 shell UID 的 ADB，保持图形服务的权限归属。
6. microG 阶段启用 Zygisk，安装官方 Vector 与自有系统模块，检查启用状态、scope 和 Android 实际签名查询，再恢复 ADB shell。

服务器完成的是安装编排、主机 APK 编译 / 签名验证和受控流程测试，没有启动新的 ARM64 AOSP Guest。M5 上的真实修补、授权、挂载和冷启动结果由安装脚本检查，并需用户验收。

## 单独运行

在源码目录运行完整 root 配置后再配置 microG：

```bash
"$HOME/Library/Application Support/AndroidSubsystem/runtime/python/bin/python3" scripts/provision-mac.py /你的/runtime-cache
"$HOME/Library/Application Support/AndroidSubsystem/runtime/python/bin/python3" scripts/provision-microg.py /你的/runtime-cache
```

重新检查：

```bash
"$HOME/Library/Application Support/AndroidSubsystem/runtime/python/bin/python3" scripts/provision-mac.py --verify-only
"$HOME/Library/Application Support/AndroidSubsystem/runtime/python/bin/python3" scripts/provision-microg.py --verify-only
```

移除私有 Magisk ramdisk 启动覆盖：

```bash
"$HOME/Library/Application Support/AndroidSubsystem/runtime/python/bin/python3" scripts/provision-mac.py --rollback-root
```

回滚停止子系统并移除启动覆盖，不删除 AVD userdata 或 SDK 镜像。它会使依赖 Magisk / Zygisk 的 microG 签名兼容通路失效，不会声称已移除全部应用更新或恢复所有 userdata。

## M5 验收

- 两次完全停止 / 启动后，Magisk 仍显示已安装。
- 普通安卓应用的 su 请求由 Magisk 管理授权，而非只证明 adb root 可用。
- microG 自动签名检查及界面 Self-Check，通过后再测试需要的应用。
- root 和 microG 配置后，多窗口图形、IME、焦点、通知仍正常。

Android 17 需要新的 ARM64 镜像和单独 root / microG 验收，当前固定配置仅为 Android 16。

来源：[Magisk v30.7 host_patch.sh](https://github.com/topjohnwu/Magisk/blob/v30.7/scripts/host_patch.sh)、[官方 AVD 测试脚本](https://github.com/topjohnwu/Magisk/blob/v30.7/scripts/avd.sh)。
