import SwiftUI
import AppKit
import UniformTypeIdentifiers
import UserNotifications

// Keep the property wrapper usable when a Command Line Tools SDK also exports
// a same-named State macro without shipping its SwiftUIMacros plugin.
typealias CompatibleState<Value> = SwiftUI.State<Value>

struct AndroidApp: Identifiable {
    var id: String { package }
    let package: String
    let label: String
    let icon: NSImage?
    init(_ row: [String: Any]) {
        package = row["package"] as? String ?? ""
        label = row["label"] as? String ?? package
        if let encoded = row["icon"] as? String, let data = Data(base64Encoded: encoded) {
            icon = NSImage(data: data)
        } else { icon = nil }
    }
}

struct BridgeFailure: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

final class Backend {
    func call(_ action: String, _ params: [String: Any] = [:]) async throws -> [String: Any] {
        // JSON is passed as a process argument, never interpolated into a shell command.
        let request = try JSONSerialization.data(withJSONObject: params)
        let encoded = String(decoding: request, as: UTF8.self)
        guard let resources = Bundle.main.resourceURL else {
            throw BridgeFailure(message: L10n.t("err.missing_resources"))
        }
        let script = resources.appendingPathComponent("backend/subsystem.py")
        guard FileManager.default.fileExists(atPath: script.path) else {
            throw BridgeFailure(message: L10n.t("err.missing_controller"))
        }
        let preferred = UserDefaults.standard.string(forKey: "pythonPath")
        let bundledPython = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/AndroidSubsystem/runtime/python/bin/python3").path
        let python = [preferred, bundledPython, "/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"]
            .compactMap { $0 }.first { FileManager.default.isExecutableFile(atPath: $0) }
        guard let python else { throw BridgeFailure(message: L10n.t("err.missing_python")) }
        return try await Task.detached(priority: .userInitiated) {
            try Self.runController(python: python, script: script, action: action, encoded: encoded)
        }.value
    }

    // The subprocess and pipe reads are synchronous work performed by the
    // detached task, outside the main actor and the async function body.
    private static func runController(python: String, script: URL, action: String,
                                      encoded: String) throws -> [String: Any] {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: python)
        process.arguments = [script.path, action, encoded]
        let output = Pipe()
        let errors = Pipe()
        process.standardOutput = output
        process.standardError = errors
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        process.environment = env
        try process.run()
        // Read stderr concurrently so neither pipe can block the child process.
        let errorBox = DataBox()
        let group = DispatchGroup()
        group.enter()
        DispatchQueue.global().async {
            errorBox.data = errors.fileHandleForReading.readDataToEndOfFile()
            group.leave()
        }
        let data = output.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        group.wait()
        guard let response = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            let detail = String(decoding: errorBox.data, as: UTF8.self)
            throw BridgeFailure(message: detail.isEmpty ? L10n.t("err.controller_empty") : String(detail.suffix(3000)))
        }
        guard response["ok"] as? Bool == true else {
            throw BridgeFailure(message: response["error"] as? String ?? L10n.t("err.operation_failed"))
        }
        return response["data"] as? [String: Any] ?? [:]
    }
}

final class DataBox: @unchecked Sendable { var data = Data() }

@MainActor
final class SubsystemModel: ObservableObject {
    @Published var apps: [AndroidApp] = []
    @Published var windows: Set<String> = []
    @Published var state = "unavailable"
    @Published var android = 16
    @Published var busy = false
    @Published var progress = ""
    @Published var error: String?
    @Published var search = ""
    @Published var config: [String: Any] = [:]
    @Published var checks: [[String: Any]] = []
    @Published var files: [String] = []
    @Published var notificationsEnabled = UserDefaults.standard.bool(forKey: "forwardNotifications")
    @Published var logsPath = ""
    /// Remembered UI language preference: system | zh | en. Changing it refreshes SwiftUI.
    @Published var uiLang: String = L10n.preference().rawValue
    let backend = Backend()
    private var polling = false
    private var seenEvents = Set<String>()
    private var notificationStart = Date().timeIntervalSince1970 * 1000
    private var timer: Timer?
    private var surfaceWindows: [String: SurfaceWindowController] = [:]
    private var queuedOperations: [(String, () async throws -> Void)] = []

    var filteredApps: [AndroidApp] {
        apps.filter { search.isEmpty || $0.label.localizedCaseInsensitiveContains(search) ||
            $0.package.localizedCaseInsensitiveContains(search) }
    }
    var stateLabel: String {
        _ = uiLang
        switch state {
        case "running": return L10n.t("state.running")
        case "booting": return L10n.t("state.booting")
        case "stopped": return L10n.t("state.stopped")
        default: return L10n.t("state.unavailable")
        }
    }
    /// UI string; depends on `uiLang` so SwiftUI refreshes when language changes.
    func t(_ key: String) -> String {
        _ = uiLang
        return L10n.t(key)
    }
    func t(_ key: String, _ a0: CVarArg) -> String {
        _ = uiLang
        return L10n.t(key, a0)
    }
    func t(_ key: String, _ a0: CVarArg, _ a1: CVarArg) -> String {
        _ = uiLang
        return L10n.t(key, a0, a1)
    }
    func setUiLang(_ raw: String) {
        let pref = UiLangPref(rawValue: raw) ?? .system
        L10n.setPreference(pref)
        uiLang = pref.rawValue
    }

    func beginPolling() {
        guard timer == nil else { return }
        Task { await refresh(reportErrors: false) }
        timer = Timer.scheduledTimer(withTimeInterval: 4, repeats: true) { [weak self] _ in
            Task { @MainActor in await self?.poll() }
        }
    }
    func operation(_ text: String, work: @escaping () async throws -> Void) {
        if busy {
            if queuedOperations.count < 128 { queuedOperations.append((text, work)) }
            else { error = L10n.t("err.queue_full") }
            return
        }
        busy = true; progress = text
        Task {
            do { try await work() } catch { self.error = error.localizedDescription }
            await refresh(reportErrors: false)
            busy = false; progress = ""
            if !queuedOperations.isEmpty {
                let next = queuedOperations.removeFirst()
                operation(next.0, work: next.1)
            }
        }
    }
    func applyStatus(_ response: [String: Any]) {
        let old = state
        state = response["state"] as? String ?? "unavailable"
        android = response["android"] as? Int ?? 16
        config = response["config"] as? [String: Any] ?? [:]
        logsPath = response["logs"] as? String ?? ""
        windows = Set((response["windows"] as? [String: Any] ?? [:]).keys).union(surfaceWindows.keys)
        if old == "running" && state != "running" { apps = []; files = [] }
    }
    func refresh(reportErrors: Bool = true) async {
        do {
            applyStatus(try await backend.call("status"))
            if state == "running" {
                let result = try await backend.call("apps")
                apps = (result["apps"] as? [[String: Any]] ?? []).map(AndroidApp.init)
                    .sorted { $0.label.localizedStandardCompare($1.label) == .orderedAscending }
            }
        } catch { if reportErrors { self.error = error.localizedDescription } }
    }
    func poll() async {
        guard !busy && !polling else { return }
        polling = true
        defer { polling = false }
        do {
            applyStatus(try await backend.call("status"))
            if state == "running" && apps.isEmpty { await refresh(reportErrors: false) }
            if state == "running" && notificationsEnabled { await pollNotifications() }
        } catch { /* Explicit operations show errors; background polls remain quiet. */ }
    }
    func boot() {
        operation(L10n.t("prog.boot", android)) {
            _ = try await self.backend.call("boot")
            await self.installCompanionIfPresent()
        }
    }
    func stop() {
        operation(L10n.t("prog.stop")) {
            for controller in Array(self.surfaceWindows.values) { controller.close() }
            _ = try await self.backend.call("stop")
        }
    }
    func launch(_ app: AndroidApp) {
        if let controller = surfaceWindows[app.package] { controller.showWindow(nil); controller.window?.makeKeyAndOrderFront(nil); return }
        operation(L10n.t("prog.open", app.label)) {
            if let existing = self.surfaceWindows[app.package] { existing.showWindow(nil); return }
            let session = try await self.backend.call("native-session", ["package": app.package])
            try self.openSurface(app, session: session)
        }
    }
    private func openSurface(_ app: AndroidApp, session: [String: Any]) throws {
        let controller = try SurfaceWindowController(app: app, session: session)
        controller.onClosed = { [weak self] in
            self?.surfaceWindows.removeValue(forKey: app.package)
            self?.windows.remove(app.package)
        }
        controller.onError = { [weak self] error in self?.error = error }
        surfaceWindows[app.package] = controller
        windows.insert(app.package)
        controller.showWindow(nil); controller.window?.makeKeyAndOrderFront(nil)
        controller.startStreaming()
        NSApp.activate(ignoringOtherApps: true)
    }
    func launchPackage(_ package: String) {
        let app = apps.first { $0.package == package } ?? AndroidApp(["package": package, "label": package])
        launch(app)
    }
    func close(_ app: AndroidApp) {
        if let controller = surfaceWindows[app.package] { controller.close(); return }
        operation(L10n.t("prog.close", app.label)) { _ = try await self.backend.call("close", ["package": app.package]) }
    }
    func installCompanionIfPresent() async {
        guard let apk = Bundle.main.resourceURL?.appendingPathComponent("MacBridge.apk"),
              FileManager.default.fileExists(atPath: apk.path) else { return }
        do { _ = try await backend.call("install", ["files": [apk.path]]) }
        catch { self.error = L10n.t("err.bridge_install", error.localizedDescription) }
    }
    func install(_ urls: [URL]) {
        operation(L10n.t("prog.install")) {
            _ = try await self.backend.call("install", ["files": urls.map(\.path)])
            await self.installCompanionIfPresent()
        }
    }
    func chooseAPKs() {
        let panel = NSOpenPanel()
        panel.title = L10n.t("panel.install_apk")
        panel.allowedContentTypes = [UTType(filenameExtension: "apk") ?? .data]
        panel.allowsMultipleSelection = true
        if panel.runModal() == .OK { install(panel.urls) }
    }
    func uninstall(_ app: AndroidApp) {
        let alert = NSAlert()
        alert.messageText = L10n.t("alert.uninstall_title", app.label)
        alert.informativeText = L10n.t("alert.uninstall_body")
        alert.addButton(withTitle: L10n.t("alert.uninstall")); alert.addButton(withTitle: L10n.t("alert.cancel"))
        if alert.runModal() == .alertFirstButtonReturn {
            surfaceWindows[app.package]?.close()
            operation(L10n.t("prog.uninstall")) { _ = try await self.backend.call("uninstall", ["package": app.package]) }
        }
    }
    func importFiles() {
        let panel = NSOpenPanel(); panel.allowsMultipleSelection = true
        panel.title = L10n.t("panel.import_files")
        if panel.runModal() == .OK {
            operation(L10n.t("prog.import")) {
                _ = try await self.backend.call("push", ["files": panel.urls.map(\.path)])
                await self.loadFiles()
            }
        }
    }
    func loadFiles() async {
        do { files = try await backend.call("files")["files"] as? [String] ?? [] }
        catch { self.error = error.localizedDescription }
    }
    func exportFile(_ remote: String) {
        let panel = NSOpenPanel(); panel.canChooseFiles = false; panel.canChooseDirectories = true
        panel.title = L10n.t("panel.export_dest")
        if panel.runModal() == .OK, let url = panel.url {
            operation(L10n.t("prog.export")) {
                _ = try await self.backend.call("pull", ["remote": remote, "destination": url.path])
            }
        }
    }
    func exportLauncher(_ app: AndroidApp) {
        let panel = NSOpenPanel(); panel.canChooseFiles = false; panel.canChooseDirectories = true
        panel.canCreateDirectories = true; panel.title = L10n.t("panel.save_launcher")
        panel.directoryURL = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Applications")
        if panel.runModal() == .OK, let url = panel.url {
            operation(L10n.t("prog.launcher")) {
                let result = try await self.backend.call("export-launcher", ["package": app.package,
                    "label": app.label, "app_path": Bundle.main.bundleURL.path, "destination": url.path])
                if let path = result["launcher"] as? String {
                    NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
                }
            }
        }
    }
    func diagnose() {
        operation(L10n.t("prog.diagnose")) {
            let result = try await self.backend.call("diagnostic")
            self.checks = result["checks"] as? [[String: Any]] ?? []
        }
    }
    func saveConfiguration(android: Int, memory: Int, cores: Int, fps: Int) {
        operation(L10n.t("prog.save_config")) {
            _ = try await self.backend.call("configure", ["android": android, "memory_mb": memory,
                                                        "cores": cores, "fps": fps])
        }
    }
    func showLogs() {
        if !logsPath.isEmpty { NSWorkspace.shared.open(URL(fileURLWithPath: logsPath)) }
    }
    func setNotifications(_ enabled: Bool) {
        notificationsEnabled = enabled
        UserDefaults.standard.set(enabled, forKey: "forwardNotifications")
        notificationStart = Date().timeIntervalSince1970 * 1000
        if enabled {
            UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, error in
                Task { @MainActor in
                    if !granted {
                        self.notificationsEnabled = false
                        UserDefaults.standard.set(false, forKey: "forwardNotifications")
                        self.error = error?.localizedDescription ?? L10n.t("err.notify_denied")
                    }
                }
            }
        }
    }
    func pollNotifications() async {
        do {
            let result = try await backend.call("notifications")
            let events = result["notifications"] as? [[String: Any]] ?? []
            for event in events {
                guard let id = event["id"] as? String, !seenEvents.contains(id) else { continue }
                seenEvents.insert(id)
                let stamp = event["timestamp"] as? Double ?? 0
                guard stamp >= notificationStart, let key = event["key"] as? String else { continue }
                if event["removed"] as? Bool == true {
                    UNUserNotificationCenter.current().removeDeliveredNotifications(withIdentifiers: [key])
                    continue
                }
                let content = UNMutableNotificationContent()
                content.title = event["title"] as? String ?? L10n.t("notify.default_title")
                content.body = event["body"] as? String ?? ""
                content.userInfo = ["package": event["package"] as? String ?? ""]
                content.sound = .default
                try await UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: key,
                                                                                      content: content, trigger: nil))
            }
            if seenEvents.count > 500 { seenEvents = Set(events.compactMap { $0["id"] as? String }) }
        } catch { /* Companion may not have notification access yet. */ }
    }
}

struct AppCard: View {
    @EnvironmentObject var model: SubsystemModel
    let app: AndroidApp
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                if let icon = app.icon { Image(nsImage: icon).resizable().frame(width: 48, height: 48) }
                else { Image(systemName: "app.fill").font(.system(size: 40)).foregroundStyle(.green) }
                Spacer()
                if model.windows.contains(app.package) {
                    Circle().fill(.green).frame(width: 8, height: 8).help(model.t("card.window_running"))
                }
            }
            VStack(alignment: .leading, spacing: 5) {
                Text(app.label).font(.headline).lineLimit(1)
                Text(app.package).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            HStack {
                Button(model.windows.contains(app.package) ? model.t("card.show") : model.t("card.open")) { model.launch(app) }
                    .buttonStyle(.borderedProminent).tint(.green)
                    .disabled(model.busy)
                Spacer()
                Menu {
                    if model.windows.contains(app.package) { Button(model.t("card.close_window")) { model.close(app) } }
                    Button(model.t("card.create_launcher")) { model.exportLauncher(app) }
                    Divider()
                    Button(model.t("card.uninstall"), role: .destructive) { model.uninstall(app) }
                } label: { Image(systemName: "ellipsis") }.menuStyle(.borderlessButton).frame(width: 22)
                    .disabled(model.busy)
            }
        }
        .padding(18).background(.background, in: RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(.quaternary))
    }
}

struct LibraryView: View {
    @EnvironmentObject var model: SubsystemModel
    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 8) {
                    Text(model.t("lib.title")).font(.largeTitle.bold())
                    Text(model.t("lib.subtitle", model.android, model.windows.count))
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button(model.t("lib.install_apk"), systemImage: "plus") { model.chooseAPKs() }
                    .buttonStyle(.borderedProminent).disabled(model.busy)
            }
            TextField(model.t("lib.search"), text: $model.search).textFieldStyle(.roundedBorder)
            if model.state != "running" {
                ContentUnavailableView {
                    Label(model.t("lib.not_running_title"), systemImage: "cpu")
                } description: { Text(model.t("lib.not_running_body")) }
                actions: { Button(model.t("lib.boot", model.android)) { model.boot() }.disabled(model.busy) }
            } else if model.apps.isEmpty {
                ContentUnavailableView(model.t("lib.empty_title"), systemImage: "square.grid.2x2", description: Text(model.t("lib.empty_body")))
            } else {
                ScrollView {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 230), spacing: 18)], spacing: 18) {
                        ForEach(model.filteredApps) { AppCard(app: $0) }
                    }.padding(2)
                }
            }
            Spacer(minLength: 0)
        }.padding(28)
    }
}

struct FilesView: View {
    @EnvironmentObject var model: SubsystemModel
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text(model.t("files.title")).font(.largeTitle.bold())
            Text(model.t("files.hint"))
                .foregroundStyle(.secondary)
            HStack {
                Button(model.t("files.import"), systemImage: "arrow.down.doc") { model.importFiles() }
                Button(model.t("files.refresh"), systemImage: "arrow.clockwise") { Task { await model.loadFiles() } }
            }.disabled(model.busy || model.state != "running")
            List(model.files, id: \.self) { path in
                HStack {
                    Image(systemName: "doc")
                    Text(URL(fileURLWithPath: path).lastPathComponent)
                    Spacer()
                    Button(model.t("files.export")) { model.exportFile(path) }.disabled(model.busy)
                }
            }
        }.padding(28).task { if model.state == "running" { await model.loadFiles() } }
    }
}

struct RuntimeView: View {
    @EnvironmentObject var model: SubsystemModel
    @CompatibleState<Int> private var android = 16
    @CompatibleState<Int> private var memory = 4096
    @CompatibleState<Int> private var cores = 4
    @CompatibleState<Int> private var fps = 30
    var body: some View {
        Form {
            Section(model.t("settings.language")) {
                Picker(model.t("settings.language"), selection: Binding(
                    get: { model.uiLang },
                    set: { model.setUiLang($0) }
                )) {
                    Text(model.t("settings.lang.system")).tag(UiLangPref.system.rawValue)
                    Text(model.t("settings.lang.zh")).tag(UiLangPref.zh.rawValue)
                    Text(model.t("settings.lang.en")).tag(UiLangPref.en.rawValue)
                }
                Text(model.t("settings.language_hint"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section(model.t("settings.runtime")) {
                Picker(model.t("settings.android_ver"), selection: $android) {
                    Text("Android 16 · API 36").tag(16)
                    Text("Android 17 · API 37").tag(17)
                }
                Text(model.t("settings.android_hint"))
                    .font(.caption).foregroundStyle(.secondary)
                Picker(model.t("settings.memory"), selection: $memory) {
                    ForEach([2048, 4096, 6144, 8192, 12288, 16384], id: \.self) { Text("\($0 / 1024) GB").tag($0) }
                }
                Stepper(model.t("settings.cores", cores), value: $cores, in: 2...12)
                Picker(model.t("settings.fps"), selection: $fps) {
                    ForEach([15, 30], id: \.self) { Text("\($0) FPS").tag($0) }
                }
                Button(model.t("settings.save")) { model.saveConfiguration(android: android, memory: memory, cores: cores, fps: fps) }
                    .disabled(model.busy || model.state == "running" || model.state == "booting")
                Text(model.t("settings.config_hint"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section(model.t("settings.notifications")) {
                Toggle(model.t("settings.forward_notify"), isOn: Binding(get: { model.notificationsEnabled }, set: { model.setNotifications($0) }))
                Button(model.t("settings.open_notify")) {
                    model.launchPackage("dev.dan.androidsubsystem")
                }.disabled(model.busy || model.state != "running")
                Text(model.t("settings.notify_hint"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section(model.t("settings.diagnostics")) {
                HStack {
                    Button(model.t("settings.check_env")) { model.diagnose() }.disabled(model.busy)
                    Button(model.t("settings.open_logs")) { model.showLogs() }
                }
                ForEach(Array(model.checks.enumerated()), id: \.offset) { _, check in
                    VStack(alignment: .leading) {
                        Label(check["name"] as? String ?? model.t("settings.check_fallback"), systemImage: check["ok"] as? Bool == true ? "checkmark.circle.fill" : "exclamationmark.triangle")
                            .foregroundStyle(check["ok"] as? Bool == true ? Color.green : Color.orange)
                        Text(check["detail"] as? String ?? "").font(.caption).textSelection(.enabled).foregroundStyle(.secondary)
                    }
                }
            }
        }.formStyle(.grouped)
        .onAppear {
            android = model.android
            memory = model.config["memory_mb"] as? Int ?? 4096
            cores = model.config["cores"] as? Int ?? 4
            fps = min(30, model.config["fps"] as? Int ?? 30)
        }
    }
}

struct MainView: View {
    @EnvironmentObject var model: SubsystemModel
    @CompatibleState<String?> private var section: String? = "apps"
    var body: some View {
        NavigationSplitView {
            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    Image(systemName: "square.stack.3d.up.fill").font(.title2).foregroundStyle(.green)
                    Text(model.t("app.title")).font(.headline)
                }.padding(.horizontal, 16).padding(.top, 22)
                List(selection: $section) {
                    Label(model.t("nav.library"), systemImage: "square.grid.2x2").tag("apps")
                    Label(model.t("nav.files"), systemImage: "folder").tag("files")
                    Label(model.t("nav.settings"), systemImage: "slider.horizontal.3").tag("settings")
                }.listStyle(.sidebar)
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Circle().fill(model.state == "running" ? .green : .secondary).frame(width: 7, height: 7)
                        Text(model.stateLabel).font(.caption)
                    }
                    if model.state == "running" || model.state == "booting" {
                        Button(model.t("nav.stop"), systemImage: "stop.circle") { model.stop() }
                    } else { Button(model.t("nav.start"), systemImage: "play.circle") { model.boot() } }
                }.disabled(model.busy).padding(16)
            }.navigationSplitViewColumnWidth(min: 190, ideal: 220)
        } detail: {
            VStack(spacing: 0) {
                if model.busy {
                    HStack { ProgressView().controlSize(.small); Text(model.progress).font(.callout); Spacer() }
                        .padding(12).background(.green.opacity(0.08))
                }
                switch section {
                case "files": FilesView()
                case "settings": RuntimeView()
                default: LibraryView()
                }
            }.background(Color(nsColor: .windowBackgroundColor))
        }
        .frame(minWidth: 900, minHeight: 620)
        .toolbar {
            Button(model.t("nav.refresh"), systemImage: "arrow.clockwise") {
                model.operation(L10n.t("prog.refresh")) { await model.refresh() }
            }.disabled(model.busy)
        }
        .alert(model.t("alert.failed_title"), isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) {
            Button(model.t("alert.ok"), role: .cancel) { model.error = nil }
            Button(model.t("alert.view_logs")) { model.showLogs(); model.error = nil }
        } message: { Text(model.error ?? "") }
        .onOpenURL { url in
            if url.scheme == "android-subsystem", url.host == "launch",
               let package = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "package" })?.value {
                model.launchPackage(package)
            } else if url.pathExtension.lowercased() == "apk" { model.install([url]) }
        }
        .onDrop(of: [.fileURL], isTargeted: nil) { providers in
            guard !model.busy else { return false }
            // Gather a drop as one transaction so split APKs are installed together.
            let group = DispatchGroup()
            let dropped = URLBox()
            for provider in providers {
                group.enter()
                provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
                    if let data = item as? Data, let url = URL(dataRepresentation: data, relativeTo: nil) {
                        dropped.append(url)
                    } else if let url = item as? URL { dropped.append(url) }
                    group.leave()
                }
            }
            group.notify(queue: .main) {
                let urls = dropped.urls
                if !urls.isEmpty && urls.allSatisfy({ $0.pathExtension.lowercased() == "apk" }) { model.install(urls) }
                else { model.error = L10n.t("err.drop_apk") }
            }
            return true
        }
        .task { model.beginPolling() }
    }
}

final class URLBox: @unchecked Sendable {
    private let lock = NSLock()
    private var values: [URL] = []
    func append(_ url: URL) { lock.lock(); defer { lock.unlock() }; values.append(url) }
    var urls: [URL] { lock.lock(); defer { lock.unlock() }; return values }
}

final class NotificationDelegate: NSObject, UNUserNotificationCenterDelegate {
    var launch: ((String) -> Void)?
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound])
    }
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        if let package = response.notification.request.content.userInfo["package"] as? String {
            DispatchQueue.main.async { self.launch?(package) }
        }
        completionHandler()
    }
}

@main
struct AndroidSubsystemApp: App {
    @StateObject private var model = SubsystemModel()
    private let notificationDelegate = NotificationDelegate()
    var body: some Scene {
        WindowGroup(model.t("app.title")) {
            MainView().environmentObject(model).onAppear {
                notificationDelegate.launch = { package in model.launchPackage(package) }
                UNUserNotificationCenter.current().delegate = notificationDelegate
            }
        }
        .commands {
            CommandGroup(after: .newItem) {
                Button(model.t("lib.install_apk")) { model.chooseAPKs() }.keyboardShortcut("i", modifiers: .command).disabled(model.busy)
            }
        }
        MenuBarExtra(model.t("app.title"), systemImage: "square.stack.3d.up") {
            Text("Android \(model.android) · \(model.stateLabel)")
            Divider()
            if model.state == "running" {
                ForEach(model.apps.prefix(15)) { app in Button(app.label) { model.launch(app) }.disabled(model.busy) }
                Divider()
                Button(model.t("nav.stop")) { model.stop() }.disabled(model.busy)
            } else { Button(model.t("nav.start")) { model.boot() }.disabled(model.busy) }
            Button(model.t("menu.show_window")) { NSApp.activate(ignoringOtherApps: true); NSApp.windows.first?.makeKeyAndOrderFront(nil) }
            Button(model.t("menu.quit")) { NSApp.terminate(nil) }
        }
    }
}
