import SwiftUI

/// The aeroandroid logo, drawn in SwiftUI so that it follows light and dark mode the way assets/logo.svg does:
/// a letter "a" (ring plus stem) as frosted glass with a soft shadow, trailing three streaks of wind that fade in
/// from nothing, on an app-icon tile. The numbers are the SVG's (scripts/make-logo.py), measured from the tile's
/// top left corner; the tile is 824 units wide.
struct LogoView: View {
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        GeometryReader { proxy in
            drawing(side: min(proxy.size.width, proxy.size.height))
        }
        .aspectRatio(1, contentMode: .fit)
        .accessibilityLabel("aeroandroid")
    }

    private var dark: Bool { scheme == .dark }

    // Light: white glass on a blue-to-mint tile. Dark: an azure-to-mint glow on a deep navy tile with a lit rim.
    private var skyStops: [Gradient.Stop] {
        let colors = dark ? [Color(hex: 0x18223d), Color(hex: 0x0f1730), Color(hex: 0x070c19)]
                          : [Color(hex: 0x3b6bff), Color(hex: 0x18b4f2), Color(hex: 0x25e3b4)]
        return [Gradient.Stop(color: colors[0], location: 0), Gradient.Stop(color: colors[1], location: 0.55),
                Gradient.Stop(color: colors[2], location: 1)]
    }
    private var litColor: Color { dark ? Color(hex: 0x9db8ff) : Color.white }
    private var litAlpha: Double { dark ? 0.16 : 0.26 }
    private var inkColors: [Color] { dark ? [Color(hex: 0x8fb4ff), Color(hex: 0x43e8c4)] : [Color.white, Color.white] }
    private var glassLevel: Double { dark ? 1.0 : 0.84 }
    private var shadowColor: Color { dark ? Color(hex: 0x4da3ff).opacity(0.55) : Color(hex: 0x04206b).opacity(0.3) }
    private var shadowDrop: CGFloat { dark ? 6 : 14 }
    private var shadowBlur: CGFloat { dark ? 40 : 32 }

    private func drawing(side: CGFloat) -> some View {
        let u = side / 824
        return ZStack {
            tile(side: side)
            LinearGradient(colors: inkColors, startPoint: UnitPoint(x: 40 / 824, y: 200 / 824), endPoint: UnitPoint(x: 630 / 824, y: 630 / 824))
                .mask { glyph(side: side) }
                .mask { glassFade }
                .shadow(color: shadowColor, radius: shadowBlur * u, x: 0, y: shadowDrop * u)
        }
        .frame(width: side, height: side)
    }

    private func tile(side: CGFloat) -> some View {
        let u = side / 824
        let shape = RoundedRectangle(cornerRadius: side * 185 / 824, style: .continuous)
        let sky = LinearGradient(stops: skyStops, startPoint: UnitPoint(x: 0.12, y: 0), endPoint: UnitPoint(x: 0.88, y: 1))
        let lit = RadialGradient(colors: [litColor.opacity(litAlpha), litColor.opacity(0)],
                                 center: UnitPoint(x: 0.24, y: 0.06), startRadius: 0, endRadius: side * 0.9)
        return shape.fill(sky)
            .overlay(glows(shape: shape, side: side).opacity(dark ? 1 : 0))
            .overlay(shape.fill(lit))
            .overlay(rim(shape: shape, u: u).opacity(dark ? 1 : 0))
    }

    /// Two soft coloured glows in the corners of the dark tile.
    private func glows(shape: RoundedRectangle, side: CGFloat) -> some View {
        ZStack {
            shape.fill(RadialGradient(colors: [Color(hex: 0x2f6bff).opacity(0.42), Color(hex: 0x2f6bff).opacity(0)],
                                      center: UnitPoint(x: 0.12, y: 1.0), startRadius: 0, endRadius: side * 0.75))
            shape.fill(RadialGradient(colors: [Color(hex: 0x1be0b4).opacity(0.22), Color(hex: 0x1be0b4).opacity(0)],
                                      center: UnitPoint(x: 0.95, y: 0.0), startRadius: 0, endRadius: side * 0.75))
        }
    }

    /// The thin lit edge of the dark tile.
    private func rim(shape: RoundedRectangle, u: CGFloat) -> some View {
        shape.inset(by: 3.5 * u)
            .strokeBorder(LinearGradient(colors: [Color(hex: 0x5b8cff), Color(hex: 0x3de8c2)], startPoint: .topLeading, endPoint: .bottomTrailing),
                          lineWidth: 5 * u)
            .opacity(0.55)
    }

    /// The whole glyph is a little more see-through towards the bottom: glass.
    private var glassFade: some View {
        LinearGradient(colors: [Color.white, Color.white.opacity(glassLevel)],
                       startPoint: UnitPoint(x: 0.5, y: 230 / 824), endPoint: UnitPoint(x: 0.5, y: 610 / 824))
    }

    /// The letter and the streaks in white: the ink gradient above is cut to this shape.
    private func glyph(side: CGFloat) -> some View {
        let u = side / 824
        return ZStack(alignment: .topLeading) {
            Circle()
                .stroke(Color.white, lineWidth: 80 * u)
                .frame(width: 296 * u, height: 296 * u)
                .position(x: 420 * u, y: 420 * u)
            bar(u, left: 528, top: 230, width: 80, height: 380, opacity: 1)
            streaks(u: u)
                .mask { LinearGradient(colors: [Color.clear, Color.white], startPoint: UnitPoint(x: 10 / 824, y: 0.5), endPoint: UnitPoint(x: 200 / 824, y: 0.5)) }
        }
        .frame(width: side, height: side, alignment: .topLeading)
    }

    private func streaks(u: CGFloat) -> some View {
        ZStack(alignment: .topLeading) {
            bar(u, left: 50, top: 310, width: 168, height: 34, opacity: 0.75)
            bar(u, left: 12, top: 403, width: 206, height: 34, opacity: 0.95)
            bar(u, left: 96, top: 496, width: 122, height: 34, opacity: 0.6)
        }
        .frame(width: 824 * u, height: 824 * u, alignment: .topLeading)
    }

    /// A bar with fully round ends, placed by its top left corner.
    private func bar(_ u: CGFloat, left: CGFloat, top: CGFloat, width: CGFloat, height: CGFloat, opacity: Double) -> some View {
        RoundedRectangle(cornerRadius: min(width, height) / 2 * u, style: .circular)
            .fill(Color.white.opacity(opacity))
            .frame(width: width * u, height: height * u)
            .position(x: (left + width / 2) * u, y: (top + height / 2) * u)
    }
}

private extension Color {
    init(hex: UInt32) {
        self.init(red: Double((hex >> 16) & 0xff) / 255, green: Double((hex >> 8) & 0xff) / 255, blue: Double(hex & 0xff) / 255)
    }
}
