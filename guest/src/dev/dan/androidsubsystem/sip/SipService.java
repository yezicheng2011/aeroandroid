package dev.dan.androidsubsystem.sip;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioManager;
import android.os.IBinder;
import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;

/** One explicit account connection, shared by the SIP phone and messages screens. */
public final class SipService extends Service {
    public static final String CONNECT = "connect", DISCONNECT = "disconnect", CALL = "call", ANSWER = "answer",
        HANGUP = "hangup", SEND = "send", MUTE = "mute";
    public static volatile String state = "Disconnected";
    public static volatile String callState = "No active call";
    public static volatile String caller = "";
    public static volatile boolean incoming, inCall, connected;
    public static volatile boolean muted;
    public static volatile long revision;
    private static volatile SipService currentService;
    private static final int ONGOING = 7100, INCOMING = 7101, MESSAGE = 7102;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private SipClient client;
    private RtpAudio audio;
    private AudioManager audioManager;
    private AudioFocusRequest focus;
    private int generation;
    private MessageStore messages;
    private volatile boolean destroyed;

    public static void command(Context context, String action, String target, String body) {
        Intent intent = new Intent(context, SipService.class).setAction(action);
        if (target != null) intent.putExtra("target", target);
        if (body != null) intent.putExtra("body", body);
        context.startForegroundService(intent);
    }
    private void execute(Runnable work) {
        try { worker.execute(work); } catch (RejectedExecutionException ignored) { }
    }
    @Override public void onCreate() {
        super.onCreate();
        currentService = this;
        messages = new MessageStore(this);
        audioManager = getSystemService(AudioManager.class);
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("sip-connection", "SIP account", NotificationManager.IMPORTANCE_LOW));
        NotificationChannel calls = new NotificationChannel("sip-calls", "SIP incoming calls", NotificationManager.IMPORTANCE_HIGH);
        calls.setDescription("Incoming calls while your SIP account is connected");
        manager.createNotificationChannel(calls);
        manager.createNotificationChannel(new NotificationChannel("sip-messages", "SIP messages", NotificationManager.IMPORTANCE_DEFAULT));
        foreground(false);
    }
    private PendingIntent screen(Class<?> screen, int request) {
        return PendingIntent.getActivity(this, request, new Intent(this, screen).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }
    private Notification ongoing() {
        PendingIntent disconnect = PendingIntent.getService(this, 3, new Intent(this, SipService.class).setAction(DISCONNECT),
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Builder(this, "sip-connection").setSmallIcon(android.R.drawable.stat_sys_phone_call)
            .setContentTitle("SIP Phone and Messages").setContentText(state + " · " + callState)
            .setContentIntent(screen(PhoneActivity.class, 1)).setOngoing(true)
            .addAction(new Notification.Action.Builder(null, "Disconnect", disconnect).build()).build();
    }
    private void foreground(boolean microphone) {
        int type = ServiceInfo.FOREGROUND_SERVICE_TYPE_PHONE_CALL;
        if (microphone) type |= ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE;
        startForeground(ONGOING, ongoing(), type);
    }
    private void updated() {
        revision++;
        if (!destroyed) getSystemService(NotificationManager.class).notify(ONGOING, ongoing());
    }
    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null) { stopSelf(); return START_NOT_STICKY; }
        String action = intent.getAction();
        execute(() -> {
            if (destroyed) return;
            try {
                if (DISCONNECT.equals(action)) { disconnect(); stopSelf(); return; }
                if (CONNECT.equals(action)) { connect(); return; }
                if (HANGUP.equals(action)) {
                    try { if (client != null) client.hangup(); } finally { endAudio(); }
                    return;
                }
                if (MUTE.equals(action)) {
                    if (audio != null) { muted = !muted; audio.setMuted(muted); updated(); }
                    return;
                }
                if (client == null || !connected) throw new IOException("Connect your SIP account first");
                if (CALL.equals(action)) {
                    if (inCall || incoming) throw new IOException("Finish the current call first");
                    String target = intent.getStringExtra("target");
                    checkEmergency(target);
                    prepareAudio();
                    caller = target; inCall = true; callState = "Calling " + target; updated();
                    client.call(target, audio.getLocalPort(), client.getLocalAddress());
                } else if (ANSWER.equals(action)) {
                    if (!incoming) throw new IOException("There is no incoming call to answer");
                    prepareAudio(); inCall = true; callState = "Answering " + caller; updated();
                    client.answer(audio.getLocalPort(), client.getLocalAddress());
                } else if (SEND.equals(action)) {
                    String target = intent.getStringExtra("target"), body = intent.getStringExtra("body");
                    String id = client.sendMessage(target, body);
                    messages.add(id, target, body, false, "Waiting for SIP server"); revision++;
                }
            } catch (Exception error) {
                if (destroyed || currentService != this) return;
                if (SEND.equals(action)) {
                    messages.add(UUID.randomUUID().toString(), intent.getStringExtra("target"),
                        intent.getStringExtra("body"), false, "Failed: " + safe(error));
                }
                state = safe(error); if (CALL.equals(action) || ANSWER.equals(action)) endAudio(); updated();
            }
        });
        return START_NOT_STICKY;
    }
    private static String safe(Exception error) {
        String text = error.getMessage();
        return text == null || text.isEmpty() ? "SIP operation failed" : text;
    }
    private static void checkEmergency(String target) throws IOException {
        if (target == null || target.trim().isEmpty()) throw new IOException("Enter a SIP address or number");
        String digits = target.replaceFirst("(?i)^tel:", "");
        if (digits.matches("112|911|999|000|110|119|120")) throw new IOException("Emergency calling is not supported. Use a carrier phone.");
    }
    private void connect() throws IOException {
        disconnect();
        final int current = ++generation;
        state = "Connecting"; updated();
        client = new SipClient(new AccountStore(this).load(), new SipClient.Listener() {
            private void event(Runnable action) { execute(() -> { if (generation == current && !destroyed) action.run(); }); }
            @Override public void onState(String value) { event(() -> {
                connected = "registered".equals(value);
                state = connected ? "Connected" : value;
                if (!connected && ("disconnected".equals(value) || value.startsWith("error"))) endAudio();
                updated();
            }); }
            @Override public void onIncomingCall(String from) { event(() -> {
                caller = from; incoming = true; callState = "Incoming call from " + from; updated();
                getSystemService(NotificationManager.class).notify(INCOMING,
                    new Notification.Builder(SipService.this, "sip-calls").setSmallIcon(android.R.drawable.sym_call_incoming)
                        .setContentTitle("Incoming SIP call").setContentText(from).setCategory(Notification.CATEGORY_CALL)
                        .setContentIntent(screen(PhoneActivity.class, 1)).setAutoCancel(true).setVisibility(Notification.VISIBILITY_PRIVATE).build());
            }); }
            @Override public void onCallEstablished(String address, int port, int payload) { event(() -> {
                try {
                    if (audio == null) throw new IOException("Microphone access is required before answering");
                    audio.start(address, port, payload);
                    incoming = false; inCall = true; callState = "In call with " + caller;
                    getSystemService(NotificationManager.class).cancel(INCOMING); updated();
                } catch (Exception error) {
                    state = safe(error); try { if (client != null) client.hangup(); } catch (IOException ignored) { }
                    endAudio(); updated();
                }
            }); }
            @Override public void onCallEnded(String reason) { event(() -> { endAudio(); callState = reason; updated(); }); }
            @Override public void onMessage(String from, String text) { event(() -> {
                String saved = text.length() > 8192 ? text.substring(0, 8192) + "\n[Message truncated]" : text;
                messages.add(UUID.randomUUID().toString(), from, saved, true, "Received over SIP"); revision++;
                getSystemService(NotificationManager.class).notify(MESSAGE,
                    new Notification.Builder(SipService.this, "sip-messages").setSmallIcon(android.R.drawable.sym_action_chat)
                        .setContentTitle("SIP message from " + from).setContentText(saved.substring(0, Math.min(160, saved.length()))).setCategory(Notification.CATEGORY_MESSAGE)
                        .setContentIntent(screen(MessagesActivity.class, 2)).setAutoCancel(true).setVisibility(Notification.VISIBILITY_PRIVATE).build());
            }); }
            @Override public void onMessageStatus(String id, boolean success, String detail) { event(() -> {
                messages.status(id, success ? "Accepted by SIP server" : "Failed: " + detail); revision++;
            }); }
        });
        client.connect();
    }
    private void prepareAudio() throws IOException {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED)
            throw new IOException("Allow microphone access in SIP Phone before calling");
        foreground(true);
        audioManager.setMode(AudioManager.MODE_IN_COMMUNICATION);
        focus = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
            .setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
            .setOnAudioFocusChangeListener(change -> { }).build();
        if (audioManager.requestAudioFocus(focus) != AudioManager.AUDIOFOCUS_REQUEST_GRANTED)
            throw new IOException("Another app is using call audio");
        if (audio != null) audio.close();
        audio = new RtpAudio();
        muted = false;
        final RtpAudio session = audio;
        session.setFailureListener(error -> execute(() -> {
            if (audio != session || destroyed) return;
            state = safe(error);
            try { if (client != null) client.hangup(); } catch (IOException ignored) { }
            endAudio(); updated();
        }));
    }
    private void endAudio() {
        if (audio != null) { audio.close(); audio = null; }
        if (focus != null) { audioManager.abandonAudioFocusRequest(focus); focus = null; }
        if (currentService == this) {
            audioManager.setMode(AudioManager.MODE_NORMAL);
            incoming = false; inCall = false; muted = false; callState = "No active call";
            getSystemService(NotificationManager.class).cancel(INCOMING);
        }
        if (!destroyed) foreground(false);
    }
    private void disconnect() {
        generation++; connected = false;
        if (client != null) { client.close(); client = null; }
        endAudio(); caller = ""; state = "Disconnected"; updated();
    }
    @Override public void onDestroy() {
        destroyed = true; generation++;
        connected = false; incoming = false; inCall = false; state = "Disconnected";
        callState = "No active call"; revision++;
        // Socket connection/TLS and audio shutdown can block; never wait for them on Android's main thread.
        execute(() -> {
            if (client != null) { client.close(); client = null; }
            endAudio();
            if (currentService == this) currentService = null;
        });
        worker.shutdown();
        getSystemService(NotificationManager.class).cancel(INCOMING);
        stopForeground(STOP_FOREGROUND_REMOVE);
        super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent) { return null; }
}
