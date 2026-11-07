package dev.dan.androidsubsystem.sip;

/** Original implementation of the ITU-T G.711 companding equations. Apache-2.0. */
public final class G711 {
    private G711() {}

    public static byte encodeMuLaw(short input) {
        int sample = input;
        int sign = sample < 0 ? 0x80 : 0;
        if (sample < 0) sample = -sample;
        sample = Math.min(sample, 32635) + 132;
        int exponent = 7;
        for (int mask = 0x4000; exponent > 0 && (sample & mask) == 0; mask >>>= 1) exponent--;
        int mantissa = (sample >>> (exponent + 3)) & 15;
        return (byte) ~(sign | (exponent << 4) | mantissa);
    }

    public static short decodeMuLaw(byte input) {
        int value = (~input) & 255;
        int sample = (((value & 15) << 3) + 132) << ((value >>> 4) & 7);
        sample -= 132;
        return (short) ((value & 128) == 0 ? sample : -sample);
    }

    public static byte encodeALaw(short input) {
        int sample = input;
        int mask = sample >= 0 ? 0xd5 : 0x55;
        if (sample < 0) sample = -sample - 1;
        int exponent = 0;
        for (int boundary = 255; exponent < 8 && sample > boundary; boundary = (boundary << 1) | 1) exponent++;
        int value = exponent << 4;
        value |= (sample >>> (exponent < 2 ? 4 : exponent + 3)) & 15;
        return (byte) (value ^ mask);
    }

    public static short decodeALaw(byte input) {
        int value = (input & 255) ^ 0x55;
        int exponent = (value >>> 4) & 7;
        int sample = (value & 15) << 4;
        if (exponent == 0) sample += 8;
        else {
            sample += 264;
            if (exponent > 1) sample <<= exponent - 1;
        }
        return (short) ((value & 128) != 0 ? sample : -sample);
    }

    public static byte encode(short sample, int payload) {
        if (payload == 0) return encodeMuLaw(sample);
        if (payload == 8) return encodeALaw(sample);
        throw new IllegalArgumentException("Only PCMU and PCMA audio are supported");
    }

    public static short decode(byte sample, int payload) {
        if (payload == 0) return decodeMuLaw(sample);
        if (payload == 8) return decodeALaw(sample);
        throw new IllegalArgumentException("Only PCMU and PCMA audio are supported");
    }
}
