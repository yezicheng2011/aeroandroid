/* SPDX-License-Identifier: Apache-2.0 */
package dev.dan.androidsubsystem.widgetprobe;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.appwidget.AppWidgetProviderInfo;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.widget.RemoteViews;

/** Original, dependency-free fixture exercising the public AppWidget contract. */
public final class WidgetProbeProvider extends AppWidgetProvider {
    static final String ACTION_INCREMENT = "dev.dan.androidsubsystem.widgetprobe.INCREMENT";
    static final String EXTRA_ITEM = "item";

    static SharedPreferences preferences(Context context) {
        return context.getSharedPreferences("widget-probe", Context.MODE_PRIVATE);
    }

    static int count(Context context, int id) {
        return preferences(context).getInt("count_" + id, 0);
    }

    @Override public void onUpdate(Context context, AppWidgetManager manager, int[] ids) {
        for (int id : ids) update(context, manager, id);
    }

    @Override public void onAppWidgetOptionsChanged(Context context, AppWidgetManager manager,
            int id, Bundle options) {
        update(context, manager, id);
    }

    @Override public void onDeleted(Context context, int[] ids) {
        SharedPreferences.Editor editor = preferences(context).edit();
        for (int id : ids) editor.remove("count_" + id).remove("label_" + id);
        editor.apply();
    }

    @Override public void onReceive(Context context, Intent intent) {
        if (ACTION_INCREMENT.equals(intent.getAction())) {
            int id = intent.getIntExtra(AppWidgetManager.EXTRA_APPWIDGET_ID,
                    AppWidgetManager.INVALID_APPWIDGET_ID);
            AppWidgetManager manager = AppWidgetManager.getInstance(context);
            AppWidgetProviderInfo info = manager.getAppWidgetInfo(id);
            if (info != null && new ComponentName(context, WidgetProbeProvider.class).equals(info.provider)) {
                preferences(context).edit().putInt("count_" + id, count(context, id) + 1).apply();
                update(context, manager, id);
            }
            return;
        }
        super.onReceive(context, intent);
    }

    static void update(Context context, AppWidgetManager manager, int id) {
        RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.widget_probe);
        String label = preferences(context).getString("label_" + id, "Widget Probe");
        views.setTextViewText(R.id.title, label + " #" + id);
        views.setTextViewText(R.id.counter, "Count: " + count(context, id));
        Bundle options = manager.getAppWidgetOptions(id);
        views.setTextViewText(R.id.dimensions, "Size: "
                + options.getInt(AppWidgetManager.OPTION_APPWIDGET_MIN_WIDTH) + "-"
                + options.getInt(AppWidgetManager.OPTION_APPWIDGET_MAX_WIDTH) + " x "
                + options.getInt(AppWidgetManager.OPTION_APPWIDGET_MIN_HEIGHT) + "-"
                + options.getInt(AppWidgetManager.OPTION_APPWIDGET_MAX_HEIGHT) + " dp");

        Intent increment = new Intent(context, WidgetProbeProvider.class)
                .setAction(ACTION_INCREMENT).putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, id);
        views.setOnClickPendingIntent(R.id.increment, PendingIntent.getBroadcast(context, id,
                increment, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));

        Intent open = new Intent(context, ProbeActivity.class)
                .setData(Uri.parse("widget-probe://widget/" + id))
                .putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, id);
        views.setOnClickPendingIntent(R.id.open_app, PendingIntent.getActivity(context, id,
                open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));

        Intent listIntent = new Intent(context, ProbeActivity.class)
                .setData(Uri.parse("widget-probe://widget/" + id + "/items"))
                .putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, id);
        // Mutable only for collection fill-in extras; the destination is explicitly scoped.
        views.setPendingIntentTemplate(R.id.items, PendingIntent.getActivity(context, id,
                listIntent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_MUTABLE));
        RemoteViews.RemoteCollectionItems.Builder items =
                new RemoteViews.RemoteCollectionItems.Builder()
                        .setHasStableIds(true).setViewTypeCount(1);
        for (int item = 1; item <= 30; item++) {
            RemoteViews row = new RemoteViews(context.getPackageName(), R.layout.widget_probe_item);
            row.setTextViewText(R.id.item, "Item " + item + " - count " + count(context, id));
            row.setOnClickFillInIntent(R.id.item, new Intent().putExtra(EXTRA_ITEM, item));
            items.addItem(item, row);
        }
        views.setRemoteAdapter(R.id.items, items.build());
        manager.updateAppWidget(id, views);
    }
}
