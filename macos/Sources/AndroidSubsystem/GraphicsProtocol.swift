import Foundation

struct GraphicsProtocolFailure: LocalizedError { let message: String; var errorDescription: String? { message } }

struct SurfaceFrame {
    let width: Int
    let height: Int
    let rowBytes: Int
    let timestamp: UInt64
    let pixels: Data
    static let maximumPayload = 20 + 2560 * 2560 * 4
    static func decode(_ payload: Data) throws -> SurfaceFrame {
        guard payload.count >= 20 else { throw GraphicsProtocolFailure(message: L10n.t("gfx.header_short")) }
        let width = Int(payload.u32(at: 0)), height = Int(payload.u32(at: 4))
        let stride = Int(payload.u32(at: 8))
        guard (320...2560).contains(width), (320...2560).contains(height), stride == width * 4,
              payload.count == 20 + stride * height else { throw GraphicsProtocolFailure(message: L10n.t("gfx.frame_size")) }
        return SurfaceFrame(width: width, height: height, rowBytes: stride,
                            timestamp: payload.u64(at: 12), pixels: payload.subdata(in: 20..<payload.count))
    }
}

extension Data {
    func u32(at offset: Int) -> UInt32 {
        let start = startIndex + offset
        return self[start..<start+4].reduce(0) { ($0 << 8) | UInt32($1) }
    }
    func u64(at offset: Int) -> UInt64 {
        let start = startIndex + offset
        return self[start..<start+8].reduce(0) { ($0 << 8) | UInt64($1) }
    }
}

