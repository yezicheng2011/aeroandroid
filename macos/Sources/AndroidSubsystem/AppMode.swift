import AppKit
import UniformTypeIdentifiers

/// The manager app that owns the backend and bridge APK: this bundle, the bundle that
/// created an exported app, or the app that contains the APK installer helper.
enum AppBundle {
    static var manager: URL {
        let info = Bundle.main.infoDictionary
        if let path = info?["SubsystemAppPath"] as? String { return URL(fileURLWithPath: path) }
        if info?["AndroidMode"] as? String == "install" {
            // <manager>.app/Contents/Helpers/APK Installer.app
            return Bundle.main.bundleURL.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        }
        return Bundle.main.bundleURL
    }
}

/// First launch on an Intel Mac: say plainly that some Android apps cannot run here.
enum IntelNotice {
    /// hw.optional.arm64 is 1 on Apple Silicon (also for an x86_64 process under Rosetta) and absent on Intel.
    static var isIntelMac: Bool {
        var value: Int32 = 0
        var size = MemoryLayout<Int32>.size
        return !(sysctlbyname("hw.optional.arm64", &value, &size, nil, 0) == 0 && value == 1)
    }
    @MainActor static func showOnce() {
        guard isIntelMac, !UserDefaults.standard.bool(forKey: "intelNoticeShown") else { return }
        UserDefaults.standard.set(true, forKey: "intelNoticeShown")
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = L10n.t("intel.title")
        alert.informativeText = L10n.t("intel.body")
        alert.addButton(withTitle: L10n.t("alert.ok"))
        NSApp.activate(ignoringOtherApps: true)
        alert.runModal()
    }
}

/// Makes double-clicking an .apk open the installer helper instead of the manager window.
enum ApkHandler {
    private static let contentType = "com.android.package-archive"
    private static let installer = "dev.dan.androidsubsystem.installer"
    static func registerOnce() {
        guard UserDefaults.standard.string(forKey: "apkHandler") != installer else { return }
        let helper = AppBundle.manager.appendingPathComponent("Contents/Helpers/APK Installer.app")
        guard FileManager.default.fileExists(atPath: helper.path) else { return }
        _ = LSRegisterURL(helper as CFURL, true)
        if LSSetDefaultRoleHandlerForContentType(contentType as CFString, .all, installer as CFString) == noErr {
            UserDefaults.standard.set(installer, forKey: "apkHandler")
        }
    }
}

/// Small floating progress window for the two single-purpose modes.
@MainActor
final class StatusPanel {
    private let panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 360, height: 96),
                                styleMask: [.titled], backing: .buffered, defer: false)
    private let label = NSTextField(labelWithString: "")
    private let spinner = NSProgressIndicator()
    init() {
        panel.isFloatingPanel = true; panel.isReleasedWhenClosed = false
        label.frame = NSRect(x: 24, y: 50, width: 312, height: 22); label.lineBreakMode = .byTruncatingTail
        spinner.style = .bar; spinner.isIndeterminate = true
        spinner.frame = NSRect(x: 24, y: 24, width: 312, height: 12)
        panel.contentView?.addSubview(label); panel.contentView?.addSubview(spinner)
    }
    func show(_ text: String) {
        label.stringValue = text; spinner.startAnimation(nil)
        panel.center(); panel.makeKeyAndOrderFront(nil)
    }
    func hide() { spinner.stopAnimation(nil); panel.orderOut(nil) }
}

@MainActor
private var retainedDelegate: NSObject?

@MainActor
private func showAlert(_ title: String, _ error: Error) {
    let alert = NSAlert()
    alert.messageText = title; alert.informativeText = error.localizedDescription
    NSApp.activate(ignoringOtherApps: true)
    alert.runModal()
}

/// Gives a window-less Android app the standard Cmd-W / Cmd-Q / Cmd-H menu.
@MainActor
private func installMenu(appName: String) {
    let menu = NSMenu(), appItem = NSMenuItem(), appMenu = NSMenu()
    appMenu.addItem(withTitle: "Hide \(appName)", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
    appMenu.addItem(withTitle: "Quit \(appName)", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
    appItem.submenu = appMenu; menu.addItem(appItem)
    let windowItem = NSMenuItem(), windowMenu = NSMenu(title: "Window")
    windowMenu.addItem(withTitle: "Minimize", action: #selector(NSWindow.miniaturize(_:)), keyEquivalent: "m")
    windowMenu.addItem(withTitle: "Close", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
    windowItem.submenu = windowMenu; menu.addItem(windowItem)
    NSApp.mainMenu = menu; NSApp.windowsMenu = windowMenu
}

// MARK: - One Android app as a Mac app

@MainActor
func runAndroidApp(package: String) -> Never {
    let name = Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? package
    let delegate = AndroidAppDelegate(AndroidApp(["package": package, "label": name]))
    retainedDelegate = delegate
    NSApplication.shared.delegate = delegate
    NSApp.setActivationPolicy(.regular)
    NSApp.run()
    exit(0)
}

@MainActor
final class AndroidAppDelegate: NSObject, NSApplicationDelegate {
    private let app: AndroidApp
    private let backend = Backend()
    private let splash = StatusPanel()
    private var controller: SurfaceWindowController?
    init(_ app: AndroidApp) { self.app = app }

    func applicationDidFinishLaunching(_ notification: Notification) {
        installMenu(appName: app.label)
        splash.show(L10n.t("app.starting", app.label))
        NSApp.activate(ignoringOtherApps: true)
        Task {
            do {
                // Boots the subsystem when it is not running yet, then opens this app's display.
                let session = try await backend.call("native-session", ["package": app.package])
                let window = try SurfaceWindowController(app: app, session: session)
                window.onClosed = { NSApp.terminate(nil) }
                window.onError = { NSLog("%@: %@", self.app.package, $0) }
                controller = window
                splash.hide()
                window.showWindow(nil); window.window?.makeKeyAndOrderFront(nil)
                window.startStreaming()
                NSApp.activate(ignoringOtherApps: true)
            } catch {
                splash.hide(); showAlert(L10n.t("app.start_failed", app.label), error); NSApp.terminate(nil)
            }
        }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { controller != nil }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        controller?.window?.makeKeyAndOrderFront(nil); return true
    }
}

// MARK: - Double-clicking an .apk

@MainActor
func runInstaller() -> Never {
    let delegate = InstallerDelegate()
    retainedDelegate = delegate
    NSApplication.shared.delegate = delegate
    NSApp.setActivationPolicy(.accessory)
    NSApp.run()
    exit(0)
}

@MainActor
final class InstallerDelegate: NSObject, NSApplicationDelegate {
    private let backend = Backend()
    private let panel = StatusPanel()
    private var urls: [URL] = []
    private var started = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        IntelNotice.showOnce()
        // Opened by double-clicking an .apk, the open-files event arrives right after launch;
        // opened directly, there is nothing to install yet, so ask for a file.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { [self] in
            if urls.isEmpty && !started { choose() }
        }
    }
    func application(_ application: NSApplication, open urls: [URL]) {
        self.urls += urls.filter { $0.pathExtension.lowercased() == "apk" }
        // Finder delivers a multi-file selection in one event; start once it has arrived.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [self] in begin() }
    }
    private func choose() {
        let panel = NSOpenPanel()
        panel.title = L10n.t("install.choose")
        panel.allowedContentTypes = [UTType(filenameExtension: "apk") ?? .data]
        panel.allowsMultipleSelection = true
        NSApp.activate(ignoringOtherApps: true)
        if panel.runModal() == .OK { urls = panel.urls; begin() } else { NSApp.terminate(nil) }
    }
    private func begin() {
        guard !started, !urls.isEmpty else { return }
        started = true
        panel.show(L10n.t("install.working"))
        Task {
            do {
                let applications = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Applications")
                let result = try await backend.call("install-app", ["files": urls.map(\.path),
                    "app_path": AppBundle.manager.path, "destination": applications.path])
                panel.hide()
                if let path = result["launcher"] as? String {
                    _ = try await NSWorkspace.shared.openApplication(at: URL(fileURLWithPath: path),
                                                                     configuration: NSWorkspace.OpenConfiguration())
                }
            } catch {
                panel.hide(); showAlert(L10n.t("install.failed"), error)
            }
            NSApp.terminate(nil)
        }
    }
}
