import AppKit
import SwiftUI

/// Files the controller treats as "the Android runtime is on this Mac".
enum RuntimePresence {
    static var root: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/AndroidSubsystem")
    }
    static var isInstalled: Bool {
        let root = root
        let fm = FileManager.default
        return fm.isExecutableFile(atPath: root.appendingPathComponent("sdk/emulator/emulator").path)
            && fm.isExecutableFile(atPath: root.appendingPathComponent("runtime/bin/scrcpy").path)
            && fm.fileExists(atPath: root.appendingPathComponent("installed-runtime.json").path)
    }
}

struct SetupFailure: LocalizedError, Sendable {
    let message: String
    var errorDescription: String? { message }
}

/// Collects installer stderr. Progress lines are forwarded; everything else is kept for errors.
final class SetupEvents: @unchecked Sendable {
    private let lock = NSLock()
    private var notes: [String] = []
    private var mirror: String?
    var onProgress: (String) -> Void = { _ in }
    func line(_ line: String) {
        if line.hasPrefix("AERO_MIRROR\t") {
            let code = String(line.dropFirst("AERO_MIRROR\t".count)).trimmingCharacters(in: .whitespacesAndNewlines)
            lock.lock()
            mirror = code
            lock.unlock()
            onProgress(line)
        } else if line.hasPrefix("AERO_PROGRESS\t") {
            onProgress(line)
        } else if !line.isEmpty {
            lock.lock()
            notes.append(line)
            lock.unlock()
        }
    }
    func chosenMirror() -> String? {
        lock.lock()
        defer { lock.unlock() }
        return mirror
    }
    func failureText() -> String {
        lock.lock()
        defer { lock.unlock() }
        let tail = notes.suffix(12).joined(separator: "\n")
        return tail.isEmpty ? L10n.t("setup.failed") : tail
    }
}

enum SetupPhase {
    case intro, license, working, failed
}

@MainActor
final class RuntimeSetupModel: ObservableObject {
    @Published var needed: Bool
    @Published var phase: SetupPhase = .intro
    @Published var fraction: Double?
    @Published var message = ""
    @Published var licenseText = ""
    @Published var mirrorLabel = ""
    @Published var mirrorCode = "auto"
    @Published var error: String?
    @Published var busy = false
    @Published var scriptReady: Bool
    @Published var pythonMissing: Bool
    private var confirmed = false

    init() {
        scriptReady = FileManager.default.fileExists(atPath: Self.scriptURL().path)
        pythonMissing = Self.pythonPath() == nil
        needed = !RuntimePresence.isInstalled
    }

    func recheckTools() {
        pythonMissing = Self.pythonPath() == nil
        scriptReady = FileManager.default.fileExists(atPath: Self.scriptURL().path)
        error = nil
    }

    /// When the runtime files are already present, ask the bundled script whether they match
    /// the pinned fingerprint. A mismatch (an older Android setup) opens the in-app installer.
    func confirmInstalledRuntime() async {
        guard !confirmed else { return }
        confirmed = true
        guard RuntimePresence.isInstalled, scriptReady, Self.pythonPath() != nil else { return }
        do {
            let text = try await launch(["status"])
            guard let data = text.data(using: .utf8),
                  let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
            if json["installed"] as? Bool == false {
                needed = true
                phase = .intro
            }
        } catch {
            // The file check already allowed the main window. A status glitch should not block it.
        }
    }

    func startLicense() {
        guard !busy, scriptReady, !pythonMissing else { return }
        busy = true
        error = nil
        phase = .working
        fraction = nil
        message = L10n.t("setup.checking")
        Task {
            do {
                let text = try await self.launch(["license", "--mirror", "auto"])
                self.licenseText = text.trimmingCharacters(in: .whitespacesAndNewlines)
                if self.licenseText.isEmpty {
                    throw BridgeFailure(message: L10n.t("setup.license_empty"))
                }
                self.rememberMirror()
                self.fraction = nil
                self.phase = .license
            } catch {
                self.error = error.localizedDescription
                self.phase = .failed
            }
            self.busy = false
        }
    }

    func acceptAndInstall() {
        guard !busy, scriptReady, !pythonMissing else { return }
        busy = true
        error = nil
        phase = .working
        fraction = 0
        message = L10n.t("setup.working")
        let mirror = mirrorCode
        Task {
            do {
                _ = try await self.launch(["download", "--mirror", mirror])
                _ = try await self.launch(["install", "--mirror", mirror, "--accept-sdk-license"])
                self.fraction = 1
                self.needed = false
            } catch {
                self.error = error.localizedDescription
                self.phase = .failed
            }
            self.busy = false
        }
    }

    func retry() {
        if licenseText.isEmpty { startLicense() } else { acceptAndInstall() }
    }

    func apply(_ line: String) {
        if line.hasPrefix("AERO_MIRROR\t") {
            let code = String(line.dropFirst("AERO_MIRROR\t".count)).trimmingCharacters(in: .whitespacesAndNewlines)
            if code == "cn" || code == "global" { mirrorCode = code }
            mirrorLabel = code == "cn" ? L10n.t("setup.mirror_cn") : L10n.t("setup.mirror_official")
            return
        }
        guard line.hasPrefix("AERO_PROGRESS\t") else { return }
        let parts = line.components(separatedBy: "\t")
        guard parts.count >= 3, let value = Double(parts[1]) else { return }
        fraction = min(1, max(0, value))
        message = parts.dropFirst(2).joined(separator: " ")
    }

    private var lastEvents: SetupEvents?
    private func rememberMirror() {
        if let code = lastEvents?.chosenMirror(), code == "cn" || code == "global" {
            mirrorCode = code
            mirrorLabel = code == "cn" ? L10n.t("setup.mirror_cn") : L10n.t("setup.mirror_official")
        }
    }
    private func launch(_ args: [String]) async throws -> String {
        let events = SetupEvents()
        lastEvents = events
        events.onProgress = { [weak self] line in
            DispatchQueue.main.async { self?.apply(line) }
        }
        guard let python = Self.pythonPath() else {
            pythonMissing = true
            throw BridgeFailure(message: L10n.t("setup.missing_python"))
        }
        let script = Self.scriptURL().path
        guard FileManager.default.fileExists(atPath: script) else {
            scriptReady = false
            throw BridgeFailure(message: L10n.t("setup.missing_script"))
        }
        return try await Task.detached(priority: .userInitiated) {
            try Self.runProcess(python: python, script: script, arguments: args, events: events)
        }.value
    }

    nonisolated private static func runProcess(python: String, script: String, arguments: [String],
                                                events: SetupEvents) throws -> String {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: python)
        process.arguments = [script] + arguments
        let output = Pipe()
        let errors = Pipe()
        process.standardOutput = output
        process.standardError = errors
        var env = ProcessInfo.processInfo.environment
        env["PYTHONUNBUFFERED"] = "1"
        env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin"
        process.environment = env
        try process.run()
        let group = DispatchGroup()
        group.enter()
        DispatchQueue.global().async {
            Self.consume(errors.fileHandleForReading) { events.line($0) }
            group.leave()
        }
        let data = output.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        group.wait()
        if process.terminationStatus != 0 {
            throw SetupFailure(message: events.failureText())
        }
        return String(decoding: data, as: UTF8.self)
    }

    nonisolated private static func consume(_ handle: FileHandle, onLine: (String) -> Void) {
        var pending = Data()
        while true {
            let chunk = handle.availableData
            if chunk.isEmpty { break }
            pending.append(chunk)
            while let newline = pending.firstIndex(of: 10) {
                let lineData = pending.prefix(upTo: newline)
                pending.removeSubrange(pending.startIndex...newline)
                var line = String(decoding: lineData, as: UTF8.self)
                if line.hasSuffix("\r") { line.removeLast() }
                onLine(line)
            }
        }
        if !pending.isEmpty {
            onLine(String(decoding: pending, as: UTF8.self))
        }
    }

    static func scriptURL() -> URL {
        AppBundle.manager.appendingPathComponent("Contents/Resources/scripts/install-runtime.py")
    }

    static func pythonPath() -> String? {
        ["/usr/bin/python3", "/opt/homebrew/bin/python3", "/usr/local/bin/python3"]
            .first { FileManager.default.isExecutableFile(atPath: $0) }
    }
}

struct RuntimeSetupView: View {
    @EnvironmentObject var setup: RuntimeSetupModel
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .center, spacing: 14) {
                LogoView().frame(width: 48, height: 48)
                VStack(alignment: .leading, spacing: 4) {
                    Text(L10n.t("setup.title")).font(.title2.bold())
                    Text(L10n.t("setup.body")).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
            }
            Text(L10n.t("setup.requirements")).font(.callout).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Text(L10n.t("setup.auto_mirror")).font(.callout).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if !setup.mirrorLabel.isEmpty {
                Text(setup.mirrorLabel).font(.callout)
            }
            if setup.phase == .license {
                Text(L10n.t("setup.license_title")).font(.headline)
                Text(L10n.t("setup.license_body")).font(.callout).foregroundStyle(.secondary)
                ScrollView {
                    Text(setup.licenseText)
                        .font(.caption)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(minHeight: 160, maxHeight: 280)
                .padding(8)
                .background(Color(nsColor: .textBackgroundColor))
                .clipShape(RoundedRectangle(cornerRadius: 8))
            }
            if setup.phase == .working || setup.phase == .failed || setup.fraction != nil {
                progress
            }
            if let error = setup.error {
                Text(error).font(.callout).foregroundStyle(.red).textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }
            controls
            Spacer(minLength: 0)
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .frame(minWidth: 720, minHeight: 520)
    }

    @ViewBuilder private var progress: some View {
        if let fraction = setup.fraction {
            ProgressView(value: fraction, total: 1)
                .progressViewStyle(.linear)
            Text(L10n.t("setup.percent", Int((fraction * 100).rounded())))
                .font(.headline).monospacedDigit()
            Text(setup.message.isEmpty ? L10n.t("setup.working") : setup.message)
                .font(.callout)
        } else {
            HStack(spacing: 8) {
                ProgressView().controlSize(.small)
                Text(setup.message.isEmpty ? L10n.t("setup.checking") : setup.message).font(.callout)
            }
        }
    }

    @ViewBuilder private var controls: some View {
        if !setup.scriptReady {
            Text(L10n.t("setup.missing_script")).font(.callout)
        } else if setup.pythonMissing {
            Text(L10n.t("setup.missing_python")).font(.callout)
            Button(L10n.t("setup.retry")) { setup.recheckTools() }
                .buttonStyle(.borderedProminent)
                .disabled(setup.busy)
        } else {
            switch setup.phase {
            case .intro:
                Button(L10n.t("setup.start")) { setup.startLicense() }
                    .buttonStyle(.borderedProminent)
                    .disabled(setup.busy)
            case .license:
                Button(L10n.t("setup.accept")) { setup.acceptAndInstall() }
                    .buttonStyle(.borderedProminent)
                    .disabled(setup.busy)
            case .working:
                EmptyView()
            case .failed:
                Button(L10n.t("setup.retry")) { setup.retry() }
                    .buttonStyle(.borderedProminent)
                    .disabled(setup.busy)
            }
        }
    }
}
