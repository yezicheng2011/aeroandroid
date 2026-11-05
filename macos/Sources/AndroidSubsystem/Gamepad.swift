import GameController
import SwiftUI

/// Android gamepad key codes a Mac controller button can be mapped to (android.view.KeyEvent).
struct PadChoice: Identifiable {
    let name: String
    let code: Int
    var id: Int { code }
}

enum AndroidPad {
    static let buttons: [PadChoice] = [
        PadChoice(name: "A", code: 96), PadChoice(name: "B", code: 97), PadChoice(name: "C", code: 98),
        PadChoice(name: "X", code: 99), PadChoice(name: "Y", code: 100), PadChoice(name: "Z", code: 101),
        PadChoice(name: "L1", code: 102), PadChoice(name: "R1", code: 103), PadChoice(name: "L2", code: 104),
        PadChoice(name: "R2", code: 105), PadChoice(name: "Thumb L", code: 106), PadChoice(name: "Thumb R", code: 107),
        PadChoice(name: "Start", code: 108), PadChoice(name: "Select", code: 109), PadChoice(name: "Mode", code: 110),
    ]
}

struct PadElement: Identifiable {
    let id: String      // key in GamepadMapping.codes
    let label: String
}

/// Which Android button each Mac controller element presses. Sticks, triggers and the D-pad
/// always drive their Android axes; this table only covers the buttons. Code 0 means "unmapped".
struct GamepadMapping: Codable, Equatable {
    static let elements: [PadElement] = [
        PadElement(id: "a", label: "A / ✕"), PadElement(id: "b", label: "B / ○"),
        PadElement(id: "x", label: "X / □"), PadElement(id: "y", label: "Y / △"),
        PadElement(id: "leftShoulder", label: "LB / L1"), PadElement(id: "rightShoulder", label: "RB / R1"),
        PadElement(id: "leftTrigger", label: "LT / L2"), PadElement(id: "rightTrigger", label: "RT / R2"),
        PadElement(id: "leftThumbstick", label: "L3"), PadElement(id: "rightThumbstick", label: "R3"),
        PadElement(id: "menu", label: "Menu"), PadElement(id: "options", label: "View / Options"),
        PadElement(id: "home", label: "Home"),
    ]
    static let standard = GamepadMapping(codes: [
        "a": 96, "b": 97, "x": 99, "y": 100, "leftShoulder": 102, "rightShoulder": 103,
        "leftTrigger": 104, "rightTrigger": 105, "leftThumbstick": 106, "rightThumbstick": 107,
        "menu": 108, "options": 109, "home": 110,
    ])
    var codes: [String: Int]

    static var enabled: Bool { UserDefaults.standard.object(forKey: "gamepadEnabled") as? Bool ?? true }
    static var current: GamepadMapping {
        guard let raw = UserDefaults.standard.string(forKey: "gamepadMapping"), let data = raw.data(using: .utf8),
              let saved = try? JSONDecoder().decode(GamepadMapping.self, from: data) else { return .standard }
        return saved
    }
    var json: String { String(decoding: (try? JSONEncoder().encode(self)) ?? Data(), as: UTF8.self) }
}

/// Forwards the first connected Mac game controller to one Android app window.
/// Only the key window listens, so several app windows never fight over a controller.
@MainActor
final class GamepadBridge {
    var send: (([String: Any]) -> Void)?
    private var running = false
    private var observers: [NSObjectProtocol] = []
    private var pressed = Set<Int>()
    private var axes: [String: Float] = [:]
    private var lastAxisSend = Date.distantPast
    private var pendingAxes: DispatchWorkItem?

    func start() {
        guard !running, GamepadMapping.enabled else { return }
        running = true
        let center = NotificationCenter.default
        observers = [
            center.addObserver(forName: .GCControllerDidConnect, object: nil, queue: .main) { [weak self] _ in
                MainActor.assumeIsolated { self?.attach() }
            },
            center.addObserver(forName: .GCControllerDidDisconnect, object: nil, queue: .main) { [weak self] _ in
                MainActor.assumeIsolated { self?.release() }
            },
        ]
        attach()
    }

    func stop() {
        guard running else { return }
        running = false
        for observer in observers { NotificationCenter.default.removeObserver(observer) }
        observers = []
        GCController.controllers().forEach { $0.extendedGamepad?.valueChangedHandler = nil }
        release()
    }

    private func attach() {
        guard let pad = GCController.controllers().first?.extendedGamepad else { return }
        // Keep Menu and Home for the game instead of macOS system gestures.
        pad.buttonMenu.preferredSystemGestureState = .disabled
        pad.buttonOptions?.preferredSystemGestureState = .disabled
        pad.buttonHome?.preferredSystemGestureState = .disabled
        pad.valueChangedHandler = { [weak self] gamepad, _ in
            MainActor.assumeIsolated { self?.changed(gamepad) }
        }
        changed(pad)
    }

    /// Let go of every button and centre the sticks, so nothing stays pressed in the game.
    private func release() {
        pendingAxes?.cancel()
        var message: [String: Any] = [:]
        if !pressed.isEmpty { message["keys"] = pressed.sorted().map { [$0, 1] } }
        if axes.values.contains(where: { $0 != 0 }) { message["axes"] = Self.centred }
        pressed = []; axes = [:]
        if !message.isEmpty { send?(message.merging(["type": "gamepad"]) { $1 }) }
    }

    private static let centred: [String: Float] = ["x": 0, "y": 0, "z": 0, "rz": 0, "lt": 0, "rt": 0, "hx": 0, "hy": 0]

    private func changed(_ pad: GCExtendedGamepad) {
        let mapping = GamepadMapping.current.codes
        let buttons: [String: Bool] = [
            "a": pad.buttonA.isPressed, "b": pad.buttonB.isPressed, "x": pad.buttonX.isPressed, "y": pad.buttonY.isPressed,
            "leftShoulder": pad.leftShoulder.isPressed, "rightShoulder": pad.rightShoulder.isPressed,
            "leftTrigger": pad.leftTrigger.value > 0.5, "rightTrigger": pad.rightTrigger.value > 0.5,
            "leftThumbstick": pad.leftThumbstickButton?.isPressed ?? false, "rightThumbstick": pad.rightThumbstickButton?.isPressed ?? false,
            "menu": pad.buttonMenu.isPressed, "options": pad.buttonOptions?.isPressed ?? false, "home": pad.buttonHome?.isPressed ?? false,
        ]
        let now = Set(buttons.compactMap { name, down in down ? mapping[name] : nil }.filter { $0 != 0 })
        let released: [[Int]] = pressed.subtracting(now).sorted().map { [$0, 1] }
        let pushed: [[Int]] = now.subtracting(pressed).sorted().map { [$0, 0] }
        let keys = released + pushed
        pressed = now

        func dead(_ value: Float) -> Float { abs(value) < 0.08 ? 0 : value }   // ignore stick drift
        let next: [String: Float] = [
            "x": dead(pad.leftThumbstick.xAxis.value), "y": -dead(pad.leftThumbstick.yAxis.value),   // Android's Y points down
            "z": dead(pad.rightThumbstick.xAxis.value), "rz": -dead(pad.rightThumbstick.yAxis.value),
            "lt": pad.leftTrigger.value, "rt": pad.rightTrigger.value,
            "hx": pad.dpad.xAxis.value, "hy": -pad.dpad.yAxis.value,
        ]
        let axesChanged = next.contains { abs($0.value - (axes[$0.key] ?? 0)) > 0.005 }
        if !keys.isEmpty { send?(["type": "gamepad", "keys": keys]) }
        if axesChanged { axes = next; sendAxes() }
    }

    /// Sticks can report hundreds of changes a second; cap the rate but never drop the last value.
    private func sendAxes() {
        let wait = 0.008 - Date().timeIntervalSince(lastAxisSend)
        guard wait <= 0 else {
            guard pendingAxes == nil else { return }
            let work = DispatchWorkItem { [weak self] in
                MainActor.assumeIsolated { self?.pendingAxes = nil; self?.sendAxes() }
            }
            pendingAxes = work
            DispatchQueue.main.asyncAfter(deadline: .now() + wait, execute: work)
            return
        }
        lastAxisSend = Date()
        send?(["type": "gamepad", "axes": axes])
    }
}

/// Settings: turn controller support on or off and choose what each button presses.
struct GamepadSettings: View {
    @EnvironmentObject var model: SubsystemModel
    @AppStorage("gamepadEnabled") private var enabled = true
    @AppStorage("gamepadMapping") private var raw = ""
    @CompatibleState<String> private var connected = L10n.t("pad.none")

    private var mapping: GamepadMapping {
        raw.isEmpty ? .standard : (try? JSONDecoder().decode(GamepadMapping.self, from: Data(raw.utf8))) ?? .standard
    }
    var body: some View {
        Section(model.t("pad.title")) {
            Toggle(model.t("pad.enable"), isOn: $enabled)
            Text(model.t("pad.connected", connected)).font(.caption).foregroundStyle(.secondary)
            if enabled {
                ForEach(GamepadMapping.elements) { element in
                    Picker(element.label, selection: Binding(
                        get: { mapping.codes[element.id] ?? 0 },
                        set: { code in var next = mapping; next.codes[element.id] = code; raw = next.json }
                    )) {
                        Text(model.t("pad.unmapped")).tag(0)
                        ForEach(AndroidPad.buttons) { Text($0.name).tag($0.code) }
                    }
                }
                Button(model.t("pad.reset")) { raw = "" }
                Text(model.t("pad.hint")).font(.caption).foregroundStyle(.secondary)
            }
        }
        .onAppear { refresh() }
        .onReceive(NotificationCenter.default.publisher(for: .GCControllerDidConnect)) { _ in refresh() }
        .onReceive(NotificationCenter.default.publisher(for: .GCControllerDidDisconnect)) { _ in refresh() }
    }
    private func refresh() { connected = GCController.controllers().first?.vendorName ?? L10n.t("pad.none") }
}
