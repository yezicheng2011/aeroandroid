package dev.dan.androidsubsystem.sip;

import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.AudioTrack;
import android.media.MediaRecorder;

import java.io.Closeable;
import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.SocketTimeoutException;
import java.security.SecureRandom;

/** One full-duplex 8 kHz G.711 RTP session. No native codec or external dependency. */
public final class RtpAudio implements Closeable {
    public interface FailureListener { void onFailure(IOException error); }
    private static final int RATE = 8000;
    private static final int SAMPLES = 160;
    private static final int MAX_AUDIO = 1920;
    private final DatagramSocket socket;
    private final Object lock = new Object();
    private volatile boolean running;
    private volatile boolean closed;
    private volatile boolean muted;
    private boolean started;
    private AudioRecord recorder;
    private AudioTrack player;
    private Thread captureThread;
    private Thread receiveThread;
    private volatile FailureListener failureListener;

    public RtpAudio() throws IOException {
        socket = new DatagramSocket();
        socket.setSoTimeout(500);
    }

    public int getLocalPort() { return socket.getLocalPort(); }
    public void setFailureListener(FailureListener listener) { failureListener = listener; }
    public void setMuted(boolean value) { muted = value; }

    public void start(String address, int port, int payload) throws IOException {
        if (payload != 0 && payload != 8) throw new IOException("Only PCMU and PCMA audio are supported");
        if (port < 1 || port > 65535) throw new IOException("Invalid remote audio port");
        InetAddress peer = InetAddress.getByName(address);
        synchronized (lock) {
            if (closed || started) throw new IOException("Audio session has already been used");
            started = true;
            try {
                socket.connect(peer, port);
                int inputMinimum = AudioRecord.getMinBufferSize(RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
                int outputMinimum = AudioTrack.getMinBufferSize(RATE, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT);
                if (inputMinimum <= 0 || outputMinimum <= 0) throw new IOException("This device cannot provide 8 kHz call audio");
                recorder = new AudioRecord(MediaRecorder.AudioSource.VOICE_COMMUNICATION, RATE,
                    AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, Math.max(inputMinimum, SAMPLES * 16));
                player = new AudioTrack.Builder()
                    .setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                    .setAudioFormat(new AudioFormat.Builder().setSampleRate(RATE).setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT).build())
                    .setTransferMode(AudioTrack.MODE_STREAM).setBufferSizeInBytes(Math.max(outputMinimum, SAMPLES * 16)).build();
                if (recorder.getState() != AudioRecord.STATE_INITIALIZED || player.getState() != AudioTrack.STATE_INITIALIZED)
                    throw new IOException("Call audio could not be initialized");
                recorder.startRecording();
                player.play();
                if (recorder.getRecordingState() != AudioRecord.RECORDSTATE_RECORDING)
                    throw new IOException("Microphone recording did not start");
                running = true;
                final AudioRecord capture = recorder;
                final AudioTrack playback = player;
                captureThread = new Thread(() -> capture(capture, payload), "SIP microphone RTP");
                receiveThread = new Thread(() -> receive(playback, peer, port, payload), "SIP speaker RTP");
                captureThread.setDaemon(true); receiveThread.setDaemon(true);
                captureThread.start(); receiveThread.start();
            } catch (IOException e) {
                close(); throw e;
            } catch (RuntimeException e) {
                close(); throw new IOException("Microphone or speaker could not be started", e);
            }
        }
    }

    private void capture(AudioRecord input, int payload) {
        SecureRandom random = new SecureRandom();
        int sequence = random.nextInt(65536), source = random.nextInt();
        long timestamp = random.nextInt() & 0xffffffffL;
        boolean first = true;
        byte[] packet = new byte[12 + SAMPLES];
        short[] samples = new short[SAMPLES];
        try {
            while (running) {
                int filled = 0;
                while (running && filled < SAMPLES) {
                    int count = input.read(samples, filled, SAMPLES - filled);
                    if (count <= 0) throw new IOException("Microphone stopped providing call audio");
                    filled += count;
                }
                if (!running) break;
                RtpPacket.header(packet, payload, first, sequence++, timestamp, source);
                first = false;
                boolean silence = muted;
                for (int i = 0; i < filled; i++) packet[12 + i] = G711.encode(silence ? (short) 0 : samples[i], payload);
                socket.send(new DatagramPacket(packet, 12 + filled));
                timestamp = (timestamp + filled) & 0xffffffffL;
            }
        } catch (IOException | RuntimeException e) { fail(e); }
    }

    private void receive(AudioTrack output, InetAddress peer, int port, int payload) {
        byte[] bytes = new byte[4096];
        short[] samples = new short[MAX_AUDIO];
        DatagramPacket packet = new DatagramPacket(bytes, bytes.length);
        boolean haveSource = false;
        int source = 0, lastSequence = 0;
        try {
            while (running) {
                try { packet.setLength(bytes.length); socket.receive(packet);
                } catch (SocketTimeoutException e) { continue; }
                if (!peer.equals(packet.getAddress()) || port != packet.getPort()) continue;
                int length = packet.getLength(), offset = RtpPacket.payloadOffset(bytes, length);
                if (offset < 0 || (bytes[1] & 127) != payload) continue;
                int count = RtpPacket.payloadLength(bytes, length, offset);
                if (count <= 0 || count > samples.length) continue;
                int currentSource = ((bytes[8] & 255) << 24) | ((bytes[9] & 255) << 16)
                    | ((bytes[10] & 255) << 8) | (bytes[11] & 255);
                int sequence = ((bytes[2] & 255) << 8) | (bytes[3] & 255);
                if (haveSource && (source != currentSource || (short) (sequence - lastSequence) <= 0)) continue;
                haveSource = true; source = currentSource; lastSequence = sequence;
                for (int i = 0; i < count; i++) samples[i] = G711.decode(bytes[offset + i], payload);
                int written = 0;
                while (running && written < count) {
                    int chunk = output.write(samples, written, count - written, AudioTrack.WRITE_BLOCKING);
                    if (chunk <= 0) throw new IOException("Speaker stopped accepting call audio");
                    written += chunk;
                }
            }
        } catch (IOException | RuntimeException e) { fail(e); }
    }

    private void fail(Exception error) {
        if (!running) return;
        close();
        FailureListener listener = failureListener;
        if (listener != null) listener.onFailure(error instanceof IOException ? (IOException) error : new IOException("Call audio failed", error));
    }

    @Override public void close() {
        AudioRecord input;
        AudioTrack output;
        Thread capture, receive;
        synchronized (lock) {
            if (closed) return;
            closed = true; running = false;
            input = recorder; output = player;
            capture = captureThread; receive = receiveThread;
            recorder = null; player = null;
        }
        socket.close();
        if (input != null) {
            try { input.stop(); } catch (RuntimeException ignored) {}
            try { input.release(); } catch (RuntimeException ignored) {}
        }
        if (output != null) {
            try { output.stop(); } catch (RuntimeException ignored) {}
            try { output.release(); } catch (RuntimeException ignored) {}
        }
        join(capture); join(receive);
    }

    private static void join(Thread thread) {
        if (thread == null || thread == Thread.currentThread()) return;
        try { thread.join(750); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
    }
}
