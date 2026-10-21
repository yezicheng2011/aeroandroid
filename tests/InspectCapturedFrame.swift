import Foundation

@main
struct InspectCapturedFrame {
    static func main() throws {
        for path in CommandLine.arguments.dropFirst() {
            let packet = try Data(contentsOf: URL(fileURLWithPath: path))
            guard packet.count >= 5, packet[0] == 1,
                  Int(packet.u32(at: 1)) == packet.count - 5 else {
                throw GraphicsProtocolFailure(message: "Invalid captured packet")
            }
            let frame = try SurfaceFrame.decode(packet.subdata(in: 5..<packet.count))
            print("PASS: captured Guest frame decoded by Swift: \(frame.width)x\(frame.height), \(frame.pixels.count) RGBA bytes, timestamp \(frame.timestamp)")
        }
    }
}
