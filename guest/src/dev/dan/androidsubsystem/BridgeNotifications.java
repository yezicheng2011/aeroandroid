package dev.dan.androidsubsystem;

import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import android.app.Notification;
import android.content.SharedPreferences;
import org.json.JSONArray;
import org.json.JSONObject;

public final class BridgeNotifications extends NotificationListenerService {
    @Override public void onNotificationPosted(StatusBarNotification n) { record(n, false); }
    @Override public void onNotificationRemoved(StatusBarNotification n) { record(n, true); }
    private synchronized void record(StatusBarNotification sbn, boolean removed) {
        if (getPackageName().equals(sbn.getPackageName())) return;
        Notification n = sbn.getNotification();
        // Ongoing notifications are often silent service status; avoid flooding the desktop.
        if (!removed && (n.flags & Notification.FLAG_ONGOING_EVENT) != 0) return;
        try {
            SharedPreferences prefs = getSharedPreferences("bridge", 0);
            JSONArray previous = new JSONArray(prefs.getString("events", "[]"));
            JSONArray events = new JSONArray();
            for (int i = Math.max(0, previous.length() - 59); i < previous.length(); i++) events.put(previous.get(i));
            JSONObject event = new JSONObject();
            event.put("id", java.util.UUID.randomUUID().toString());
            event.put("key", sbn.getKey()); event.put("package", sbn.getPackageName());
            event.put("removed", removed); event.put("timestamp", System.currentTimeMillis());
            CharSequence title = n.extras.getCharSequence(Notification.EXTRA_TITLE, "");
            CharSequence text = n.extras.getCharSequence(Notification.EXTRA_BIG_TEXT);
            if (text == null) text = n.extras.getCharSequence(Notification.EXTRA_TEXT, "");
            event.put("title", title.toString()); event.put("body", text.toString());
            events.put(event);
            prefs.edit().putString("events", events.toString()).apply();
        } catch (org.json.JSONException ignored) { }
    }
}
