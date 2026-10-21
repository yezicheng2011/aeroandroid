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
        body.setText("安卓子系统 · 桌面桥接\n\n开启通知访问后，Mac 管理应用可以将安卓通知转发到 macOS 通知中心。\n\n通知内容只经过本机 ADB，不上传网络。可以随时在安卓设置里关闭通知访问。\n\n应用图标和名称无需开启通知访问。");
        body.setTextSize(16); body.setPadding(0, pad, 0, pad);
        layout.addView(body);
        Button notifications = new Button(this);
        notifications.setText("打开通知访问设置");
        notifications.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)));
        layout.addView(notifications);
        setContentView(layout);
    }
}
