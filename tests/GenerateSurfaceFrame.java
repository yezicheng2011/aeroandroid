import dev.dan.androidsubsystem.SurfaceWire;
import java.io.DataOutputStream;
import java.io.FileOutputStream;
public final class GenerateSurfaceFrame {
    public static void main(String[] args) throws Exception {
        byte[] pixels = new byte[320 * 480 * 4];
        for (int i = 0; i < pixels.length; i += 4) {
            pixels[i] = (byte) 255; pixels[i + 1] = 0; pixels[i + 2] = (byte) 128; pixels[i + 3] = (byte) 255;
        }
        try (DataOutputStream output = new DataOutputStream(new FileOutputStream(args[0]))) {
            SurfaceWire.writeFrame(output, 320, 480, 1234567891234L, pixels);
        }
        if (args.length > 1) {
            try (DataOutputStream output = new DataOutputStream(new FileOutputStream(args[1]))) {
                SurfaceWire.writeFrame(output, 64, 96, 7L, new byte[64 * 96 * 4]);
            }
        }
        try {
            SurfaceWire.writeFrame(new DataOutputStream(new java.io.ByteArrayOutputStream()), 63, 96, 0L, new byte[63 * 96 * 4]);
            throw new AssertionError("A frame below the widget minimum was accepted");
        } catch (IllegalArgumentException expected) { }
        try {
            SurfaceWire.writeFrame(new DataOutputStream(System.out), 1, 1, 0L, new byte[4]);
            throw new AssertionError("Invalid dimensions accepted");
        } catch (IllegalArgumentException expected) { }
    }
}
