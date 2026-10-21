import Foundation

@main
struct GraphicsProtocolTests {
    static func require(_ condition: @autoclosure () -> Bool, _ message: String) throws {
        if !condition() { throw GraphicsProtocolFailure(message: message) }
    }
    static func reject(_ payload: Data) throws {
        do { _ = try SurfaceFrame.decode(payload) }
        catch { return }
        throw GraphicsProtocolFailure(message: "Invalid frame was accepted")
    }
    static func main() throws {
        let packet = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
        try require(packet[0] == 1, "Wrong packet type")
        try require(Int(packet.u32(at: 1)) == packet.count - 5, "Wire length mismatch")
        let body = packet.subdata(in: 5..<packet.count)
        let frame = try SurfaceFrame.decode(body)
        try require(frame.width == 320 && frame.height == 480 && frame.rowBytes == 1280, "Dimensions mismatch")
        try require(frame.timestamp == 1234567891234, "Timestamp endian mismatch")
        try require(Array(frame.pixels.prefix(4)) == [255, 0, 128, 255], "RGBA byte order mismatch")
        try reject(Data())
        try reject(body.prefix(19))
        try reject(body.dropLast())
        var wrongStride = body; wrongStride[11] = 1; try reject(wrongStride)
        var enormousWidth = body; enormousWidth[0] = 255; try reject(enormousWidth)
        var tooSmall = body; tooSmall[0] = 0; tooSmall[1] = 0; tooSmall[2] = 0; tooSmall[3] = 1; try reject(tooSmall)
        var trailing = body; trailing.append(0); try reject(trailing)
        print("PASS: Java → Swift frame interoperability and 7 malformed-frame checks")
    }
}
