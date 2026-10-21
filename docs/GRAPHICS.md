# 图形通路与实现边界

## Guest

`SurfaceServer` 由 ADB 用 shell UID 启动，代码从已编译 APK 的 dex 加载。Context 归属 `com.android.shell`，避免用 `android` 包名发出 UID 不匹配的系统调用。该进程负责显示器、Surface、输入注入，普通 APK 内的 Activity 不承担这些系统权限操作。

每个认证连接创建一个 `VirtualDisplay` 和 RGBA8 `ImageReader`，将目标 launcher Activity 启动到该 display。帧从 ImageReader 按行读取，处理 gralloc row stride，按固定顺序写出。不会抓取整个屏幕后裁切应用区域。

图形连接关闭时释放 VirtualDisplay。resize 在同一图像 Handler 上顺序更换 ImageReader 与显示器 Surface；旧 reader 的回调被忽略。缓冲区数量固定为 3，使用 acquireLatestImage，帧率限制为 15–30 FPS。Surface 会涉及 GPU 到 CPU 的读回，性能需要实测。

独立显示使用可信显示、独立显示组、保持解锁及独立焦点标记；后端在启动前唤醒 Guest。display state、应用启动输出、第一帧与 resize异常写入 surface-bridge.log。异步 resize 的异常回传给 Host并关闭会话，避免抓帧线程退出而窗口仍等待。Guest APK SHA256 纳入服务复用条件，更新后会替换旧服务。

输入通过 InputManager / InputManagerGlobal 的 shell 权限注入，每个事件明确指定 displayId。文字经 companion 的受 DUMP 权限保护的 ContentProvider 传给 InputMethodService，支持 Mac 输入法提交 Unicode。焦点、复制、最小化和恢复行为需要在安卓多显示器模式下验证，隐藏 API 在版本变化时可能需要调整。

## Wire protocol v1

所有包使用 1 字节类型 + 4 字节大端 payload 长度。

| 类型 | 方向 | 内容 |
|---|---|---|
| 1 | Guest → Host | width u32、height u32、rowBytes u32、timestamp u64、RGBA8 |
| 3 | Guest → Host | UTF-8 JSON：ready、error、input-warning、clipboard |
| 16 | Host → Guest | UTF-8 JSON：hello、pointer、scroll、key、text、resize、focus、visibility、clipboard-get、close |

hello 包含协议版本、目标包名、尺寸、DPI、帧率与随机认证 token。host token 位于本地私有数据目录，guest token 位于 shell 所有的 0700 目录里。guest 仅监听其 loopback，host 通过 ADB 分配的 loopback 端口连接。token 不写日志，也不放进命令行参数。

控制包最多 64 KiB；图形包最多 2560×2560×4+20 字节。Host 检查尺寸、stride 和精确长度，避免根据不可信长度无限分配内存。Host 只排队一个待消费帧，IOSurface 缓冲池最多 4 个在用 buffer。

## macOS

`SurfaceWindowController` 为一个安卓应用创建一个 Cocoa NSWindow。`SurfaceConnection` 解析流包；`SurfaceView` 使用 IOSurface-backed CVPixelBufferPool，将帧填入 CPU 可写的缓冲区，再通过 CVMetalTextureCache 导入 Metal。

Guest 字节顺序是 RGBA，CoreVideo buffer 使用 BGRA 格式来获得 Metal 兼容性；fragment shader 执行通道交换。Metal command 完成前保留 buffer 与 texture，避免 GPU 使用已经回收的 IOSurface。窗口缩放回传显示器新尺寸；输入坐标按窗口内容和 guest 帧尺寸映射。

窗口及错误回调就绪后才开始连接，首帧成功前保持初始 Surface尺寸。缩放依据窗口点尺寸，最长边限制为1280，避免 Retina 把未压缩数据量放大四倍。20秒无首帧时窗口显示错误；surface-mac.log区分收到RGBA与完成Metal绘制。Drawable尚未就绪时重试保留的静态帧；纹理/编码器失败会明确回传。最小化期间暂停首次绘制超时，恢复时重新计时。用户已反馈旧版本灰屏修复后的 M5 画面正常；新纯 AOSP 镜像仍需重新确认显示、焦点与生命周期。

## 零拷贝的下一道关卡

当前协议走复制型 TCP；Mac 内部共享纹理不等于 Guest / Host 共享显存。真正零拷贝需要：

1. host 为每个应用 buffer 提供可映射的共享内存 / GPU blob，定义注册、释放、生命周期和 stride / format 信息。
2. 虚拟设备将该 buffer 引用与 guest DMA / GPU buffer 关联；修改 guest 图形 allocator / composer 与 host 图形后端，不能仅修改 APK。
3. 跨 VM 传递同步 fence，保证 guest 写入、host Metal 采样、复用三个阶段不冲突。
4. 按 display / application 路由 compositor 输出，处理 secure content、多窗口切换和热重建。
5. 在 M5 上验证 HVF 内存映射、gfxstream / ANGLE / Metal 导出路径与系统镜像支持。

本版本没有把这些未实现的步骤包装成已工作的接口。原始帧通路提供一个可观察、可测量的显示和输入基线，后续可以替换传输层而保留原生窗口、输入和应用管理。
