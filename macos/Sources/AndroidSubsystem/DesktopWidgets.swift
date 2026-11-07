import SwiftUI
import AppKit

struct AndroidWidgetProvider: Identifiable {
    var id: String { provider }
    let provider: String
    let label: String
    let package: String
    let minimumWidth: Int
    let minimumHeight: Int
    let resizeMode: Int
    let configure: Bool
    var supportsDesktopSize: Bool { minimumWidth <= 1280 && minimumHeight <= 1280 }

    init?(_ row: [String: Any]) {
        guard let provider = row["provider"] as? String, !provider.isEmpty else { return nil }
        self.provider = provider
        package = row["package"] as? String ?? provider.components(separatedBy: "/").first ?? provider
        label = row["label"] as? String ?? package
        resizeMode = row["resize_mode"] as? Int ?? 0
        let width = max(64, row["min_width_dp"] as? Int ?? 160)
        let height = max(64, row["min_height_dp"] as? Int ?? 100)
        let resizeWidth = row["min_resize_width_dp"] as? Int ?? 0
        let resizeHeight = row["min_resize_height_dp"] as? Int ?? 0
        minimumWidth = resizeMode & 1 == 1 && resizeWidth > 0 ? max(64, resizeWidth) : width
        minimumHeight = resizeMode & 2 == 2 && resizeHeight > 0 ? max(64, resizeHeight) : height
        configure = row["has_configuration"] as? Bool ?? false
    }
}

struct AndroidDesktopWidget: Identifiable {
    let id: Int
    let provider: String
    let label: String
    let width: Int
    let height: Int

    init?(_ row: [String: Any]) {
        guard let id = row["id"] as? Int, id > 0, let provider = row["provider"] as? String else { return nil }
        self.id = id
        self.provider = provider
        label = row["label"] as? String ?? provider
        width = row["width_dp"] as? Int ?? 240
        height = row["height_dp"] as? Int ?? 160
    }
}

/// Retains live widget surfaces independently of the management window.
/// Android persists AppWidget IDs and state; the surface controller saves Mac frames.
@MainActor
final class DesktopWidgetCoordinator: ObservableObject {
    @Published private(set) var providers: [AndroidWidgetProvider] = []
    @Published private(set) var widgets: [AndroidDesktopWidget] = []
    @Published private(set) var visibleIDs = Set<Int>()
    @Published private(set) var loaded = false
    @Published private(set) var isRefreshing = false
    @Published private(set) var error: String?
    private let backend = Backend()
    private var controllers: [Int: SurfaceWindowController] = [:]
    private var hiddenIDs = Set<Int>()
    private var failedIDs = Set<Int>()
    private var programmaticClosures = Set<Int>()
    private var running = false
    private var providersLoaded = false
    private var generation = 0

    func setRunning(_ value: Bool) {
        guard running != value else { return }
        running = value
        generation += 1
        if !value {
            closeAll()
            widgets = []; providers = []; failedIDs = []
            loaded = false; providersLoaded = false; isRefreshing = false; error = nil
        }
    }

    func refresh(loadProviders: Bool = false) async {
        // Never start Android just because the manager or its Widgets panel opens.
        guard running, !isRefreshing else { return }
        let currentGeneration = generation
        isRefreshing = true
        defer { if generation == currentGeneration { isRefreshing = false } }
        do {
            // An explicit picker refresh also upgrades an already-running older bridge.
            // Query providers first; that endpoint installs the current host before inventory.
            if loadProviders {
                let result = try await backend.call("widget-providers")
                guard running, generation == currentGeneration else { return }
                providers = (result["providers"] as? [[String: Any]] ?? []).compactMap(AndroidWidgetProvider.init)
                    .sorted { $0.label.localizedStandardCompare($1.label) == .orderedAscending }
                providersLoaded = true
            }
            let result = try await backend.call("widgets")
            guard running, generation == currentGeneration else { return }
            widgets = (result["widgets"] as? [[String: Any]] ?? []).compactMap(AndroidDesktopWidget.init)
                .sorted { $0.id < $1.id }
            loaded = true
            error = nil
            let activeIDs = Set(widgets.map(\.id))
            for id in Array(controllers.keys) where !activeIDs.contains(id) { closeWindow(id) }
            hiddenIDs.formIntersection(activeIDs)
            failedIDs.formIntersection(activeIDs)
            if !providersLoaded {
                let result = try await backend.call("widget-providers")
                guard running, generation == currentGeneration else { return }
                providers = (result["providers"] as? [[String: Any]] ?? []).compactMap(AndroidWidgetProvider.init)
                    .sorted { $0.label.localizedStandardCompare($1.label) == .orderedAscending }
                providersLoaded = true
            }
            for widget in widgets where controllers[widget.id] == nil && !hiddenIDs.contains(widget.id) && !failedIDs.contains(widget.id) {
                do { try await open(widget, reveal: false) }
                catch {
                    failedIDs.insert(widget.id)
                    self.error = error.localizedDescription
                }
                guard running, generation == currentGeneration else { return }
            }
        } catch {
            if generation == currentGeneration { self.error = error.localizedDescription }
        }
    }

    func add(_ provider: AndroidWidgetProvider, width: Int, height: Int) async throws {
        guard provider.supportsDesktopSize, (provider.minimumWidth...1280).contains(width),
              (provider.minimumHeight...1280).contains(height) else {
            throw BridgeFailure(message: L10n.t("widgets.unsupported_size", provider.minimumWidth, provider.minimumHeight))
        }
        invalidatePendingSessions()
        let result = try await backend.call("add-widget", ["provider": provider.provider, "width_dp": width, "height_dp": height])
        guard let widget = AndroidDesktopWidget(result["widget"] as? [String: Any] ?? result) else {
            throw BridgeFailure(message: L10n.t("widgets.invalid_instance"))
        }
        if !widgets.contains(where: { $0.id == widget.id }) { widgets.append(widget) }
        hiddenIDs.remove(widget.id); failedIDs.remove(widget.id)
        try await open(widget, reveal: true, setup: true)
    }

    func show(_ widget: AndroidDesktopWidget) async throws {
        hiddenIDs.remove(widget.id)
        if failedIDs.remove(widget.id) != nil { closeWindow(widget.id) }
        try await open(widget, reveal: true)
    }

    func configure(_ widget: AndroidDesktopWidget) async throws {
        invalidatePendingSessions()
        closeWindow(widget.id)
        hiddenIDs.remove(widget.id); failedIDs.remove(widget.id)
        try await open(widget, reveal: true, setup: true, configure: true)
    }

    func hide(_ widget: AndroidDesktopWidget) {
        hiddenIDs.insert(widget.id)
        closeWindow(widget.id)
    }

    func remove(_ widget: AndroidDesktopWidget) async throws {
        invalidatePendingSessions()
        _ = try await backend.call("delete-widget", ["id": widget.id])
        closeWindow(widget.id)
        widgets.removeAll { $0.id == widget.id }
        hiddenIDs.remove(widget.id); failedIDs.remove(widget.id)
    }

    func closeAll() {
        // Invalidate sessions still being prepared when Android is stopped.
        invalidatePendingSessions()
        for id in Array(controllers.keys) { closeWindow(id) }
    }

    private func invalidatePendingSessions() {
        generation += 1
        isRefreshing = false
    }

    private func closeWindow(_ id: Int) {
        guard let controller = controllers[id] else { return }
        programmaticClosures.insert(id)
        controller.close()
        controllers.removeValue(forKey: id); visibleIDs.remove(id)
        programmaticClosures.remove(id)
    }

    private func open(_ widget: AndroidDesktopWidget, reveal: Bool, setup: Bool = false, configure: Bool = false) async throws {
        guard running else { return }
        if let controller = controllers[widget.id] {
            if reveal { controller.showWindow(nil); controller.window?.makeKeyAndOrderFront(nil) }
            return
        }
        let currentGeneration = generation
        var session = try await backend.call(configure ? "configure-widget" : "widget-session", ["id": widget.id])
        guard running, generation == currentGeneration, !hiddenIDs.contains(widget.id),
              widgets.contains(where: { $0.id == widget.id }) else { return }
        // A restore and a Show action may have awaited the same widget concurrently.
        if let controller = controllers[widget.id] {
            if reveal { controller.showWindow(nil); controller.window?.makeKeyAndOrderFront(nil) }
            return
        }
        session["widget_setup"] = setup || (session["widget_setup"] as? Bool ?? false)
        let app = AndroidApp(["package": session["package"] as? String ?? "dev.dan.androidsubsystem", "label": widget.label])
        let controller = try SurfaceWindowController(app: app, session: session, desktopWidgetID: widget.id)
        controller.onClosed = { [weak self, weak controller] in
            guard let self, self.controllers[widget.id] === controller else { return }
            self.controllers.removeValue(forKey: widget.id)
            self.visibleIDs.remove(widget.id)
            if !self.programmaticClosures.contains(widget.id) { self.hiddenIDs.insert(widget.id) }
        }
        controller.onError = { [weak self, weak controller] message in
            guard let self, self.controllers[widget.id] === controller else { return }
            self.failedIDs.insert(widget.id)
            self.error = message
        }
        controllers[widget.id] = controller
        visibleIDs.insert(widget.id)
        controller.showWindow(nil)
        if reveal { controller.window?.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true) }
        controller.startStreaming()
    }
}

struct DesktopWidgetsView: View {
    @EnvironmentObject var model: SubsystemModel
    @ObservedObject var coordinator: DesktopWidgetCoordinator
    @CompatibleState<String> private var selectedProvider = ""
    @CompatibleState<Int> private var width = 240
    @CompatibleState<Int> private var height = 160

    private var provider: AndroidWidgetProvider? { coordinator.providers.first { $0.id == selectedProvider } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(model.t("widgets.title")).font(.largeTitle.bold())
                        Text(model.t("widgets.subtitle")).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button(model.t("nav.refresh"), systemImage: "arrow.clockwise") { model.refreshWidgets() }
                        .disabled(model.busy || coordinator.isRefreshing || model.state != "running")
                }
                Text(model.t("widgets.runtime_hint")).font(.callout).foregroundStyle(.secondary)
                if model.state != "running" {
                    ContentUnavailableView {
                        Label(model.t("widgets.stopped_title"), systemImage: "rectangle.3.group")
                    } description: { Text(model.t("widgets.stopped_body")) }
                    actions: { Button(model.t("lib.boot", model.android)) { model.boot() }.disabled(model.busy) }
                } else {
                    if let error = coordinator.error {
                        Text(error).font(.callout).foregroundStyle(.orange).textSelection(.enabled)
                    }
                    if !coordinator.loaded || coordinator.isRefreshing && coordinator.providers.isEmpty {
                        ProgressView(model.t("widgets.loading")).frame(maxWidth: .infinity).padding()
                    } else {
                        providerPicker
                        installedWidgets
                    }
                }
            }.padding(28)
        }
        .task { await coordinator.refresh(loadProviders: true); selectFirstProvider() }
        .onChange(of: coordinator.providers.map(\.id)) { _, _ in selectFirstProvider() }
        .onChange(of: selectedProvider) { _, _ in
            width = min(1280, max(240, provider?.minimumWidth ?? 64))
            height = min(1280, max(160, provider?.minimumHeight ?? 64))
        }
        .onChange(of: provider?.minimumWidth) { _, minimum in width = min(1280, max(width, minimum ?? 64)) }
        .onChange(of: provider?.minimumHeight) { _, minimum in height = min(1280, max(height, minimum ?? 64)) }
    }

    private var providerPicker: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 14) {
                Text(model.t("widgets.add_title")).font(.title2.bold())
                if coordinator.providers.isEmpty {
                    Text(model.t("widgets.no_providers")).foregroundStyle(.secondary)
                } else {
                    Picker(model.t("widgets.provider"), selection: $selectedProvider) {
                        ForEach(coordinator.providers) { provider in
                            Text("\(provider.label) · \(provider.package)").tag(provider.id)
                        }
                    }
                    HStack(spacing: 20) {
                        Stepper(model.t("widgets.width", width), value: $width,
                                in: min(1280, provider?.minimumWidth ?? 64)...1280, step: 20)
                        Stepper(model.t("widgets.height", height), value: $height,
                                in: min(1280, provider?.minimumHeight ?? 64)...1280, step: 20)
                    }.disabled(provider?.supportsDesktopSize != true)
                    Button(model.t("widgets.add"), systemImage: "plus") {
                        if let provider { model.addWidget(provider, width: width, height: height) }
                    }.buttonStyle(.borderedProminent)
                        .disabled(model.busy || coordinator.isRefreshing || provider?.supportsDesktopSize != true)
                    if let provider, !provider.supportsDesktopSize {
                        Text(model.t("widgets.unsupported_size", provider.minimumWidth, provider.minimumHeight))
                            .font(.caption).foregroundStyle(.orange)
                    }
                    Text(model.t("widgets.setup_hint")).font(.caption).foregroundStyle(.secondary)
                }
            }.frame(maxWidth: .infinity, alignment: .leading).padding(8)
        }
    }

    private var installedWidgets: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 14) {
                Text(model.t("widgets.installed_title")).font(.title2.bold())
                if coordinator.widgets.isEmpty {
                    Text(model.t("widgets.empty")).foregroundStyle(.secondary)
                } else {
                    ForEach(coordinator.widgets) { widget in
                        Divider()
                        HStack(alignment: .top, spacing: 12) {
                            Image(systemName: "rectangle.3.group").font(.title2).padding(.top, 2)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(widget.label).font(.headline)
                                Text(widget.provider).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                                Text(model.t(coordinator.visibleIDs.contains(widget.id) ? "widgets.visible" : "widgets.hidden"))
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Button(model.t("widgets.show")) { model.showWidget(widget) }
                            Menu {
                                if coordinator.visibleIDs.contains(widget.id) {
                                    Button(model.t("widgets.hide")) { coordinator.hide(widget) }
                                }
                                if coordinator.providers.first(where: { $0.provider == widget.provider })?.configure == true {
                                    Button(model.t("widgets.configure")) { model.configureWidget(widget) }
                                }
                                Divider()
                                Button(model.t("widgets.remove"), role: .destructive) { model.removeWidget(widget) }
                            } label: { Image(systemName: "ellipsis") }.menuStyle(.borderlessButton).frame(width: 22)
                        }.disabled(model.busy || coordinator.isRefreshing)
                    }
                }
                Text(model.t("widgets.desktop_hint")).font(.caption).foregroundStyle(.secondary)
            }.frame(maxWidth: .infinity, alignment: .leading).padding(8)
        }
    }

    private func selectFirstProvider() {
        if !coordinator.providers.contains(where: { $0.id == selectedProvider }) {
            selectedProvider = coordinator.providers.first?.id ?? ""
        }
    }
}
