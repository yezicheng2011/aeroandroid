# Graphics Path and Implementation Boundaries

## Guest

`SurfaceServer` is launched by ADB with the shell UID, and its code is loaded from the dex of the compiled APK. Its Context belongs to `com.android.shell`, which avoids making system calls with a mismatched UID under the `android` package name. This process handles displays, Surfaces and input injection; Activities inside the ordinary APK do not perform these privileged system operations.

Each authenticated connection creates a `VirtualDisplay` and an RGBA8 `ImageReader`, and launches the target launcher Activity onto that display. Frames are read from the ImageReader row by row, honouring the gralloc row stride, and written out in a fixed order. The whole screen is never captured and then cropped to the app area.

The VirtualDisplay is released when the graphics connection closes. A resize swaps the ImageReader and the display Surface sequentially on the same image Handler; callbacks from the old reader are ignored. The buffer count is fixed at 3, `acquireLatestImage` is used, and the frame rate is limited to 15–30 FPS. The Surface involves a GPU-to-CPU readback, so performance needs to be measured.

Separate displays use the trusted-display, own-display-group, keep-unlocked and own-focus flags; the backend wakes the Guest before launching. Display state, app launch output, the first frame and resize exceptions are written to surface-bridge.log. Exceptions from asynchronous resizes are sent back to the Host and the session is closed, so the window never keeps waiting after the frame-capture thread has exited. The Guest APK's SHA256 is part of the service-reuse condition, so the old service is replaced after an update.

Input is injected through InputManager / InputManagerGlobal with shell permissions, and every event specifies its displayId explicitly. Text is passed to the InputMethodService through the companion's DUMP-permission-protected ContentProvider, so committed Unicode from Mac input methods is supported. Focus, copy, minimize and restore behaviour needs to be verified in Android multi-display mode, and hidden APIs may need adjustment when versions change.

## Wire protocol v1

Every packet uses a 1-byte type + a 4-byte big-endian payload length.

| Type | Direction | Content |
|---|---|---|
| 1 | Guest → Host | width u32, height u32, rowBytes u32, timestamp u64, RGBA8 |
| 3 | Guest → Host | UTF-8 JSON: ready, error, input-warning, clipboard |
| 16 | Host → Guest | UTF-8 JSON: hello, pointer, scroll, key, text, resize, focus, visibility, clipboard-get, close |

`hello` contains the protocol version, target package name, size, DPI, frame rate and a random authentication token. The host token lives in the local private data directory, and the guest token in a 0700 directory owned by shell. The guest listens only on its loopback, and the host connects through a loopback port allocated by ADB. Tokens are never logged or passed as command-line arguments.

Control packets are at most 64 KiB; graphics packets are at most 2560×2560×4+20 bytes. The Host checks dimensions, stride and exact length to avoid unbounded allocation driven by an untrusted length. The Host queues only one pending frame, and the IOSurface buffer pool has at most 4 buffers in use.

## macOS

`SurfaceWindowController` creates one Cocoa NSWindow per Android app. `SurfaceConnection` parses the stream packets; `SurfaceView` uses an IOSurface-backed CVPixelBufferPool, fills frames into CPU-writable buffers, and imports them into Metal via CVMetalTextureCache.

The Guest byte order is RGBA, while the CoreVideo buffers use BGRA for Metal compatibility; the fragment shader swaps the channels. Buffers and textures are retained until the Metal command completes, so the GPU never uses an IOSurface that has already been recycled. Window resizes send the new display size back; input coordinates are mapped according to the window content and the guest frame size.

The connection starts only once the window and its error callbacks are ready, and the initial Surface size is kept until the first frame succeeds. Scaling is based on the window's point size, with the longest side capped at 1280, so Retina doesn't quadruple the uncompressed data volume. If no first frame arrives within 20 seconds, the window shows an error; surface-mac.log distinguishes between receiving RGBA and finishing the Metal draw. When the drawable isn't ready yet, the retained static frame is retried; texture/encoder failures are reported explicitly. The first-draw timeout is paused while minimized and restarts on restore. The user has reported that the M5 picture is normal after the gray-screen fix in the old version; display, focus and lifecycle still need to be re-confirmed on the new pure AOSP image.

## The next hurdle: zero-copy

The current protocol uses copying TCP; shared textures inside the Mac are not the same as Guest / Host shared video memory. True zero-copy requires:

1. The host provides mappable shared memory / GPU blobs for each app buffer, defining registration, release, lifecycle and stride / format information.
2. The virtual device associates that buffer reference with the guest DMA / GPU buffer; this requires changes to the guest graphics allocator / composer and the host graphics backend — modifying the APK alone is not enough.
3. Sync fences are passed across the VM so that guest writes, host Metal sampling and reuse never conflict.
4. Compositor output is routed per display / application, handling secure content, multi-window switching and hot rebuilds.
5. HVF memory mapping, the gfxstream / ANGLE / Metal export path and system-image support are verified on the M5.

This version does not dress up these unimplemented steps as working interfaces. The raw frame path provides an observable, measurable display and input baseline; the transport layer can later be replaced while keeping the native windows, input and app management.
