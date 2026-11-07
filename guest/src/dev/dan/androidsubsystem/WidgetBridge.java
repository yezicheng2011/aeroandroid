package dev.dan.androidsubsystem;

import android.appwidget.AppWidgetHost;
import android.appwidget.AppWidgetHostView;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProviderInfo;
import android.content.ComponentName;
import android.content.Context;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.util.SizeF;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.HashMap;
import java.util.Map;
import java.util.HashSet;
import java.util.Set;
import java.lang.ref.WeakReference;

/** Original Apache-2.0 AppWidget host state. Android owns rendering and widget interactions. */
public final class WidgetBridge {
    public static final int HOST_ID = 0x4145524f;
    private static final Object LOCK = new Object();
    private static DesktopHost host;
    private static int listeners;
    private static final Map<Integer, boolean[]> activityStates = new HashMap<>();
    private static final Map<Integer, WeakReference<Context>> viewOwners = new HashMap<>();
    private static final Map<Integer, WeakReference<Context>> activityOwners = new HashMap<>();
    public static final Uri WIDGETS_URI = Uri.parse("content://dev.dan.androidsubsystem.bridge/widgets");
    private static final int MAX_WIDGETS = 64;
    private WidgetBridge() { }

    public static final class DesktopHost extends AppWidgetHost {
        DesktopHost(Context context) { super(context.getApplicationContext(), HOST_ID); }
        void releaseViews() { clearViews(); }
    }

    public static DesktopHost host(Context context) {
        synchronized (LOCK) {
            if (host == null) host = new DesktopHost(context);
            return host;
        }
    }
    public static void startListening(Context context) {
        synchronized (LOCK) {
            if (listeners++ == 0) {
                try { host(context).startListening(); }
                catch (RuntimeException error) { listeners--; throw error; }
            }
        }
    }
    public static void stopListening(Context context) {
        synchronized (LOCK) {
            if (listeners > 0 && --listeners == 0) {
                host(context).stopListening();
                host(context).releaseViews();
                viewOwners.clear();
            }
        }
    }
    /** A stopped host can otherwise retain an Activity through its native view while other hosts listen. */
    public static void releaseView(Context context, int id) {
        synchronized (LOCK) {
            WeakReference<Context> activity = activityOwners.get(id);
            if (activity != null && activity.get() == context) activityOwners.remove(id);
            WeakReference<Context> owner = viewOwners.get(id);
            // A replacement session may already be hosting this ID when an old Activity is destroyed.
            if (owner == null || owner.get() != context) return;
            viewOwners.remove(id);
            if (listeners == 0 || !ownsId(context, id)) return;
            AppWidgetProviderInfo info = AppWidgetManager.getInstance(context).getAppWidgetInfo(id);
            if (info != null) host(context).createView(context.getApplicationContext(), id, info);
        }
    }
    public static void foregroundActivity(Context context, int id) {
        synchronized (LOCK) { activityOwners.put(id, new WeakReference<>(context)); }
    }
    public static AppWidgetHostView createView(Context context, int id, AppWidgetProviderInfo provider) {
        synchronized (LOCK) {
            AppWidgetHostView view = host(context).createView(context, id, provider);
            viewOwners.put(id, new WeakReference<>(context));
            return view;
        }
    }
    private static void changed(Context context) { context.getContentResolver().notifyChange(WIDGETS_URI, null); }
    public static void activityState(Context context, int id, boolean active, boolean configuring) {
        synchronized (LOCK) {
            WeakReference<Context> owner = activityOwners.get(id);
            if (owner != null && owner.get() != null && owner.get() != context) return;
            boolean[] previous = activityStates.get(id);
            if (previous != null && previous[0] == active && previous[1] == configuring) return;
            activityStates.put(id, new boolean[] {active, configuring});
            changed(context);
        }
    }
    private static SharedPreferences preferences(Context context) {
        return context.getSharedPreferences("desktop_widgets", Context.MODE_PRIVATE);
    }
    private static JSONArray saved(Context context) {
        try { return new JSONArray(preferences(context).getString("instances", "[]")); }
        catch (JSONException error) { throw new IllegalStateException("Cannot read saved desktop widgets", error); }
    }
    private static void save(Context context, JSONArray widgets) {
        if (!preferences(context).edit().putString("instances", widgets.toString()).commit())
            throw new IllegalStateException("Cannot save desktop widgets");
    }
    private static int size(int value) {
        if (value < 64 || value > 1600) throw new IllegalArgumentException("Widget size must be 64..1600 dp");
        return value;
    }
    private static AppWidgetProviderInfo provider(Context context, String name) {
        ComponentName component = ComponentName.unflattenFromString(name == null ? "" : name);
        if (component == null) throw new IllegalArgumentException("Invalid widget provider");
        for (AppWidgetProviderInfo info : AppWidgetManager.getInstance(context).getInstalledProviders())
            if (info.provider.equals(component) && (info.widgetCategory & AppWidgetProviderInfo.WIDGET_CATEGORY_HOME_SCREEN) != 0)
                return info;
        throw new IllegalArgumentException("This app does not provide that home-screen widget");
    }
    private static int dp(Context context, int pixels) {
        return Math.max(0, Math.round(pixels / context.getResources().getDisplayMetrics().density));
    }
    private static JSONObject providerJson(Context context, AppWidgetProviderInfo info) throws JSONException {
        JSONObject result = new JSONObject();
        result.put("provider", info.provider.flattenToString());
        result.put("package", info.provider.getPackageName());
        result.put("label", info.loadLabel(context.getPackageManager()));
        CharSequence application = context.getPackageManager().getApplicationLabel(info.getActivityInfo().applicationInfo);
        result.put("app_label", application == null ? info.provider.getPackageName() : application.toString());
        result.put("min_width_dp", dp(context, info.minWidth));
        result.put("min_height_dp", dp(context, info.minHeight));
        result.put("min_resize_width_dp", dp(context, info.minResizeWidth));
        result.put("min_resize_height_dp", dp(context, info.minResizeHeight));
        result.put("max_resize_width_dp", dp(context, info.maxResizeWidth));
        result.put("max_resize_height_dp", dp(context, info.maxResizeHeight));
        result.put("resize_mode", info.resizeMode);
        result.put("has_configuration", info.configure != null);
        result.put("configuration_optional", (info.widgetFeatures & AppWidgetProviderInfo.WIDGET_FEATURE_CONFIGURATION_OPTIONAL) != 0);
        result.put("reconfigurable", (info.widgetFeatures & AppWidgetProviderInfo.WIDGET_FEATURE_RECONFIGURABLE) != 0);
        return result;
    }
    public static JSONArray providers(Context context) throws JSONException {
        List<JSONObject> items = new ArrayList<>();
        for (AppWidgetProviderInfo info : AppWidgetManager.getInstance(context).getInstalledProviders()) {
            if ((info.widgetCategory & AppWidgetProviderInfo.WIDGET_CATEGORY_HOME_SCREEN) == 0
                    || (info.widgetFeatures & AppWidgetProviderInfo.WIDGET_FEATURE_HIDE_FROM_PICKER) != 0) continue;
            items.add(providerJson(context, info));
        }
        Collections.sort(items, Comparator.comparing(value -> value.optString("app_label") + " " + value.optString("label"), String.CASE_INSENSITIVE_ORDER));
        JSONArray result = new JSONArray();
        for (JSONObject value : items) result.put(value);
        return result;
    }
    private static JSONObject record(Context context, int id) throws JSONException {
        JSONArray values = saved(context);
        for (int index = 0; index < values.length(); index++) {
            JSONObject value = values.getJSONObject(index);
            if (value.getInt("id") == id) return value;
        }
        throw new IllegalArgumentException("Widget does not belong to this desktop host");
    }
    private static boolean ownsId(Context context, int id) {
        for (int allocated : host(context).getAppWidgetIds()) if (allocated == id) return true;
        return false;
    }
    public static JSONObject info(Context context, int id) throws JSONException {
        synchronized (LOCK) {
            JSONObject value = new JSONObject(record(context, id).toString());
            if (!ownsId(context, id)) throw new IllegalArgumentException("Android removed this desktop widget");
            AppWidgetProviderInfo bound = AppWidgetManager.getInstance(context).getAppWidgetInfo(id);
            value.put("bound", bound != null);
            value.put("needs_permission", bound == null);
            boolean[] state = activityStates.get(id);
            value.put("active", state != null && state[0]);
            value.put("configuring", state != null && state[1]);
            value.put("provider_available", false);
            try {
                AppWidgetProviderInfo known = provider(context, value.getString("provider"));
                value.put("provider_available", true);
                value.put("label", known.loadLabel(context.getPackageManager()));
                value.put("reconfigurable", (known.widgetFeatures & AppWidgetProviderInfo.WIDGET_FEATURE_RECONFIGURABLE) != 0);
            } catch (IllegalArgumentException ignored) { }
            return value;
        }
    }
    public static JSONArray instances(Context context) throws JSONException {
        synchronized (LOCK) {
            JSONArray result = new JSONArray();
            JSONArray values = saved(context);
            JSONArray kept = new JSONArray();
            Set<Integer> retained = new HashSet<>();
            for (int index = 0; index < values.length(); index++) {
                int id = values.getJSONObject(index).getInt("id");
                try { result.put(info(context, id)); kept.put(values.getJSONObject(index)); retained.add(id); }
                catch (IllegalArgumentException ignored) { activityStates.remove(id); }
            }
            if (kept.length() != values.length()) save(context, kept);
            // Recover an allocation interrupted before its private record was committed.
            for (int id : host(context).getAppWidgetIds())
                if (!retained.contains(id)) host(context).deleteAppWidgetId(id);
            return result;
        }
    }
    public static Bundle options(int width, int height) {
        Bundle result = new Bundle();
        result.putInt(AppWidgetManager.OPTION_APPWIDGET_HOST_CATEGORY, AppWidgetProviderInfo.WIDGET_CATEGORY_HOME_SCREEN);
        result.putInt(AppWidgetManager.OPTION_APPWIDGET_MIN_WIDTH, size(width));
        result.putInt(AppWidgetManager.OPTION_APPWIDGET_MAX_WIDTH, width);
        result.putInt(AppWidgetManager.OPTION_APPWIDGET_MIN_HEIGHT, size(height));
        result.putInt(AppWidgetManager.OPTION_APPWIDGET_MAX_HEIGHT, height);
        ArrayList<SizeF> sizes = new ArrayList<>(); sizes.add(new SizeF(width, height));
        result.putParcelableArrayList(AppWidgetManager.OPTION_APPWIDGET_SIZES, sizes);
        return result;
    }
    public static JSONObject create(Context context, String component, int width, int height) throws JSONException {
        synchronized (LOCK) {
            size(width); size(height);
            AppWidgetProviderInfo provider = provider(context, component);
            instances(context); // Reconcile IDs removed by Android before enforcing the limit.
            JSONArray values = saved(context);
            if (values.length() >= MAX_WIDGETS) throw new IllegalStateException("Remove a desktop widget before adding more (limit 64)");
            int id = host(context).allocateAppWidgetId();
            try {
                JSONObject value = new JSONObject();
                value.put("id", id); value.put("provider", provider.provider.flattenToString());
                value.put("label", provider.loadLabel(context.getPackageManager()));
                value.put("width_dp", width); value.put("height_dp", height);
                value.put("configured", provider.configure == null || (provider.widgetFeatures & AppWidgetProviderInfo.WIDGET_FEATURE_CONFIGURATION_OPTIONAL) != 0);
                values.put(value); save(context, values);
                AppWidgetManager.getInstance(context).bindAppWidgetIdIfAllowed(id, provider.getProfile(), provider.provider, options(width, height));
                changed(context);
                return info(context, id);
            } catch (RuntimeException | JSONException error) {
                host(context).deleteAppWidgetId(id);
                removeRecord(context, id);
                throw error;
            }
        }
    }
    private static void removeRecord(Context context, int id) throws JSONException {
        JSONArray values = saved(context), kept = new JSONArray();
        for (int index = 0; index < values.length(); index++) {
            JSONObject value = values.getJSONObject(index);
            if (value.getInt("id") != id) kept.put(value);
        }
        save(context, kept);
    }
    public static void delete(Context context, int id) throws JSONException {
        synchronized (LOCK) {
            record(context, id);
            host(context).deleteAppWidgetId(id);
            removeRecord(context, id);
            activityStates.remove(id);
            viewOwners.remove(id);
            activityOwners.remove(id);
            changed(context);
        }
    }
    public static JSONObject resize(Context context, int id, int width, int height) throws JSONException {
        synchronized (LOCK) {
            JSONObject value = record(context, id); size(width); size(height);
            if (!ownsId(context, id)) throw new IllegalArgumentException("Android removed this desktop widget");
            if (value.getInt("width_dp") == width && value.getInt("height_dp") == height) return info(context, id);
            value.put("width_dp", width); value.put("height_dp", height);
            updateRecord(context, value);
            AppWidgetManager.getInstance(context).updateAppWidgetOptions(id, options(width, height));
            changed(context);
            return info(context, id);
        }
    }
    private static void updateRecord(Context context, JSONObject replacement) throws JSONException {
        JSONArray values = saved(context);
        for (int index = 0; index < values.length(); index++)
            if (values.getJSONObject(index).getInt("id") == replacement.getInt("id")) values.put(index, replacement);
        save(context, values);
    }
    public static void configured(Context context, int id) throws JSONException {
        synchronized (LOCK) {
            JSONObject value = record(context, id); value.put("configured", true); updateRecord(context, value);
            changed(context);
        }
    }
    public static int idFromRequest(JSONObject request) throws JSONException {
        Object value = request.get("id");
        if (!(value instanceof Integer) || ((Integer) value) <= 0) throw new IllegalArgumentException("Invalid widget id");
        return (Integer) value;
    }
    public static int sizeFromRequest(JSONObject request, String name) throws JSONException {
        Object value = request.get(name);
        if (!(value instanceof Integer)) throw new IllegalArgumentException("Invalid widget size");
        return size((Integer) value);
    }
}
