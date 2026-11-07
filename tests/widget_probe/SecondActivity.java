/* SPDX-License-Identifier: Apache-2.0 */
package dev.dan.androidsubsystem.widgetprobe;

import android.app.Activity;
import android.os.Bundle;
import android.widget.LinearLayout;
import android.widget.TextView;

/** A second task-stack entry makes premature widget restoration observable. */
public final class SecondActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout content = ProbeActivity.content(this, "Widget Probe: Second Screen");
        TextView details = new TextView(this);
        details.setText(ProbeActivity.details(this)
                + "\n\nAndroid Back should return to the app screen before returning to the widget.");
        content.addView(details);
        setContentView(content);
    }
}
