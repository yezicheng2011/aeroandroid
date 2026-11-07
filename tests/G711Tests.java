import dev.dan.androidsubsystem.sip.G711;
import dev.dan.androidsubsystem.sip.RtpPacket;

/** Standalone JVM checks for the original codecs and RTP framing. */
public final class G711Tests {
    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
    public static void main(String[] args) {
        check((G711.encodeMuLaw((short) 0) & 255) == 255, "PCMU silence");
        check(G711.decodeMuLaw((byte) 255) == 0, "PCMU positive zero");
        check(G711.decodeMuLaw((byte) 127) == 0, "PCMU negative zero");
        check(G711.decodeMuLaw((byte) 128) == 32124, "PCMU positive peak");
        check(G711.decodeMuLaw((byte) 0) == -32124, "PCMU negative peak");
        check((G711.encodeALaw((short) 0) & 255) == 0xd5, "PCMA silence");
        check(G711.decodeALaw((byte) 0xd5) == 8, "PCMA positive near-zero");
        check(G711.decodeALaw((byte) 0x55) == -8, "PCMA negative near-zero");
        check(G711.decodeALaw((byte) 0xaa) == 32256, "PCMA positive peak");
        check(G711.decodeALaw((byte) 0x2a) == -32256, "PCMA negative peak");
        for (int sample = Short.MIN_VALUE; sample <= Short.MAX_VALUE; sample++) {
            check(Math.abs(sample - G711.decodeMuLaw(G711.encodeMuLaw((short) sample))) <= 650, "PCMU error at " + sample);
            check(Math.abs(sample - G711.decodeALaw(G711.encodeALaw((short) sample))) <= 520, "PCMA error at " + sample);
        }
        for (int value = 0; value < 256; value++) {
            check((G711.encodeALaw(G711.decodeALaw((byte) value)) & 255) == value, "PCMA canonical code");
            int canonical = value == 127 ? 255 : value;
            check((G711.encodeMuLaw(G711.decodeMuLaw((byte) value)) & 255) == canonical, "PCMU canonical code");
        }
        byte[] packet = new byte[172];
        RtpPacket.header(packet, 8, true, 65535, 0x12345678L, 0x11223344);
        check(RtpPacket.payloadOffset(packet, packet.length) == 12, "basic offset");
        check(RtpPacket.payloadLength(packet, packet.length, 12) == 160, "basic size");
        check((packet[1] & 255) == 136 && (packet[2] & 255) == 255 && (packet[3] & 255) == 255, "header values");
        check((packet[4] & 255) == 0x12 && (packet[7] & 255) == 0x78, "network timestamp");
        check(RtpPacket.payloadOffset(packet, 11) == -1, "short header");
        packet[0] = (byte) 0x93; // RTPv2 with three CSRCs and an extension
        packet[26] = 0; packet[27] = 2;
        check(RtpPacket.payloadOffset(packet, packet.length) == 36, "CSRC extension offset");
        packet[26] = (byte) 255;
        check(RtpPacket.payloadOffset(packet, packet.length) == -1, "oversized extension");
        packet[0] = (byte) 0xa0; packet[171] = 10;
        check(RtpPacket.payloadOffset(packet, packet.length) == 12, "padded offset");
        check(RtpPacket.payloadLength(packet, packet.length, 12) == 150, "padding removed");
        packet[171] = 0;
        check(RtpPacket.payloadOffset(packet, packet.length) == -1, "zero padding rejected");
        packet[171] = (byte) 255;
        check(RtpPacket.payloadOffset(packet, packet.length) == -1, "excess padding rejected");
        packet[0] = 0;
        check(RtpPacket.payloadOffset(packet, packet.length) == -1, "RTP version checked");
        System.out.println("G.711 and RTP framing checks passed");
    }
}
