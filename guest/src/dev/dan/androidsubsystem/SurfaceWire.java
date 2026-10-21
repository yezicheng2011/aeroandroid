package dev.dan.androidsubsystem;
import java.io.DataOutputStream;
import java.io.IOException;

/** Pure-Java wire framing, independently tested against the Swift decoder. */
public final class SurfaceWire {
    private SurfaceWire() { }
    public static void writeFrame(DataOutputStream output, int width, int height, long timestamp, byte[] pixels) throws IOException {
        if (width < 320 || width > 2560 || height < 320 || height > 2560 || pixels.length != width * height * 4) {
            throw new IllegalArgumentException("Invalid RGBA surface frame");
        }
        output.writeByte(1); output.writeInt(20 + pixels.length);
        output.writeInt(width); output.writeInt(height); output.writeInt(width * 4); output.writeLong(timestamp);
        output.write(pixels); output.flush();
    }
}
