package dev.dan.androidsubsystem;

import android.app.Activity;
import android.os.Bundle;
import android.content.Intent;
import android.provider.Settings;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

public final class BridgeActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (24 * getResources().getDisplayMetrics().density);
        layout.setPadding(pad, pad, pad, pad);
        TextView heading = new TextView(this);
        heading.setText("Mac Bridge"); heading.setTextSize(28);
        layout.addView(heading);
        TextView body = new TextView(this);
        body.setText("Android Subsystem · desktop bridge\n\nAfter you grant notification access, the Mac manager can forward Android notifications to Notification Center.\n\nNotifications stay on-device over local ADB and are never uploaded. You can revoke access anytime in Android Settings.\n\nApp icons and names do not require notification access.");
        body.setTextSize(16); body.setPadding(0, pad, 0, pad);
        layout.addView(body);
        Button notifications = new Button(this);
        notifications.setText("Open notification access settings");
        notifications.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)));
        layout.addView(notifications);
        setContentView(layout);
    }
}
