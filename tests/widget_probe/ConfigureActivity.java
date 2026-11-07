/* SPDX-License-Identifier: Apache-2.0 */
package dev.dan.androidsubsystem.widgetprobe;

import android.app.Activity;
import android.appwidget.AppWidgetManager;
import android.content.Intent;
import android.os.Bundle;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Required configuration deliberately exercises Android's cancellation/result flow. */
public final class ConfigureActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        final int id = getIntent().getIntExtra(AppWidgetManager.EXTRA_APPWIDGET_ID,
                AppWidgetManager.INVALID_APPWIDGET_ID);
        final Intent result = new Intent().putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, id);
        setResult(RESULT_CANCELED, result);
        if (id == AppWidgetManager.INVALID_APPWIDGET_ID) { finish(); return; }

        LinearLayout content = ProbeActivity.content(this, "Widget Probe Configuration");
        TextView instructions = new TextView(this);
        instructions.setText("Save to finish setup. Use Android Back to cancel.");
        content.addView(instructions);
        EditText label = new EditText(this);
        label.setSingleLine(true);
        label.setHint("Widget label");
        label.setText(WidgetProbeProvider.preferences(this).getString("label_" + id, "Widget Probe"));
        content.addView(label);
        Button save = new Button(this);
        save.setText("Save Widget");
        save.setOnClickListener(view -> {
            String value = label.getText().toString().trim();
            WidgetProbeProvider.preferences(this).edit()
                    .putString("label_" + id, value.isEmpty() ? "Widget Probe" : value).apply();
            WidgetProbeProvider.update(this, AppWidgetManager.getInstance(this), id);
            setResult(RESULT_OK, result);
            finish();
        });
        content.addView(save);
        setContentView(content);
    }
}
