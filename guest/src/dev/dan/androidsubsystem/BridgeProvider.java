package dev.dan.androidsubsystem;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Intent;
import android.content.ComponentName;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.drawable.Drawable;
import android.app.NotificationManager;
import android.util.Base64;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;

public final class BridgeProvider extends ContentProvider {
    @Override public boolean onCreate() { return true; }
    @Override public Cursor query(Uri uri, String[] projection, String selection, String[] args, String order) {
        // Explicitly check caller as well as manifest readPermission. Never expose to arbitrary APKs.
        getContext().enforceCallingOrSelfPermission("android.permission.DUMP", "ADB shell only");
        JSONObject result = new JSONObject();
        try {
            String endpoint = uri.getLastPathSegment();
            if ("apps".equals(endpoint)) {
                JSONArray apps = new JSONArray();
                PackageManager pm = getContext().getPackageManager();
                Intent intent = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
                List<ResolveInfo> activities = pm.queryIntentActivities(intent, 0);
                java.util.HashSet<String> seen = new java.util.HashSet<>();
                for (ResolveInfo info : activities) {
                    String pkg = info.activityInfo.packageName;
                    if (!seen.add(pkg)) continue;
                    JSONObject app = new JSONObject();
                    app.put("package", pkg); app.put("label", info.loadLabel(pm).toString());
                    try {
                        Drawable icon = info.loadIcon(pm);
                        Bitmap bitmap = Bitmap.createBitmap(64, 64, Bitmap.Config.ARGB_8888);
                        Canvas canvas = new Canvas(bitmap); icon.setBounds(0, 0, 64, 64); icon.draw(canvas);
                        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                        bitmap.compress(Bitmap.CompressFormat.PNG, 100, bytes);
                        app.put("icon", Base64.encodeToString(bytes.toByteArray(), Base64.NO_WRAP));
                        bitmap.recycle();
                    } catch (RuntimeException e) { app.put("icon", ""); }
                    apps.put(app);
                }
                result.put("apps", apps);
            } else if ("notifications".equals(endpoint)) {
                result.put("notifications", new JSONArray(getContext().getSharedPreferences("bridge", 0).getString("events", "[]")));
            } else if ("status".equals(endpoint)) {
                NotificationManager manager = getContext().getSystemService(NotificationManager.class);
                result.put("notification_access", manager.isNotificationListenerAccessGranted(new ComponentName(getContext(), BridgeNotifications.class)));
            } else { throw new IllegalArgumentException("Unknown endpoint"); }
        } catch (org.json.JSONException e) { throw new IllegalStateException(e); }
        MatrixCursor cursor = new MatrixCursor(new String[]{"payload"});
        cursor.addRow(new Object[]{Base64.encodeToString(result.toString().getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP)});
        return cursor;
    }
    @Override public String getType(Uri uri) { return "application/json"; }
    @Override public android.os.Bundle call(String method, String arg, android.os.Bundle extras) {
        getContext().enforceCallingOrSelfPermission("android.permission.DUMP", "ADB shell only");
        if (!"commit".equals(method)) throw new UnsupportedOperationException();
        String text = extras == null ? "" : extras.getString("text", "");
        if (text.length() > 8192) throw new IllegalArgumentException("Text too long");
        android.os.Bundle result = new android.os.Bundle();
        result.putBoolean("accepted", BridgeIme.commit(text));
        return result;
    }
    @Override public Uri insert(Uri uri, ContentValues values) { throw new UnsupportedOperationException(); }
    @Override public int update(Uri uri, ContentValues values, String selection, String[] args) { throw new UnsupportedOperationException(); }
    @Override public int delete(Uri uri, String selection, String[] args) { throw new UnsupportedOperationException(); }
}
