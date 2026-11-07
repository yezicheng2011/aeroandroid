package dev.dan.androidsubsystem.sip;

import android.Manifest;
import android.app.Activity;
import android.app.role.RoleManager;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.os.Handler;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

/** Shared English-only layout helpers; no account data is sent through external intents. */
abstract class SipScreens extends Activity {
    protected LinearLayout layout;
    protected final Handler handler = new Handler(android.os.Looper.getMainLooper());
    protected int pad;
    protected void begin(String heading) {
        pad = (int) (18 * getResources().getDisplayMetrics().density);
        layout = new LinearLayout(this); layout.setOrientation(LinearLayout.VERTICAL); layout.setPadding(pad, pad, pad, pad);
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true); scroll.addView(layout); setContentView(scroll);
        TextView title = text(heading); title.setTextSize(26);
    }
    protected TextView text(String value) {
        TextView view = new TextView(this); view.setText(value); view.setTextSize(16); view.setPadding(0, pad / 3, 0, pad / 3);
        layout.addView(view); return view;
    }
    protected EditText input(String hint, int type) {
        EditText view = new EditText(this); view.setHint(hint); view.setInputType(type);
        layout.addView(view, new LinearLayout.LayoutParams(-1, -2)); return view;
    }
    protected Button button(String label, Runnable action) {
        Button button = new Button(this); button.setText(label); button.setOnClickListener(view -> action.run());
        layout.addView(button); return button;
    }
    protected void account() { startActivity(new Intent(this, AccountActivity.class)); }
    protected void role(String name) {
        RoleManager manager = getSystemService(RoleManager.class);
        if (!manager.isRoleAvailable(name)) { toast("This Android image does not offer that default-app role"); return; }
        if (manager.isRoleHeld(name)) { toast("This SIP app is already the default"); return; }
        startActivityForResult(manager.createRequestRoleIntent(name), 20);
    }
    protected void toast(String value) { Toast.makeText(this, value, Toast.LENGTH_LONG).show(); }
    protected void notifyPermission() {
        if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 30);
    }
    protected void command(String action, String target, String body) {
        try { SipService.command(this, action, target, body); }
        catch (RuntimeException error) { toast("Cannot start SIP service: " + error.getMessage()); }
    }
    protected static String recipient(String value) {
        String text = value == null ? "" : value.trim();
        if (text.regionMatches(true, 0, "tel:", 0, 4)) text = text.substring(4);
        // Normalize telephone formatting only; preserve SIP user names and full URI syntax.
        if (text.matches("[+0-9(). \\-]+")) return text.replaceAll("[(). \\-]", "");
        return text;
    }
}
