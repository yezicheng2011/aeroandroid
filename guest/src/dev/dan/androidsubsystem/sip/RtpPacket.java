package dev.dan.androidsubsystem.sip;

/** Minimal RTP v2 packet framing for G.711, with strict length checks. Apache-2.0. */
public final class RtpPacket {
    private RtpPacket() {}

    public static int payloadOffset(byte[] data, int length) {
        if (length < 12 || length > data.length || ((data[0] & 255) >>> 6) != 2) return -1;
        int offset = 12 + (data[0] & 15) * 4;
        if (offset > length) return -1;
        if ((data[0] & 16) != 0) {
            if (length - offset < 4) return -1;
            int words = ((data[offset + 2] & 255) << 8) | (data[offset + 3] & 255);
            if (words > (length - offset - 4) / 4) return -1;
            offset += 4 + words * 4;
        }
        return payloadLength(data, length, offset) > 0 ? offset : -1;
    }

    public static int payloadLength(byte[] data, int length, int offset) {
        if (offset < 12 || length > data.length || length < offset) return -1;
        int padding = (data[0] & 32) == 0 ? 0 : data[length - 1] & 255;
        if ((data[0] & 32) != 0 && (padding == 0 || padding > length - offset)) return -1;
        return length - offset - padding;
    }

    public static void header(byte[] data, int payload, boolean marker, int sequence, long timestamp, int source) {
        if (data.length < 12) throw new IllegalArgumentException("RTP header is too short");
        data[0] = (byte) 0x80;
        data[1] = (byte) (payload | (marker ? 128 : 0));
        data[2] = (byte) (sequence >>> 8); data[3] = (byte) sequence;
        data[4] = (byte) (timestamp >>> 24); data[5] = (byte) (timestamp >>> 16);
        data[6] = (byte) (timestamp >>> 8); data[7] = (byte) timestamp;
        data[8] = (byte) (source >>> 24); data[9] = (byte) (source >>> 16);
        data[10] = (byte) (source >>> 8); data[11] = (byte) source;
    }
}
