package dev.dan.androidsubsystem;

import android.app.Activity;
import android.os.Bundle;
import android.content.Intent;
import android.provider.Settings;
import android.net.Uri;
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
        TextView storage = new TextView(this);
        storage.setText("Mac folders shared in the Mac manager appear in Android's file picker under Mac. Files open and save directly in the original folder, without importing or exporting copies. Only folders you choose on the Mac are shared. Use an app's Open or Save command to grant it access to a file or folder.");
        storage.setPadding(0, pad, 0, pad);
        layout.addView(storage);
        Button files = new Button(this);
        files.setText("Browse Mac files");
        files.setOnClickListener(v -> startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT)
            .addCategory(Intent.CATEGORY_OPENABLE).setType("*/*"), 1));
        layout.addView(files);
        Button phone = new Button(this);
        phone.setText("SIP Phone");
        phone.setOnClickListener(v -> startActivity(new Intent(this, dev.dan.androidsubsystem.sip.PhoneActivity.class)));
        layout.addView(phone);
        Button messages = new Button(this);
        messages.setText("SIP Messages");
        messages.setOnClickListener(v -> startActivity(new Intent(this, dev.dan.androidsubsystem.sip.MessagesActivity.class)));
        layout.addView(messages);
        setContentView(layout);
    }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == 1 && result == RESULT_OK && data != null && data.getData() != null) {
            Uri uri = data.getData();
            Intent view = new Intent(Intent.ACTION_VIEW).setDataAndType(uri, getContentResolver().getType(uri))
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            if (view.resolveActivity(getPackageManager()) != null) startActivity(view);
        }
    }
}
