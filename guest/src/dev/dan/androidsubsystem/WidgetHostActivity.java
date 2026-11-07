package dev.dan.androidsubsystem;

import android.app.Activity;
import android.appwidget.AppWidgetHostView;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProviderInfo;
import android.content.ActivityNotFoundException;
import android.content.ComponentName;
import android.content.Intent;
import android.os.Bundle;
import android.util.SizeF;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.TextView;
import android.window.OnBackInvokedDispatcher;
import org.json.JSONException;
import org.json.JSONObject;
import java.util.Collections;

/** Actual Android AppWidgetHostView on its own streamed display, not a widget snapshot. */
public final class WidgetHostActivity extends Activity {
    private static final int BIND = 41, CONFIGURE = 42;
    private int id;
    private FrameLayout content;
    private AppWidgetHostView widget;
    private boolean listening, resumed, waitingForResult, reconfigure, cancelled;
    private int widthDp = -1, heightDp = -1;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        content = new FrameLayout(this);
        content.setBackgroundColor(android.graphics.Color.TRANSPARENT);
        setContentView(content);
        id = getIntent().getIntExtra(AppWidgetManager.EXTRA_APPWIDGET_ID,
            getIntent().getIntExtra("appWidgetId", AppWidgetManager.INVALID_APPWIDGET_ID));
        waitingForResult = state != null && state.getBoolean("waiting");
        reconfigure = state == null ? getIntent().getBooleanExtra("reconfigure", false) : state.getBoolean("reconfigure");
        cancelled = state != null && state.getBoolean("cancelled");
        content.addOnLayoutChangeListener((view, left, top, right, bottom, oldLeft, oldTop, oldRight, oldBottom) -> reportSize());
        // Back from a provider's Activity returns here; Back on the desktop itself must not destroy it.
        getOnBackInvokedDispatcher().registerOnBackInvokedCallback(OnBackInvokedDispatcher.PRIORITY_DEFAULT, () -> { });
    }
    private void state(boolean active) { WidgetBridge.activityState(this, id, active, waitingForResult); }
    private void message(String text) {
        widget = null;
        content.removeAllViews();
        TextView label = new TextView(this); label.setText(text); label.setTextSize(16);
        label.setTextColor(android.graphics.Color.WHITE); label.setBackgroundColor(0xcc20262e);
        label.setPadding(20, 20, 20, 20);
        content.addView(label, new FrameLayout.LayoutParams(-1, -1));
        state(false);
    }
    private void attach() {
        if (cancelled) return;
        try {
            JSONObject saved = WidgetBridge.info(this, id);
            AppWidgetProviderInfo info = AppWidgetManager.getInstance(this).getAppWidgetInfo(id);
            if (info == null) {
                message("Allow this app's widget when Android asks. You can cancel without changing the app.");
                if (waitingForResult) return;
                if (!saved.optBoolean("provider_available")) { message("The app that provides this widget is unavailable."); return; }
                ComponentName provider = ComponentName.unflattenFromString(saved.getString("provider"));
                Intent request = new Intent(AppWidgetManager.ACTION_APPWIDGET_BIND)
                    .putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, id)
                    .putExtra(AppWidgetManager.EXTRA_APPWIDGET_PROVIDER, provider)
                    .putExtra(AppWidgetManager.EXTRA_APPWIDGET_OPTIONS,
                        WidgetBridge.options(saved.getInt("width_dp"), saved.getInt("height_dp")));
                waitingForResult = true; state(false);
                startActivityForResult(request, BIND);
                return;
            }
            if (info.configure != null && (!saved.optBoolean("configured") || reconfigure)) {
                message("Complete this widget's Android configuration to place it on the desktop.");
                if (!waitingForResult) {
                    waitingForResult = true; state(false);
                    WidgetBridge.host(this).startAppWidgetConfigureActivityForResult(this, id, 0, CONFIGURE, null);
                }
                return;
            }
            show(info);
        } catch (JSONException | IllegalArgumentException error) {
            waitingForResult = false;
            message("This desktop widget is unavailable. Remove it in the Mac manager and add it again.");
        } catch (ActivityNotFoundException | SecurityException error) {
            waitingForResult = false;
            message("Android could not open this widget's permission or configuration screen. Remove it and try again.");
        }
    }
    private void show(AppWidgetProviderInfo info) {
        content.removeAllViews();
        // stopListening clears Android's registered views. Re-create after every resume so updates recover.
        widget = WidgetBridge.createView(this, id, info);
        ViewGroup parent = (ViewGroup) widget.getParent();
        if (parent != null) parent.removeView(widget);
        widget.setBackgroundColor(android.graphics.Color.TRANSPARENT);
        content.addView(widget, new FrameLayout.LayoutParams(-1, -1));
        widthDp = heightDp = -1;
        reportSize();
        state(resumed && listening && widget != null);
    }
    private void reportSize() {
        if (widget == null || content.getWidth() <= 0 || content.getHeight() <= 0) return;
        float density = getResources().getDisplayMetrics().density;
        int width = Math.max(64, Math.min(1600, Math.round(content.getWidth() / density)));
        int height = Math.max(64, Math.min(1600, Math.round(content.getHeight() / density)));
        if (width == widthDp && height == heightDp) return;
        widthDp = width; heightDp = height;
        try {
            WidgetBridge.resize(this, id, width, height);
            widget.updateAppWidgetSize(WidgetBridge.options(width, height), Collections.singletonList(new SizeF(width, height)));
        } catch (JSONException | RuntimeException error) {
            message("Android could not resize this widget. Remove it and add it again.");
        }
    }
    @Override protected void onStart() {
        super.onStart();
        try { WidgetBridge.startListening(this); listening = true; }
        catch (RuntimeException error) { message("Android could not listen for widget updates."); }
    }
    @Override protected void onResume() {
        super.onResume(); resumed = true;
        WidgetBridge.foregroundActivity(this, id);
        if (listening) attach();
    }
    @Override protected void onPause() {
        resumed = false; state(false); super.onPause();
    }
    @Override public void onConfigurationChanged(android.content.res.Configuration configuration) {
        super.onConfigurationChanged(configuration);
        // A native resize must not look like a provider Activity launch to the Mac.
        // Rebuild with the updated resources while keeping this host resumed.
        if (resumed && listening && !waitingForResult) attach();
    }
    @Override protected void onStop() {
        if (listening) { WidgetBridge.stopListening(this); listening = false; }
        super.onStop();
    }
    @Override protected void onDestroy() {
        WidgetBridge.releaseView(this, id);
        super.onDestroy();
    }
    @Override protected void onSaveInstanceState(Bundle state) {
        state.putBoolean("waiting", waitingForResult);
        state.putBoolean("reconfigure", reconfigure);
        state.putBoolean("cancelled", cancelled);
        super.onSaveInstanceState(state);
    }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != BIND && request != CONFIGURE) return;
        waitingForResult = false;
        if (result != RESULT_OK || (request == BIND && AppWidgetManager.getInstance(this).getAppWidgetInfo(id) == null)) {
            if (request == CONFIGURE && reconfigure) {
                try {
                    if (WidgetBridge.info(this, id).optBoolean("configured")) { reconfigure = false; state(false); return; }
                } catch (JSONException | IllegalArgumentException ignored) { }
            }
            try { WidgetBridge.delete(this, id); } catch (JSONException | IllegalArgumentException ignored) { }
            cancelled = true;
            message(request == BIND ? "Widget permission was cancelled. Add the widget again from the Mac manager."
                                   : "Widget configuration was cancelled. Add the widget again from the Mac manager.");
            return;
        }
        try {
            if (request == CONFIGURE) { WidgetBridge.configured(this, id); reconfigure = false; }
            state(false);
            if (resumed) attach();
        } catch (JSONException | IllegalArgumentException error) { message("The widget could not save its configuration."); }
    }
}
