package dev.dan.androidsubsystem.sip;

import android.app.role.RoleManager;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;
import java.text.DateFormat;
import java.util.Date;

/** SIP MESSAGE conversation history, separate from carrier SMS. */
public final class MessagesActivity extends SipScreens {
    private EditText target, body;
    private TextView status, history;
    private Button send;
    private long seenRevision = -1;
    private final Runnable refresh = new Runnable() {
        @Override public void run() {
            status.setText(SipService.state); send.setEnabled(SipService.connected);
            if (seenRevision != SipService.revision) { seenRevision = SipService.revision; render(); }
            handler.postDelayed(this, 750);
        }
    };
    @Override public void onCreate(Bundle state) {
        super.onCreate(state); begin("SIP Messages"); status = text(SipService.state);
        text("Messages use SIP MESSAGE through your account. Sending to a mobile number works only if your provider offers a compatible SMS gateway. Accepted by SIP server does not mean delivered to a carrier handset. History stays in this app (latest 200 messages).");
        target = input("SIP address or gateway number", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        body = input("Message", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE); body.setMinLines(3);
        applyIntent(getIntent());
        send = button("Send SIP message", () -> {
            String destination = recipient(target.getText().toString()), message = body.getText().toString();
            if (destination.isEmpty() || message.isEmpty()) { toast("Enter a recipient and message"); return; }
            if (message.getBytes(java.nio.charset.StandardCharsets.UTF_8).length > 8192) { toast("Message exceeds 8192 UTF-8 bytes"); return; }
            command(SipService.SEND, destination, message); body.setText("");
        });
        button("Account settings / connect", this::account);
        button("Use as default messaging app", () -> role(RoleManager.ROLE_SMS));
        button("SIP Phone", () -> startActivity(new Intent(this, PhoneActivity.class)));
        history = text(""); history.setTextIsSelectable(true); render(); notifyPermission();
    }
    private void applyIntent(Intent intent) {
        Uri data = intent.getData();
        if (data != null) {
            String recipient = "sip".equalsIgnoreCase(data.getScheme()) ? data.toString() : data.getSchemeSpecificPart();
            if (recipient != null) { int query = recipient.indexOf('?'); target.setText(query < 0 ? recipient : recipient.substring(0, query)); }
        }
        String text = intent.getStringExtra("sms_body");
        if (text == null) text = intent.getStringExtra(Intent.EXTRA_TEXT);
        if (text != null) body.setText(text);
    }
    private void render() {
        JSONArray messages = new MessageStore(this).messages(); StringBuilder display = new StringBuilder();
        for (int i = messages.length() - 1; i >= 0; i--) {
            JSONObject item = messages.optJSONObject(i); if (item == null) continue;
            display.append(item.optBoolean("incoming") ? "From " : "To ").append(item.optString("peer"))
                .append(" · ").append(DateFormat.getDateTimeInstance().format(new Date(item.optLong("time"))))
                .append('\n').append(item.optString("body")).append('\n').append(item.optString("status")).append("\n\n");
        }
        history.setText(display.length() == 0 ? "No SIP messages yet" : display.toString());
    }
    @Override protected void onNewIntent(Intent intent) { super.onNewIntent(intent); setIntent(intent); applyIntent(intent); }
    @Override protected void onResume() { super.onResume(); seenRevision = -1; handler.post(refresh); }
    @Override protected void onPause() { handler.removeCallbacks(refresh); super.onPause(); }
}
