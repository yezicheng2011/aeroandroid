# Widget Probe

This original Apache-2.0 fixture uses Android framework APIs without third-party dependencies. It targets API 36 and uses the API 31 `RemoteCollectionItems` collection implementation.

Build and install it into a running Android guest:

```sh
scripts/build-widget-probe.sh
adb install -r artifacts/WidgetProbe.apk
```

Add two instances of **Widget Probe** through the Mac widget picker. Complete the required Android configuration with different labels. Check these behaviors on a real guest and Mac:

1. Cancel configuration once, then create a new instance successfully.
2. Click **Increment** on one instance. Its counter and collection rows update while the other instance keeps its own count.
3. Resize either window. Its reported Android size options change, and the list remains scrollable.
4. Scroll to **Item 30** and tap it. The actual app screen displays the originating widget ID and item number.
5. Tap **Open Second Screen**. Android **Back** returns through the app screen before the widget becomes visible again.
6. Close one widget window while keeping the other open. Its live counter must continue working. Reopen the first instance and verify its label and counter persist.
7. Remove one widget instance. The other instance must retain its state. Remove the probe application and check that its widget windows can be closed safely.

The collection's mutable PendingIntent is explicitly addressed to the probe activity; it allows the framework to deliver the selected item's fill-in extras. The counter and **Open App** button use immutable PendingIntents. All interactions execute Android's real PendingIntent paths.

Building the signed APK validates resource linking and framework API compatibility. It does not replace these runtime checks.
