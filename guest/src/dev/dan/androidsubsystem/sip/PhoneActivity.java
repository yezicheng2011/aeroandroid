package dev.dan.androidsubsystem.sip;

import android.Manifest;
import android.app.role.RoleManager;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;

/** SIP dialer that never silently falls back to cellular calling. */
public final class PhoneActivity extends SipScreens {
    private EditText target;
    private TextView status;
    private Button call, answer, hangup, mute;
    private String pendingAction;
    private final Runnable refresh = new Runnable() {
        @Override public void run() {
            status.setText(SipService.state + "\n" + SipService.callState);
            call.setEnabled(SipService.connected && !SipService.inCall && !SipService.incoming);
            answer.setEnabled(SipService.incoming && !SipService.inCall);
            hangup.setEnabled(SipService.inCall || SipService.incoming);
            mute.setEnabled(SipService.inCall); mute.setText(SipService.muted ? "Unmute microphone" : "Mute microphone");
            handler.postDelayed(this, 500);
        }
    };
    @Override public void onCreate(Bundle state) {
        super.onCreate(state); begin("SIP Phone");
        status = text(SipService.state);
        target = input("SIP address or PBX number", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        applyIntent(getIntent());
        call = button("Call", () -> microphone(SipService.CALL));
        answer = button("Answer incoming call", () -> microphone(SipService.ANSWER));
        hangup = button("End / decline call", () -> command(SipService.HANGUP, null, null));
        mute = button("Mute microphone", () -> command(SipService.MUTE, null, null));
        button("Account settings / connect", this::account);
        button("Use as default phone app", () -> role(RoleManager.ROLE_DIALER));
        button("SIP messages", () -> startActivity(new Intent(this, MessagesActivity.class)));
        text("Calls use your configured SIP account. Emergency calls and cellular calling are not provided. Your provider must support TCP or TLS, G.711 audio and symmetric RTP for networks behind NAT. Media is RTP, not SRTP; use a trusted network or VPN.");
        notifyPermission();
    }
    private void applyIntent(Intent intent) {
        Uri data = intent.getData();
        if (data != null) {
            String address = "sip".equalsIgnoreCase(data.getScheme()) ? data.toString() : data.getSchemeSpecificPart();
            target.setText(address == null ? "" : address);
        }
    }
    @Override protected void onNewIntent(Intent intent) { super.onNewIntent(intent); setIntent(intent); applyIntent(intent); }
    private void microphone(String action) {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            pendingAction = action; requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 40); return;
        }
        command(action, recipient(target.getText().toString()), null);
    }
    @Override public void onRequestPermissionsResult(int request, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(request, permissions, results);
        if (request == 40) {
            String action = pendingAction; pendingAction = null;
            if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED && action != null) microphone(action);
            else toast("Microphone permission is required for SIP audio calls");
        }
    }
    @Override protected void onResume() { super.onResume(); handler.post(refresh); }
    @Override protected void onPause() { handler.removeCallbacks(refresh); super.onPause(); }
}
