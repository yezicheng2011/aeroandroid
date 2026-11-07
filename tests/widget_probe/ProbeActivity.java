/* SPDX-License-Identifier: Apache-2.0 */
package dev.dan.androidsubsystem.widgetprobe;

import android.app.Activity;
import android.appwidget.AppWidgetManager;
import android.content.Intent;
import android.os.Bundle;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/** The actual PendingIntent target, including collection fill-in data. */
public final class ProbeActivity extends Activity {
    static LinearLayout content(Activity activity, String title) {
        LinearLayout content = new LinearLayout(activity);
        content.setOrientation(LinearLayout.VERTICAL);
        int padding = Math.round(20 * activity.getResources().getDisplayMetrics().density);
        content.setPadding(padding, padding, padding, padding);
        TextView heading = new TextView(activity);
        heading.setText(title);
        heading.setTextSize(24);
        content.addView(heading);
        return content;
    }

    static String details(Activity activity) {
        int id = activity.getIntent().getIntExtra(AppWidgetManager.EXTRA_APPWIDGET_ID,
                AppWidgetManager.INVALID_APPWIDGET_ID);
        int item = activity.getIntent().getIntExtra(WidgetProbeProvider.EXTRA_ITEM, -1);
        return "Widget ID: " + id + "\nCollection item: " + (item < 0 ? "none" : item)
                + "\nCount: " + WidgetProbeProvider.count(activity, id);
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout content = content(this, "Widget Probe: App Screen");
        TextView details = new TextView(this);
        details.setText(details(this)
                + "\n\nOpen the second screen, then press Android Back twice to return to the widget.");
        content.addView(details);
        Button next = new Button(this);
        next.setText("Open Second Screen");
        next.setOnClickListener(view -> {
            Intent intent = new Intent(this, SecondActivity.class);
            if (getIntent().getExtras() != null) intent.putExtras(getIntent().getExtras());
            startActivity(intent);
        });
        content.addView(next);
        setContentView(content);
    }
}
