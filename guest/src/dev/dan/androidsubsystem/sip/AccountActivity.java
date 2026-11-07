package dev.dan.androidsubsystem.sip;

import android.os.Bundle;
import android.text.InputType;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.TextView;

/** User-supplied SIP account; TLS is preferred and certificate checks cannot be disabled. */
public final class AccountActivity extends SipScreens {
    private EditText host, port, domain, username, password, displayName;
    private CheckBox tls;
    private TextView status;
    private final Runnable refresh = new Runnable() {
        @Override public void run() { status.setText(SipService.state); handler.postDelayed(this, 1000); }
    };
    @Override public void onCreate(Bundle state) {
        super.onCreate(state); begin("SIP account");
        AccountStore store = new AccountStore(this);
        text("Use an account from your SIP provider or PBX. TCP and verified TLS are supported. Voice uses unencrypted G.711 RTP; TLS protects signaling only. SIP MESSAGE requires your provider's support; carrier SMS needs its gateway. Emergency calling is not supported.");
        host = input("SIP server hostname", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        host.setText(store.value("host", ""));
        tls = new CheckBox(this); tls.setText("TLS signaling (recommended)"); tls.setChecked(store.tls()); layout.addView(tls);
        port = input("Server port", InputType.TYPE_CLASS_NUMBER); port.setText(Integer.toString(store.port()));
        tls.setOnCheckedChangeListener((button, checked) -> {
            String old = port.getText().toString();
            if (old.equals("5060") || old.equals("5061")) port.setText(checked ? "5061" : "5060");
        });
        domain = input("SIP domain (address after @)", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        domain.setText(store.value("domain", ""));
        username = input("Username", InputType.TYPE_CLASS_TEXT); username.setText(store.value("username", ""));
        password = input("Password (leave blank to keep saved password)", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        password.setSaveEnabled(false);
        displayName = input("Display name (optional)", InputType.TYPE_CLASS_TEXT); displayName.setText(store.value("display_name", ""));
        text("The password is encrypted with Android Keystore and stays inside this app. Keep this screen private while entering it. Incoming calls and messages need an active account connection and permission to show notifications.");
        status = text(SipService.state);
        button("Save and connect", () -> {
            try {
                int number = Integer.parseInt(port.getText().toString().trim());
                new AccountStore(this).save(host.getText().toString().trim(), number, tls.isChecked(), domain.getText().toString().trim(),
                    username.getText().toString().trim(), password.getText().toString(), displayName.getText().toString().trim());
                password.setText(""); notifyPermission(); command(SipService.CONNECT, null, null);
            } catch (Exception error) { toast(error.getMessage() == null ? "Check account settings" : error.getMessage()); }
        });
        button("Disconnect", () -> command(SipService.DISCONNECT, null, null));
        button("Open SIP Phone", () -> startActivity(new android.content.Intent(this, PhoneActivity.class)));
        button("Open SIP Messages", () -> startActivity(new android.content.Intent(this, MessagesActivity.class)));
    }
    @Override protected void onResume() { super.onResume(); handler.post(refresh); }
    @Override protected void onPause() { handler.removeCallbacks(refresh); super.onPause(); }
}
