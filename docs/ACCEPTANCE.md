# M5 验收清单

当前需要在用户 M5 上完成。请先确认构建和基础显示，不要直接以大型游戏作为首次验证对象。

完整安装先运行 `Build.command`（已有 Google 镜像版本用 `Migrate-to-AOSP.command`），随后运行 `Graphics-Acceptance.command`。单独排查图形时可用 `Graphics-Install.command` 跳过 root 和 microG。自动结果和两个应用的实际像素 PNG 会保存在本机运行目录的 `acceptance/日期时间` 下。自动报告不含认证 token。随后打开的两个原生窗口需要人工检查实际画面和操作效果；不能用 PNG 存在代替 Metal 验收。检查纯 AOSP / microG 时请另外完成 [microG 自检](MICROG.md)。

1. 双击 Install.command，记录任何 Swift / Metal 编译错误。成功后应用应在 ~/Applications 中。
2. 在设置页“检查运行环境”，确认 Apple Silicon、硬件加速、Android 16 ARM64 镜像、ADB 都可用。
3. 点击启动；启动完成后应用库应显示应用标签和图标。
4. 打开安卓设置（com.android.settings），确认画面在一个原生 Mac 窗口内显示。它应属于安卓子系统进程，不是 scrcpy 窗口。
5. 打开第二个安卓应用，同时移动、缩放两个窗口。一个窗口变化不应改变另一个窗口的内容。
6. 验证颜色：红、蓝、透明区域不能出现通道颠倒；文字和界面不能上下翻转。
7. 分别点击两个窗口中的按钮，滚动列表。输入应只作用于目标显示器。
8. 在可输入文字的位置测试英文、中文输入法、退格、回车、方向键、Cmd+A / C / V。检查焦点切换后文字仍发给正确的应用。
9. 最小化一个窗口，确认另一个继续响应；恢复后应重新出现画面。
10. 关闭一个窗口，确认另一窗口保留。重新打开关闭的应用，应用保存的数据不应丢失。
11. 安装一个 ARM64 / Java APK，刷新应用库后打开。split APK 应在同一次文件选择里全选安装。
12. 导入一个文件，在安卓 Download/MacBridge 找到它，再导出到 Mac。验证同名文件不会被默默覆盖。
13. 可选：在 Android Mac Bridge 内打开通知访问设置，允许监听，再在 Mac 设置页启用通知。触发一条通知并点击它打开对应应用。
14. 停止子系统，确认所有窗口关闭；重新启动后新 AOSP 环境中应用数据仍然存在。
15. 打开 microG 设置检查 Self-Check，并重新运行 `provision-microg.py --verify-only`；检查 Magisk / Vector 冷启动后仍生效。设备注册、推送、Google 账号均按用户需要选择，不作为图形或基础安装通过的条件。
16. 迁移后的内存仍为原配置；新 AVD 不出现原 Google Play / Chrome。旧 userdata 留在独立备份位置，不自动混入新系统。

已知当前无法验收为完成：原生音频、跨 VM 零拷贝、独立 Dock 进程身份、摄像头 / 麦克风、所有应用兼容性。

## 收集诊断

在终端进入项目目录运行：

```bash
"$HOME/Library/Application Support/AndroidSubsystem/runtime/python/bin/python3" scripts/collect-diagnostics.py
```

报告保存到桌面 AndroidSubsystem-Diagnostics.json，不自动上传。它包含运行检查、应用进程信息和有限日志，可能带有本机路径与应用名称；不包含 surface-token。

如果安装阶段失败，可保留 Install.command 的终端输出。若图形窗口黑屏，优先查看 surface-bridge.log 中的 VirtualDisplay / InputManager / permission 错误。
