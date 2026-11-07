package dev.dan.androidsubsystem.sip;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

/** Bounded private SIP MESSAGE history; status never implies carrier delivery. */
public final class MessageStore {
    private final SharedPreferences preferences;
    public MessageStore(Context context) { preferences = context.getSharedPreferences("sip-messages", Context.MODE_PRIVATE); }
    public synchronized JSONArray messages() {
        try { return new JSONArray(preferences.getString("history", "[]")); }
        catch (JSONException e) { return new JSONArray(); }
    }
    public synchronized void add(String id, String peer, String body, boolean incoming, String status) {
        JSONArray current = messages(), next = new JSONArray();
        for (int i = Math.max(0, current.length() - 199); i < current.length(); i++) next.put(current.opt(i));
        try {
            JSONObject item = new JSONObject();
            item.put("id", id).put("peer", peer).put("body", body).put("incoming", incoming)
                .put("status", status).put("time", System.currentTimeMillis());
            next.put(item);
        } catch (JSONException ignored) { return; }
        preferences.edit().putString("history", next.toString()).apply();
    }
    public synchronized void status(String id, String status) {
        JSONArray items = messages();
        for (int i = 0; i < items.length(); i++) {
            JSONObject item = items.optJSONObject(i);
            if (item != null && id.equals(item.optString("id"))) {
                try { item.put("status", status); } catch (JSONException ignored) { }
            }
        }
        preferences.edit().putString("history", items.toString()).apply();
    }
}
