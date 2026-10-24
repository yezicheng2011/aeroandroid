import AppKit
import MetalKit
import CoreVideo
import Network

// Native graphics path. Guest Surface -> RGBA frame -> IOSurface-backed CVPixelBuffer
// -> CVMetalTexture -> Metal drawable. TCP copies at the VM boundary are explicit.
// This path does not run scrcpy and does not claim shared memory across the VM.

private final class PacketAccumulator {
    var data = Data()
    init(capacity: Int) { data.reserveCapacity(capacity) }
}

private enum SurfaceLog {
    private static let lock = NSLock()
    static func write(_ message: String) {
        lock.lock(); defer { lock.unlock() }
        let directory = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/AndroidSubsystem/logs")
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let file = directory.appendingPathComponent("surface-mac.log")
            if !FileManager.default.fileExists(atPath: file.path) {
                FileManager.default.createFile(atPath: file.path, contents: nil,
                                              attributes: [.posixPermissions: 0o600])
            }
            let handle = try FileHandle(forWritingTo: file)
            defer { try? handle.close() }
            try handle.seekToEnd()
            try handle.write(contentsOf: Data("\(ISO8601DateFormatter().string(from: Date())) \(message)\n".utf8))
        } catch { /* A log failure must not interrupt rendering. */ }
    }
}

final class SurfaceConnection {
    private let connection: NWConnection
    private let queue = DispatchQueue(label: "android.surface.transport")
    private var closed = false
    private var ready = false
    var onFrame: ((SurfaceFrame) -> Void)?
    var onEvent: (([String: Any]) -> Void)?
    var onError: ((String) -> Void)?
    init(port: UInt16) {
        let tcp = NWProtocolTCP.Options(); tcp.noDelay = true
        connection = NWConnection(host: "127.0.0.1", port: NWEndpoint.Port(rawValue: port)!,
                                  using: NWParameters(tls: nil, tcp: tcp))
    }
    func start(_ hello: [String: Any]) {
        connection.stateUpdateHandler = { [weak self] state in
            guard let self else { return }
            switch state {
            case .ready: self.sendPacket(hello); self.ready = true; self.readHeader()
            case .failed(let error): self.fail(error.localizedDescription)
            default: break
            }
        }
        connection.start(queue: queue)
    }
    func send(_ command: [String: Any]) {
        queue.async { [weak self] in
            guard let self, !self.closed, self.ready else { return }
            self.sendPacket(command)
        }
    }
    private func sendPacket(_ command: [String: Any]) {
        guard let json = try? JSONSerialization.data(withJSONObject: command), json.count <= 65536 else { return }
        var packet = Data([16])
        var count = UInt32(json.count).bigEndian
        withUnsafeBytes(of: &count) { packet.append(contentsOf: $0) }
        packet.append(json)
        connection.send(content: packet, completion: .contentProcessed { [weak self] error in
            if let error { self?.fail(error.localizedDescription) }
        })
    }
    private func readExact(_ count: Int, buffer: PacketAccumulator? = nil, completion: @escaping (Data) -> Void) {
        let packet = buffer ?? PacketAccumulator(capacity: count)
        guard !closed else { return }
        connection.receive(minimumIncompleteLength: 1, maximumLength: count - packet.data.count) { [weak self] data, _, complete, error in
            guard let self, !self.closed else { return }
            if let data { packet.data.append(data) }
            if packet.data.count == count { completion(packet.data) }
            else if let error { self.fail(error.localizedDescription) }
            else if complete { self.fail(L10n.t("gfx.closed")) }
            else { self.readExact(count, buffer: packet, completion: completion) }
        }
    }
    private func readHeader() {
        readExact(5) { [weak self] header in
            guard let self else { return }
            let type = header[header.startIndex], count = Int(header.u32(at: 1))
            guard count > 0, count <= SurfaceFrame.maximumPayload,
                  type == 1 || (type == 3 && count <= 65536) else { self.fail(L10n.t("gfx.bad_frame")); return }
            self.readExact(count) { [weak self] payload in
                guard let self else { return }
                do {
                    if type == 1 {
                        let frame = try SurfaceFrame.decode(payload)
                        // Acknowledge consumption on the main queue before reading another frame.
                        // This bounds queued frames to one instead of accumulating latency and RAM.
                        DispatchQueue.main.async { [weak self] in
                            self?.onFrame?(frame)
                            self?.queue.async { self?.readHeader() }
                        }
                    } else {
                        guard let event = try JSONSerialization.jsonObject(with: payload) as? [String: Any] else {
                            throw BridgeFailure(message: L10n.t("gfx.bad_control"))
                        }
                        DispatchQueue.main.async { [weak self] in self?.onEvent?(event) }
                        self.readHeader()
                    }
                } catch { self.fail(error.localizedDescription) }
            }
        }
    }
    private func fail(_ message: String) {
        guard !closed else { return }
        closed = true; connection.cancel()
        DispatchQueue.main.async { [weak self] in self?.onError?(message) }
    }
    func close() {
        send(["type": "close"])
        queue.asyncAfter(deadline: .now() + 0.1) { [weak self] in
            self?.closed = true; self?.connection.cancel()
        }
    }
}

final class SurfaceView: MTKView, MTKViewDelegate, NSTextInputClient {
    private var commandQueue: MTLCommandQueue!
    private var pipeline: MTLRenderPipelineState!
    private var textureCache: CVMetalTextureCache?
    private var pool: CVPixelBufferPool?
    private var pixelBuffer: CVPixelBuffer?
    private var dimensions = CGSize.zero
    private var marked = NSAttributedString(string: "")
    var control: (([String: Any]) -> Void)?
    var reportError: ((String) -> Void)?
    var resizeDisplay: ((Int, Int, Int) -> Void)?
    var baseDPI = 200
    var guestWidth = 1280
    var guestHeight = 960
    private var resizeWork: DispatchWorkItem?
    private var drawRetry: DispatchWorkItem?
    private var drawRetries = 0
    private var displayFailed = false
    private let statusLabel = NSTextField(labelWithString: L10n.t("gfx.connecting"))
    var onRendered: (() -> Void)?

    init(graphicsDevice: MTLDevice?) throws {
        guard let gpu = graphicsDevice else { throw BridgeFailure(message: L10n.t("gfx.no_metal")) }
        super.init(frame: .zero, device: gpu)
        commandQueue = gpu.makeCommandQueue()
        guard commandQueue != nil else { throw BridgeFailure(message: L10n.t("gfx.no_queue")) }
        colorPixelFormat = .bgra8Unorm
        framebufferOnly = true; autoResizeDrawable = true
        isPaused = true; enableSetNeedsDisplay = false
        clearColor = MTLClearColor(red: 0.06, green: 0.07, blue: 0.08, alpha: 1)
        delegate = self
        let cacheStatus = CVMetalTextureCacheCreate(kCFAllocatorDefault, nil, gpu, nil, &textureCache)
        guard cacheStatus == kCVReturnSuccess, textureCache != nil else {
            throw BridgeFailure(message: L10n.t("gfx.no_cache", cacheStatus))
        }
        statusLabel.alignment = .center
        statusLabel.textColor = .secondaryLabelColor
        statusLabel.lineBreakMode = .byWordWrapping
        statusLabel.translatesAutoresizingMaskIntoConstraints = false
        addSubview(statusLabel)
        NSLayoutConstraint.activate([
            statusLabel.centerXAnchor.constraint(equalTo: centerXAnchor),
            statusLabel.centerYAnchor.constraint(equalTo: centerYAnchor),
            statusLabel.widthAnchor.constraint(lessThanOrEqualTo: widthAnchor, multiplier: 0.85)
        ])
        let shader = """
        #include <metal_stdlib>
        using namespace metal;
        struct Varying { float4 position [[position]]; float2 uv; };
        vertex Varying surfaceVertex(uint id [[vertex_id]]) {
            const float2 positions[4] = {float2(-1,-1),float2(1,-1),float2(-1,1),float2(1,1)};
            const float2 uv[4] = {float2(0,1),float2(1,1),float2(0,0),float2(1,0)};
            Varying out; out.position=float4(positions[id],0,1); out.uv=uv[id]; return out;
        }
        fragment float4 surfaceFragment(Varying in [[stage_in]], texture2d<float> surface [[texture(0)]]) {
            constexpr sampler s(filter::linear, address::clamp_to_edge);
            // Guest bytes are RGBA. The CoreVideo storage uses BGRA for Metal compatibility.
            return surface.sample(s,in.uv).bgra;
        }
        """
        let library = try gpu.makeLibrary(source: shader, options: nil)
        let description = MTLRenderPipelineDescriptor()
        description.vertexFunction = library.makeFunction(name: "surfaceVertex")
        description.fragmentFunction = library.makeFunction(name: "surfaceFragment")
        description.colorAttachments[0].pixelFormat = colorPixelFormat
        pipeline = try gpu.makeRenderPipelineState(descriptor: description)
    }
    required init(coder: NSCoder) { fatalError("Storyboard initialization is unsupported") }
    override var acceptsFirstResponder: Bool { true }
    override var isFlipped: Bool { true }

    func showStatus(_ message: String) {
        guard !displayFailed else { return }
        statusLabel.stringValue = message
        statusLabel.isHidden = false
    }
    func showFailureMessage(_ message: String) {
        showStatus(message)
        displayFailed = true; drawRetry?.cancel()
    }

    func present(_ frame: SurfaceFrame) {
        do {
            if dimensions != CGSize(width: CGFloat(frame.width), height: CGFloat(frame.height)) || pool == nil {
                let attributes: [String: Any] = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
                    kCVPixelBufferWidthKey as String: frame.width, kCVPixelBufferHeightKey as String: frame.height,
                    kCVPixelBufferMetalCompatibilityKey as String: true,
                    kCVPixelBufferIOSurfacePropertiesKey as String: [:]]
                let status = CVPixelBufferPoolCreate(kCFAllocatorDefault,
                    [kCVPixelBufferPoolMinimumBufferCountKey as String: 3] as CFDictionary, attributes as CFDictionary, &pool)
                guard status == kCVReturnSuccess else { throw BridgeFailure(message: L10n.t("gfx.no_pool")) }
                dimensions = CGSize(width: CGFloat(frame.width), height: CGFloat(frame.height))
            }
            var buffer: CVPixelBuffer?
            guard let pool else { throw BridgeFailure(message: L10n.t("gfx.pool_missing")) }
            let bufferStatus = CVPixelBufferPoolCreatePixelBufferWithAuxAttributes(kCFAllocatorDefault, pool,
                [kCVPixelBufferPoolAllocationThresholdKey as String: 4] as CFDictionary, &buffer)
            if bufferStatus == kCVReturnWouldExceedAllocationThreshold { return }
            guard bufferStatus == kCVReturnSuccess, let buffer else {
                throw BridgeFailure(message: L10n.t("gfx.no_buffer", bufferStatus))
            }
            let lockStatus = CVPixelBufferLockBaseAddress(buffer, [])
            guard lockStatus == kCVReturnSuccess else { throw BridgeFailure(message: L10n.t("gfx.no_pixels", lockStatus)) }
            guard let base = CVPixelBufferGetBaseAddress(buffer) else {
                CVPixelBufferUnlockBaseAddress(buffer, [])
                throw BridgeFailure(message: L10n.t("gfx.null_pixels"))
            }
            let stride = CVPixelBufferGetBytesPerRow(buffer)
            guard stride >= frame.rowBytes else {
                CVPixelBufferUnlockBaseAddress(buffer, [])
                throw BridgeFailure(message: L10n.t("gfx.bad_stride"))
            }
            frame.pixels.withUnsafeBytes { bytes in
                guard let source = bytes.baseAddress else { return }
                for y in 0..<frame.height { memcpy(base.advanced(by: y * stride), source.advanced(by: y * frame.rowBytes), frame.rowBytes) }
            }
            CVPixelBufferUnlockBaseAddress(buffer, [])
            pixelBuffer = buffer; guestWidth = frame.width; guestHeight = frame.height
            drawRetry?.cancel(); drawRetries = 0
            draw()
        } catch { reportError?(error.localizedDescription) }
    }
    func draw(in view: MTKView) {
        guard !displayFailed else { return }
        guard let buffer = pixelBuffer, let cache = textureCache else { return }
        guard let pass = currentRenderPassDescriptor, let drawable = currentDrawable else {
            // A static app may send only one frame before its window gets a drawable.
            // Retry that retained frame instead of waiting for another Guest update.
            if drawRetries < 10, window?.isMiniaturized != true {
                drawRetries += 1
                let work = DispatchWorkItem { [weak self] in self?.draw() }
                drawRetry = work
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.05, execute: work)
            }
            return
        }
        guard let command = commandQueue.makeCommandBuffer() else { reportError?(L10n.t("gfx.no_command")); return }
        var texture: CVMetalTexture?
        let status = CVMetalTextureCacheCreateTextureFromImage(kCFAllocatorDefault, cache, buffer, nil,
            .bgra8Unorm, CVPixelBufferGetWidth(buffer), CVPixelBufferGetHeight(buffer), 0, &texture)
        guard status == kCVReturnSuccess, let texture, let metalTexture = CVMetalTextureGetTexture(texture) else {
            reportError?(L10n.t("gfx.no_texture", status)); return
        }
        guard let encoder = command.makeRenderCommandEncoder(descriptor: pass) else {
            reportError?(L10n.t("gfx.no_encoder")); return
        }
        encoder.setRenderPipelineState(pipeline)
        encoder.setFragmentTexture(metalTexture, index: 0)
        encoder.drawPrimitives(type: .triangleStrip, vertexStart: 0, vertexCount: 4)
        encoder.endEncoding()
        command.present(drawable)
        // Keep the IOSurface and its texture alive until the GPU completes this submission.
        command.addCompletedHandler { [weak self] completed in
            _ = buffer; _ = texture
            let failure = completed.status == .error ? (completed.error?.localizedDescription ?? L10n.t("gfx.draw_failed")) : nil
            DispatchQueue.main.async {
                guard let self else { return }
                if let failure { self.reportError?(failure) }
                else if !self.displayFailed { self.statusLabel.isHidden = true; self.onRendered?() }
            }
        }
        command.commit()
    }
    func mtkView(_ view: MTKView, drawableSizeWillChange size: CGSize) {
        requestGuestResize()
    }
    func requestGuestResize() {
        guard bounds.width >= 320, bounds.height >= 320 else { return }
        resizeWork?.cancel()
        // Keep Android at window-point resolution rather than doubling both axes
        // for Retina, which quadruples this uncompressed transport's byte rate.
        let scale = min(1, 1280 / max(bounds.width, bounds.height))
        let width = min(1280, max(320, Int(bounds.width * scale)))
        let height = min(1280, max(320, Int(bounds.height * scale)))
        let density = min(640, max(100, Int(CGFloat(baseDPI) * scale)))
        let work = DispatchWorkItem { [weak self] in self?.resizeDisplay?(width, height, density) }
        resizeWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2, execute: work)
    }
    private func point(_ event: NSEvent) -> (Double, Double) {
        let p = convert(event.locationInWindow, from: nil)
        return (Double(p.x / max(1, bounds.width)) * Double(guestWidth),
                Double(p.y / max(1, bounds.height)) * Double(guestHeight))
    }
    private func pointer(_ event: NSEvent, action: Int) {
        let (x, y) = point(event); control?(["type": "pointer", "action": action, "x": x, "y": y])
    }
    override func mouseDown(with event: NSEvent) { window?.makeFirstResponder(self); pointer(event, action: 0) }
    override func mouseDragged(with event: NSEvent) { pointer(event, action: 2) }
    override func mouseUp(with event: NSEvent) { pointer(event, action: 1) }
    override func rightMouseDown(with event: NSEvent) { keyPair(4) }
    override func scrollWheel(with event: NSEvent) {
        let (x, y) = point(event)
        control?(["type": "scroll", "x": x, "y": y, "dx": -event.scrollingDeltaX / 12, "dy": event.scrollingDeltaY / 12])
    }
    private let specialKeys: [UInt16: Int] = [36: 66, 51: 67, 48: 61, 53: 4, 123: 21, 124: 22, 125: 20, 126: 19, 117: 112]
    private func keyPair(_ code: Int, meta: Int = 0) {
        control?(["type": "key", "code": code, "action": 0, "meta": meta])
        control?(["type": "key", "code": code, "action": 1, "meta": meta])
    }
    override func keyDown(with event: NSEvent) {
        if event.modifierFlags.contains(.command), let char = event.charactersIgnoringModifiers?.lowercased() {
            if char == "v", let text = NSPasteboard.general.string(forType: .string) { control?(["type": "text", "text": text]); return }
            if let code = ["a": 29, "c": 31, "x": 52, "z": 54][char] {
                keyPair(code, meta: 4096)
                if char == "c" || char == "x" {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) { [weak self] in self?.control?(["type": "clipboard-get"]) }
                }
                return
            }
        }
        if let code = specialKeys[event.keyCode] { keyPair(code, meta: event.modifierFlags.contains(.shift) ? 1 : 0) }
        else { interpretKeyEvents([event]) }
    }
    // NSTextInputClient lets macOS input methods compose Unicode text locally.
    func insertText(_ string: Any, replacementRange: NSRange) {
        let text = (string as? NSAttributedString)?.string ?? string as? String ?? ""
        marked = NSAttributedString(string: "")
        if !text.isEmpty { control?(["type": "text", "text": text]) }
    }
    func setMarkedText(_ string: Any, selectedRange: NSRange, replacementRange: NSRange) {
        marked = (string as? NSAttributedString) ?? NSAttributedString(string: string as? String ?? "")
    }
    func unmarkText() { marked = NSAttributedString(string: "") }
    func selectedRange() -> NSRange { NSRange(location: 0, length: 0) }
    func markedRange() -> NSRange { marked.length > 0 ? NSRange(location: 0, length: marked.length) : NSRange(location: NSNotFound, length: 0) }
    func hasMarkedText() -> Bool { marked.length > 0 }
    func validAttributesForMarkedText() -> [NSAttributedString.Key] { [] }
    func attributedSubstring(forProposedRange range: NSRange, actualRange: NSRangePointer?) -> NSAttributedString? { nil }
    func firstRect(forCharacterRange range: NSRange, actualRange: NSRangePointer?) -> NSRect {
        guard let window else { return .zero }
        return window.convertToScreen(convert(NSRect(x: 10, y: max(0, bounds.height - 30), width: 1, height: 20), to: nil))
    }
    func characterIndex(for point: NSPoint) -> Int { 0 }
    override func doCommand(by selector: Selector) {
        if selector == #selector(NSResponder.insertNewline(_:)) { keyPair(66) }
        else if selector == #selector(NSResponder.deleteBackward(_:)) { keyPair(67) }
        else if selector == #selector(NSResponder.insertTab(_:)) { keyPair(61) }
    }
}

final class SurfaceWindowController: NSWindowController, NSWindowDelegate {
    let package: String
    private let transport: SurfaceConnection
    private let surface: SurfaceView
    private var hello: [String: Any] = [:]
    private var started = false
    private var receivedFrame = false
    private var renderedFrame = false
    private var failed = false
    private var firstFrameTimeout: DispatchWorkItem?
    var onClosed: (() -> Void)?
    var onError: ((String) -> Void)?
    init(app: AndroidApp, session: [String: Any]) throws {
        guard let rawPort = session["port"] as? Int, (1024...65535).contains(rawPort) else {
            throw BridgeFailure(message: L10n.t("gfx.bad_port"))
        }
        package = app.package; transport = SurfaceConnection(port: UInt16(rawPort))
        surface = try SurfaceView(graphicsDevice: MTLCreateSystemDefaultDevice())
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 960, height: 720),
                              styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = app.label; window.minSize = NSSize(width: 360, height: 360)
        window.contentView = surface; window.isReleasedWhenClosed = false; window.center()
        super.init(window: window); window.delegate = self
        surface.control = { [weak transport] command in transport?.send(command) }
        surface.baseDPI = session["dpi"] as? Int ?? 200
        surface.resizeDisplay = { [weak self] width, height, dpi in
            guard let self, self.renderedFrame, !self.failed else { return }
            self.transport.send(["type": "resize", "width": width, "height": height, "dpi": dpi])
        }
        surface.reportError = { [weak self] error in self?.showFailure(error) }
        transport.onFrame = { [weak self] frame in
            guard let self, !self.failed else { return }
            if !self.receivedFrame {
                self.receivedFrame = true
                SurfaceLog.write("\(self.package) first RGBA frame \(frame.width)x\(frame.height)")
                self.surface.showStatus(L10n.t("gfx.drawing"))
            }
            self.surface.present(frame)
        }
        surface.onRendered = { [weak self] in
            guard let self, !self.renderedFrame, !self.failed else { return }
            self.renderedFrame = true; self.firstFrameTimeout?.cancel()
            SurfaceLog.write("\(self.package) first Metal render completed")
            self.surface.requestGuestResize()
        }
        transport.onEvent = { [weak self] event in
            if event["event"] as? String == "clipboard", let text = event["text"] as? String {
                NSPasteboard.general.clearContents(); NSPasteboard.general.setString(text, forType: .string)
            }
            if event["event"] as? String == "ready", let self, !self.failed {
                SurfaceLog.write("\(self.package) Guest display ready: \(event["display"] ?? "unknown")")
                if !self.receivedFrame { self.surface.showStatus(L10n.t("gfx.waiting")) }
            }
            if event["event"] as? String == "error" || event["event"] as? String == "input-warning" {
                let message = event["message"] as? String ?? L10n.t("gfx.bridge_error")
                if event["event"] as? String == "error" { self?.showFailure(message) }
                else { self?.onError?(message) }
            }
        }
        transport.onError = { [weak self] message in self?.showFailure(message) }
        hello = session; hello["type"] = "hello"; hello["package"] = app.package
    }
    func startStreaming() {
        guard !started else { return }
        started = true
        SurfaceLog.write("\(package) starting RGBA transport")
        armFirstFrameTimeout()
        transport.start(hello)
    }
    private func armFirstFrameTimeout() {
        firstFrameTimeout?.cancel()
        let timeout = DispatchWorkItem { [weak self] in
            guard let self, !self.renderedFrame, !self.failed, self.window?.isMiniaturized != true else { return }
            let message = self.receivedFrame ? L10n.t("gfx.timeout_drawn")
                : L10n.t("gfx.timeout_wait")
            self.showFailure(message)
        }
        firstFrameTimeout = timeout
        DispatchQueue.main.asyncAfter(deadline: .now() + 20, execute: timeout)
    }
    private func showFailure(_ message: String) {
        guard !failed else { return }
        failed = true; firstFrameTimeout?.cancel()
        SurfaceLog.write("\(package) ERROR: \(message)")
        surface.showFailureMessage(message); onError?(message); transport.close()
    }
    required init?(coder: NSCoder) { fatalError("Storyboard initialization is unsupported") }
    func windowDidBecomeKey(_ notification: Notification) { transport.send(["type": "focus"]); surface.draw() }
    func windowDidMiniaturize(_ notification: Notification) { transport.send(["type": "visibility", "visible": false]) }
    func windowDidDeminiaturize(_ notification: Notification) {
        transport.send(["type": "visibility", "visible": true])
        if !renderedFrame && !failed { armFirstFrameTimeout() }
        surface.draw()
    }
    func windowWillClose(_ notification: Notification) { firstFrameTimeout?.cancel(); transport.close(); onClosed?() }
}
