import SwiftUI

/// The aeroandroid logo, drawn in SwiftUI so that it follows light and dark mode the way assets/logo.svg does:
/// a rounded tile that holds a letter "a" (ring plus stem) trailing three wind lines.
/// The numbers are the SVG's, measured from the tile's top left corner; the tile is 824 units wide.
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

    // Light: white "a" on a sky-to-mint tile. Dark: a glowing azure-to-mint "a" on a deep navy tile with a thin rim.
    private var tileColors: [Color] {
        dark ? [Color(hex: 0x1a2744), Color(hex: 0x0a111f)] : [Color(hex: 0x2463eb), Color(hex: 0x1ed6aa)]
    }
    private var inkColors: [Color] {
        dark ? [Color(hex: 0x7aa7ff), Color(hex: 0x3de8c2)] : [Color.white, Color.white]
    }
    private var rimColor: Color {
        dark ? Color(hex: 0x8fb4ff).opacity(0.22) : Color.clear
    }

    private func drawing(side: CGFloat) -> some View {
        ZStack {
            tile(side: side)
            LinearGradient(colors: inkColors, startPoint: UnitPoint(x: 0.06, y: 0.28), endPoint: UnitPoint(x: 0.74, y: 0.74))
                .mask { glyph(side: side) }
        }
        .frame(width: side, height: side)
    }

    private func tile(side: CGFloat) -> some View {
        let shape = RoundedRectangle(cornerRadius: side * 228 / 824, style: .circular)
        let sky = LinearGradient(colors: tileColors, startPoint: UnitPoint(x: 0.2, y: 0), endPoint: UnitPoint(x: 0.8, y: 1))
        let sheen = LinearGradient(colors: [Color.white.opacity(dark ? 0.06 : 0.16), Color.white.opacity(0)],
                                   startPoint: .top, endPoint: UnitPoint(x: 0.5, y: 0.5))
        return shape.fill(sky)
            .overlay(shape.fill(sheen))
            .overlay(shape.strokeBorder(rimColor, lineWidth: max(1, side / 140)))
    }

    /// The letter and the wind lines in white: the gradient above is cut to this shape, so one gradient runs across all of it.
    private func glyph(side: CGFloat) -> some View {
        let u = side / 824
        return ZStack(alignment: .topLeading) {
            Circle()
                .stroke(Color.white.opacity(0.97), lineWidth: 84 * u)
                .frame(width: 296 * u, height: 296 * u)
                .position(x: 420 * u, y: 420 * u)
            bar(u, left: 524, top: 230, width: 86, height: 380, opacity: 0.97)
            bar(u, left: 90, top: 310, width: 128, height: 34, opacity: 0.55)
            bar(u, left: 50, top: 403, width: 168, height: 34, opacity: 0.8)
            bar(u, left: 130, top: 496, width: 88, height: 34, opacity: 0.45)
        }
        .frame(width: side, height: side, alignment: .topLeading)
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
