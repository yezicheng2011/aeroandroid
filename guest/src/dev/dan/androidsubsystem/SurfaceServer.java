package dev.dan.androidsubsystem;

import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.PixelFormat;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.SystemClock;
import android.view.Display;
import android.view.InputDevice;
import android.view.InputEvent;
import android.view.KeyCharacterMap;
import android.view.KeyEvent;
import android.view.MotionEvent;
import org.json.JSONObject;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.File;
import java.lang.reflect.Method;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.concurrent.atomic.AtomicBoolean;

/** Shell-UID guest display service. Started by app_process, not an ordinary APK activity.
 * One authenticated connection owns one VirtualDisplay. Frames are packed RGBA8.
 * This initial transport copies pixels over ADB-forwarded TCP; it is NOT VM zero-copy.
 */
public final class SurfaceServer {
    private static final int PORT = 7900;
    private static final int MAX_CONTROL = 65536;
    // These shell-only flags are @hide in the public API 36 android.jar. Keep
    // their Android 16 framework values, as scrcpy does, instead of referencing
    // SDK fields that javac cannot see. No mirroring or system decorations.
    // https://android.googlesource.com/platform/frameworks/base/+/android16-release/core/java/android/hardware/display/DisplayManager.java
    private static final int VIRTUAL_DISPLAY_FLAG_SUPPORTS_TOUCH = 1 << 6;
    private static final int VIRTUAL_DISPLAY_FLAG_DESTROY_CONTENT_ON_REMOVAL = 1 << 8;
    private static final int VIRTUAL_DISPLAY_FLAG_TRUSTED = 1 << 10;
    private static final int VIRTUAL_DISPLAY_FLAG_OWN_DISPLAY_GROUP = 1 << 11;
    private static final int VIRTUAL_DISPLAY_FLAG_ALWAYS_UNLOCKED = 1 << 12;
    private static final int VIRTUAL_DISPLAY_FLAG_TOUCH_FEEDBACK_DISABLED = 1 << 13;
    private static final int VIRTUAL_DISPLAY_FLAG_OWN_FOCUS = 1 << 14;
    private static final int DISPLAY_FLAGS = DisplayManager.VIRTUAL_DISPLAY_FLAG_PUBLIC
            | DisplayManager.VIRTUAL_DISPLAY_FLAG_OWN_CONTENT_ONLY
            | VIRTUAL_DISPLAY_FLAG_SUPPORTS_TOUCH
            | VIRTUAL_DISPLAY_FLAG_DESTROY_CONTENT_ON_REMOVAL
            | VIRTUAL_DISPLAY_FLAG_TRUSTED
            | VIRTUAL_DISPLAY_FLAG_OWN_DISPLAY_GROUP
            | VIRTUAL_DISPLAY_FLAG_ALWAYS_UNLOCKED
            | VIRTUAL_DISPLAY_FLAG_TOUCH_FEEDBACK_DISABLED
            | VIRTUAL_DISPLAY_FLAG_OWN_FOCUS;
    private static Context context;
    private static byte[] token;
    private static Object inputManager;
    private static Method injectInput, setDisplay;

    public static void main(String[] args) throws Exception {
        android.os.Looper.prepareMainLooper();
        Class<?> activityThread = Class.forName("android.app.ActivityThread");
        Object thread = activityThread.getMethod("systemMain").invoke(null);
        Context system = (Context) activityThread.getMethod("getSystemContext").invoke(thread);
        // Attribute Binder calls to the actual shell UID, not the android/system package.
        context = system.createPackageContext("com.android.shell", Context.CONTEXT_IGNORE_SECURITY);
        token = Files.readAllBytes(new File("/data/local/tmp/mac-surface/token").toPath());
        Class<?> manager;
        try { manager = Class.forName("android.hardware.input.InputManagerGlobal"); }
        catch (ClassNotFoundException legacy) { manager = Class.forName("android.hardware.input.InputManager"); }
        inputManager = manager.getMethod("getInstance").invoke(null);
        injectInput = manager.getMethod("injectInputEvent", InputEvent.class, int.class);
        setDisplay = InputEvent.class.getMethod("setDisplayId", int.class);
        Thread listener = new Thread(() -> {
            try (ServerSocket server = new ServerSocket(PORT, 8, InetAddress.getByName("127.0.0.1"))) {
                System.out.println("Mac Surface Bridge ready v1");
                while (true) {
                    Socket client = server.accept();
                    client.setTcpNoDelay(true);
                    client.setSoTimeout(10000);
                    new Thread(() -> {
                        try { new Session(client).run(); }
                        catch (Exception e) { System.err.println("Session failed: " + e.getClass().getSimpleName() + ": " + e.getMessage()); }
                        finally { try { client.close(); } catch (Exception ignored) { } }
                    }, "surface-session").start();
                }
            } catch (Exception e) { System.err.println(e); System.exit(1); }
        }, "surface-listener");
        listener.start();
        android.os.Looper.loop();
    }

    private static void inject(InputEvent event, int display) throws Exception {
        setDisplay.invoke(event, display);
        if (!Boolean.TRUE.equals(injectInput.invoke(inputManager, event, 0))) {
            throw new IllegalStateException("Android rejected input injection");
        }
    }

    private static final class Session {
        final Socket socket;
        final DataInputStream input;
        final DataOutputStream output;
        final AtomicBoolean closed = new AtomicBoolean();
        HandlerThread images;
        Handler imageHandler;
        volatile VirtualDisplay display;
        volatile ImageReader reader;
        volatile int width, height, dpi, displayId;
        int fps;
        String packageName;
        long lastFrame, pointerDown;
        long framesSent;
        boolean imageCallbackLogged;
        byte[] pixels;
        Session(Socket s) throws Exception { socket = s; input = new DataInputStream(s.getInputStream()); output = new DataOutputStream(s.getOutputStream()); }
        JSONObject readControl() throws Exception {
            int type = input.readUnsignedByte(), length = input.readInt();
            if (type != 16 || length < 2 || length > MAX_CONTROL) throw new IllegalArgumentException("Bad control frame");
            byte[] payload = new byte[length]; input.readFully(payload);
            return new JSONObject(new String(payload, StandardCharsets.UTF_8));
        }
        synchronized void json(JSONObject data) throws Exception {
            byte[] bytes = data.toString().getBytes(StandardCharsets.UTF_8);
            output.writeByte(3); output.writeInt(bytes.length); output.write(bytes); output.flush();
        }
        String displayDetails() {
            if (display == null) return "display=not-created";
            try {
                Display current = display.getDisplay();
                return "display=" + current.getDisplayId() + " valid=" + current.isValid()
                        + " state=" + current.getState() + " flags=0x" + Integer.toHexString(current.getFlags());
            } catch (RuntimeException unavailable) {
                return "display=" + displayId + " state=unavailable(" + unavailable.getClass().getSimpleName() + ")";
            }
        }
        void logDisplay(String stage) {
            System.out.println("Surface " + stage + " package=" + packageName + " " + displayDetails()
                    + " requestedFlags=0x" + Integer.toHexString(DISPLAY_FLAGS));
        }
        void signalFailure(String stage, Throwable failure) {
            if (!closed.compareAndSet(false, true)) return;
            Throwable detail = failure;
            for (int depth = 0; depth < 16 && detail.getCause() != null && detail.getCause() != detail; depth++) {
                detail = detail.getCause();
            }
            String message = detail.getClass().getSimpleName() + ": " + String.valueOf(detail.getMessage());
            System.err.println("Surface " + stage + " failed package=" + packageName + " " + displayDetails() + ": " + message);
            detail.printStackTrace(System.err);
            if (message.length() > 4096) message = message.substring(0, 4096) + "… (see surface-bridge.log)";
            try {
                JSONObject error = new JSONObject(); error.put("event", "error");
                error.put("stage", stage); error.put("message", message); error.put("display", displayId);
                error.put("details", displayDetails()); json(error);
            } catch (Exception ignored) { }
            finally { try { socket.close(); } catch (Exception ignored) { } }
        }
        void displayState(String stage) {
            if (closed.get()) return;
            logDisplay(stage);
            try {
                JSONObject event = new JSONObject(); event.put("event", "display-state");
                event.put("stage", stage); event.put("display", displayId);
                event.put("details", displayDetails()); json(event);
            } catch (Exception failure) { signalFailure("display-state", failure); }
        }
        void run() throws Exception {
            try {
                JSONObject hello = readControl();
                byte[] supplied = hello.optString("token").getBytes(StandardCharsets.UTF_8);
                if (!MessageDigest.isEqual(token, supplied) || hello.optInt("version") != 1) throw new SecurityException("Authentication failed");
                packageName = hello.getString("package");
                if (!packageName.matches("[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z0-9_]+)+")) throw new IllegalArgumentException("Bad package");
                width = hello.optInt("width", 1280); height = hello.optInt("height", 960);
                dpi = hello.optInt("dpi", 200); fps = hello.optInt("fps", 30);
                validateSize(width, height, dpi);
                if (fps < 15 || fps > 60) throw new IllegalArgumentException("Bad frame rate");
                images = new HandlerThread("surface-images"); images.start(); imageHandler = new Handler(images.getLooper());
                reader = newReader(width, height);
                DisplayManager manager = context.getSystemService(DisplayManager.class);
                display = manager.createVirtualDisplay("MacApp:" + packageName, width, height, dpi, reader.getSurface(),
                        DISPLAY_FLAGS, new VirtualDisplay.Callback() {
                            @Override public void onPaused() { displayState("paused"); }
                            @Override public void onResumed() { displayState("resumed"); }
                            @Override public void onStopped() {
                                if (!closed.get()) signalFailure("display-stopped", new IllegalStateException("Android stopped the application display"));
                            }
                        }, imageHandler);
                if (display == null) throw new IllegalStateException("Virtual display creation failed");
                displayId = display.getDisplay().getDisplayId();
                logDisplay("created");
                startApplication();
                JSONObject ready = new JSONObject(); ready.put("event", "ready"); ready.put("display", displayId);
                ready.put("details", displayDetails());
                ready.put("width", width); ready.put("height", height); ready.put("transport", "rgba-tcp-v1"); json(ready);
                socket.setSoTimeout(0);
                while (!closed.get()) control(readControl());
            } catch (Throwable failure) {
                signalFailure("session", failure);
            } finally {
                closed.set(true);
                if (display != null) { try { display.release(); } catch (RuntimeException failure) { System.err.println("Surface display cleanup: " + failure); } }
                if (reader != null) { try { reader.close(); } catch (RuntimeException failure) { System.err.println("Surface reader cleanup: " + failure); } }
                if (images != null) images.quitSafely();
            }
        }
        ImageReader newReader(int w, int h) {
            ImageReader next = ImageReader.newInstance(w, h, PixelFormat.RGBA_8888, 3);
            next.setOnImageAvailableListener(this::frame, imageHandler);
            return next;
        }
        static void validateSize(int w, int h, int density) {
            if (w < 320 || h < 320 || w > 2560 || h > 2560 || density < 100 || density > 640) throw new IllegalArgumentException("Bad display size");
        }
        void frame(ImageReader source) {
            if (closed.get() || source != reader) return;
            if (!imageCallbackLogged) { imageCallbackLogged = true; logDisplay("first-image-callback"); }
            try (Image image = source.acquireLatestImage()) {
                if (image == null) return;
                long now = SystemClock.elapsedRealtimeNanos();
                if (now - lastFrame < 1000000000L / fps) return;
                lastFrame = now;
                Image.Plane plane = image.getPlanes()[0];
                int w = image.getWidth(), h = image.getHeight(), stride = plane.getRowStride(), step = plane.getPixelStride();
                if (step != 4) throw new IllegalStateException("Expected RGBA8 surface");
                int count = w * h * 4;
                if (pixels == null || pixels.length != count) pixels = new byte[count];
                ByteBuffer data = plane.getBuffer();
                for (int row = 0; row < h; row++) { data.position(row * stride); data.get(pixels, row * w * 4, w * 4); }
                synchronized (this) {
                    SurfaceWire.writeFrame(output, w, h, image.getTimestamp(), pixels);
                }
                if (framesSent++ == 0) {
                    System.out.println("Surface first-frame package=" + packageName + " display=" + displayId
                            + " size=" + w + "x" + h + " bytes=" + count);
                }
            } catch (Throwable failure) {
                signalFailure("frame", failure);
            }
        }
        void startApplication() throws Exception {
            Intent intent = context.getPackageManager().getLaunchIntentForPackage(packageName);
            if (intent == null || intent.getComponent() == null) throw new IllegalArgumentException("No launcher activity for " + packageName);
            Process process = new ProcessBuilder("am", "start", "--display", String.valueOf(displayId), "-n", intent.getComponent().flattenToString()).redirectErrorStream(true).start();
            // Drain the bounded command output to avoid a blocked child process.
            ByteArrayOutputStreamLimited log = new ByteArrayOutputStreamLimited();
            byte[] buffer = new byte[1024]; int n;
            while ((n = process.getInputStream().read(buffer)) != -1) log.add(buffer, n);
            int exit = process.waitFor();
            System.out.println("Surface launch package=" + packageName + " display=" + displayId
                    + " exit=" + exit + " output=" + log.text().trim());
            if (exit != 0 || log.text().contains("Error:")) throw new IllegalStateException("Launch failed: " + log.text());
        }
        void control(JSONObject message) throws Exception {
            String type = message.getString("type");
            if ("close".equals(type)) { closed.set(true); return; }
            if ("resize".equals(type)) {
                int w = message.getInt("width"), h = message.getInt("height"), density = message.optInt("dpi", dpi); validateSize(w, h, density);
                imageHandler.post(() -> {
                    if (closed.get()) return;
                    if (width == w && height == h && dpi == density) return;
                    ImageReader next = null;
                    try {
                        System.out.println("Surface resize package=" + packageName + " display=" + displayId
                                + " size=" + w + "x" + h + " dpi=" + density);
                        ImageReader old = reader; next = newReader(w, h);
                        display.setSurface(next.getSurface()); display.resize(w, h, density);
                        reader = next; width = w; height = h; dpi = density; lastFrame = 0;
                        old.close(); logDisplay("resized");
                    } catch (Throwable failure) {
                        if (next != null) { try { next.close(); } catch (Exception ignored) { } }
                        signalFailure("resize", failure);
                    }
                });
            } else if ("pointer".equals(type)) {
                int action = message.getInt("action");
                if (action != MotionEvent.ACTION_DOWN && action != MotionEvent.ACTION_UP && action != MotionEvent.ACTION_MOVE) throw new IllegalArgumentException("Bad pointer action");
                long now = SystemClock.uptimeMillis(); if (action == MotionEvent.ACTION_DOWN) pointerDown = now;
                float x = Math.max(0, Math.min(width - 1, (float) message.getDouble("x")));
                float y = Math.max(0, Math.min(height - 1, (float) message.getDouble("y")));
                MotionEvent event = MotionEvent.obtain(pointerDown, now, action, x, y, 0);
                event.setSource(InputDevice.SOURCE_TOUCHSCREEN); inject(event, displayId); event.recycle();
            } else if ("key".equals(type)) {
                int code = message.getInt("code"), action = message.optInt("action", 0);
                if (code < 0 || code > KeyEvent.getMaxKeyCode() || (action != 0 && action != 1)) throw new IllegalArgumentException("Bad key event");
                long now = SystemClock.uptimeMillis();
                inject(new KeyEvent(now, now, action, code, 0, message.optInt("meta", 0), KeyCharacterMap.VIRTUAL_KEYBOARD, 0, 0, InputDevice.SOURCE_KEYBOARD), displayId);
            } else if ("text".equals(type)) {
                String text = message.getString("text");
                if (text.length() > 8192) throw new IllegalArgumentException("Text too long");
                android.os.Bundle args = new android.os.Bundle(); args.putString("text", text);
                android.os.Bundle result = context.getContentResolver().call(android.net.Uri.parse("content://dev.dan.androidsubsystem.bridge"), "commit", null, args);
                if (result == null || !result.getBoolean("accepted")) {
                    KeyEvent[] events = KeyCharacterMap.load(KeyCharacterMap.VIRTUAL_KEYBOARD).getEvents(text.toCharArray());
                    if (events == null) { JSONObject error = new JSONObject(); error.put("event", "input-warning"); error.put("message", "Enable Mac Bridge IME for Unicode text input"); json(error); }
                    else for (KeyEvent event : events) inject(event, displayId);
                }
            } else if ("focus".equals(type)) {
                // Re-select the existing activity on its display; Android owns Activity lifecycle.
                startApplication();
            } else if ("visibility".equals(type)) {
                display.setSurface(message.getBoolean("visible") ? reader.getSurface() : null);
            } else if ("clipboard-get".equals(type)) {
                try {
                    android.content.ClipboardManager clipboard = context.getSystemService(android.content.ClipboardManager.class);
                    android.content.ClipData clip = clipboard.getPrimaryClip();
                    if (clip != null && clip.getItemCount() > 0) {
                        JSONObject event = new JSONObject(); event.put("event", "clipboard");
                        CharSequence text = clip.getItemAt(0).coerceToText(context);
                        event.put("text", text == null ? "" : text.toString()); json(event);
                    }
                } catch (RuntimeException denied) {
                    JSONObject warning = new JSONObject(); warning.put("event", "input-warning");
                    warning.put("message", "Clipboard unavailable: " + denied.getClass().getSimpleName()); json(warning);
                }
            } else if ("scroll".equals(type)) {
                long now = SystemClock.uptimeMillis();
                MotionEvent.PointerProperties properties = new MotionEvent.PointerProperties(); properties.id = 0; properties.toolType = MotionEvent.TOOL_TYPE_MOUSE;
                MotionEvent.PointerCoords coords = new MotionEvent.PointerCoords(); coords.x = (float) message.getDouble("x"); coords.y = (float) message.getDouble("y");
                coords.setAxisValue(MotionEvent.AXIS_VSCROLL, (float) message.getDouble("dy"));
                coords.setAxisValue(MotionEvent.AXIS_HSCROLL, (float) message.getDouble("dx"));
                MotionEvent event = MotionEvent.obtain(now, now, MotionEvent.ACTION_SCROLL, 1, new MotionEvent.PointerProperties[]{properties}, new MotionEvent.PointerCoords[]{coords}, 0, 0, 1, 1, 0, 0, InputDevice.SOURCE_MOUSE, 0);
                inject(event, displayId); event.recycle();
            } else { throw new IllegalArgumentException("Unknown control type"); }
        }
    }
    private static final class ByteArrayOutputStreamLimited {
        final java.io.ByteArrayOutputStream bytes = new java.io.ByteArrayOutputStream();
        void add(byte[] b, int n) { if (bytes.size() < 65536) bytes.write(b, 0, Math.min(n, 65536 - bytes.size())); }
        String text() { return new String(bytes.toByteArray(), StandardCharsets.UTF_8); }
    }
}
