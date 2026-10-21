package dev.dan.androidsubsystem.graphicsprobe;
import android.app.Activity;
import android.os.Bundle;
import android.graphics.Color;
import android.view.MotionEvent;
import android.view.KeyEvent;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.EditText;

/** A real Android application for stripped ATD images and visual Mac acceptance. */
public final class ProbeActivity extends Activity {
    TextView status;
    int touches, keys;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout root = new LinearLayout(this); root.setOrientation(1);
        root.setPadding(24,24,24,24); root.setBackgroundColor(Color.WHITE);
        TextView title = new TextView(this); title.setText("Graphics Probe / Android 16");
        title.setTextColor(Color.BLACK); title.setTextSize(25); root.addView(title);
        for (int color : new int[]{Color.RED, Color.GREEN, Color.BLUE}) {
            TextView bar = new TextView(this); bar.setBackgroundColor(color);
            root.addView(bar, new LinearLayout.LayoutParams(-1,48));
        }
        status = new TextView(this); status.setTextSize(20); status.setTextColor(Color.BLACK);
        root.addView(status); update();
        EditText text = new EditText(this); text.setHint("Type English / 中文 here"); root.addView(text);
        setContentView(root);
    }
    void update() { status.setText("Touch: " + touches + "   Key: " + keys); }
    @Override public boolean dispatchTouchEvent(MotionEvent event) {
        if (event.getAction() == MotionEvent.ACTION_UP) { touches++; update(); }
        return super.dispatchTouchEvent(event);
    }
    @Override public boolean dispatchKeyEvent(KeyEvent event) {
        if (event.getAction() == KeyEvent.ACTION_DOWN) { keys++; update(); }
        return super.dispatchKeyEvent(event);
    }
}
