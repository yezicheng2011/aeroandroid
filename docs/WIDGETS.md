# Android widgets on the Mac desktop

The Widgets panel hosts real Android home-screen widgets inside live Mac desktop windows. Android's
`AppWidgetHostView` renders the provider's original RemoteViews and handles its updates, collection lists,
buttons and PendingIntents. This is not a periodically refreshed picture of a widget.

Only apps that actually publish a home-screen AppWidget provider appear in the picker. Installing an APK
does not create a widget for an app that has none. A provider hidden from ordinary Android pickers or available
only in another Android profile is not exposed by this host.

## Add and use

1. Start Android in the Mac manager and open **Widgets**.
2. Select an installed app's widget and its initial size, then choose **Add to desktop**.
3. Complete Android's normal binding permission and, if requested, the provider's configuration screen.
   Setup temporarily uses a foreground window with more room for Android's controls.
4. When setup finishes, the live widget returns to the desktop layer. Drag its title bar to move it and
   resize its window to change the Android widget's size options.
5. Click or scroll the widget as you would on Android. If a click opens the provider's app or a settings
   Activity, its exact Android navigation stays on that widget's display and the window moves to the foreground.
   Use the title-bar **Back** button to return through the Android screens; a nested stack can need several presses.

The widget's Android ID and settings persist, and the Mac saves each widget window's position and size.
Closing or hiding a desktop window keeps the widget instance; **Show** restores it. **Remove** deletes only
that widget instance, without uninstalling its app. **Configure** reopens the provider's configuration when one exists.
Cancelling a required initial permission/configuration removes the unfinished instance; cancelling reconfiguration
keeps an already configured widget.

Closing the manager's main window leaves its widgets and menu bar running. Quitting the manager or stopping
Android closes the live surfaces. Reopen the manager and start Android to restore saved widget instances.
The menu bar's management-window action opens the manager itself, rather than accidentally selecting a widget.
This does not automatically enable startup at Mac login.

## Behavior and limits

- The original Android implementation handles updates and interactions. Normal Android scheduling, permissions,
  battery policies, network access and the app's own data/service requirements still apply.
- Independent instances use independent AppWidget IDs. One shared Android host keeps updates connected across
  simultaneous windows; hiding one widget does not stop the other widgets' listeners.
- The desktop layer sits above wallpaper and below ordinary application windows. Finder icons can cover a widget
  in the same area, so place widgets away from icons. Fullscreen/Spaces behavior needs Mac acceptance.
- These are live desktop windows managed by aeroandroid, not entries in Apple's WidgetKit gallery. They require
  the manager and Android runtime to remain running and use the existing local graphics transport.
- Clicking an app-launching widget temporarily shows that Android app in the same surface. It does not translate
  its PendingIntent into a new, unrelated launch that would lose the original deep link or extras.
- Initial sizes are bounded to 64–1280 dp per axis; providers whose required minimum exceeds that range are marked
  unsupported in the picker. Native title bars impose their own small minimum window size. Android host state
  is limited to 64 saved widget instances to bound resource use.
- Resizing reports actual available dp dimensions and responsive-layout options to Android. Provider-specific
  fixed layouts may refuse to adapt or look different at a size they did not design for.
- Applications without an AppWidget provider, OEM-launcher-only integrations, private/work-profile providers,
  unsupported Google APIs and provider-specific restrictions are not guaranteed to work. There is no blanket
  claim that every third-party widget retains every feature without testing.

## Implementation and licensing

`WidgetBridge` persists host-owned IDs, validates operations and exposes DUMP-protected bridge RPC.
`WidgetHostActivity` hosts actual Android views, uses standard bind/configuration consent and publishes lifecycle
state. The shell graphics service creates one independent virtual display for each widget, validates the widget ID,
and observes lifecycle changes to promote setup/app screens and return completed widgets to the desktop.

The Mac coordinator retains windows independently from the manager UI, restores instances after Android starts,
and remembers desktop frames separately from temporary foreground frames. The transport supports small widget
frames without changing its bounded payload sizes. Nothing copies RemoteViews into a different Mac rendering API.
All new code is original Apache-2.0; no external widget library or GPL dependency is added.

## Validation

The controller suite checks provider inventory, separate IDs, mutations, stopped polling, pending setup, invalid
parameters and session geometry. CI builds the bridge and probe APKs and checks Java-to-Swift frame interoperability,
including a 64-pixel widget frame and malformed-frame rejection. Native Swift compilation and shell checks also run.

For actual interaction acceptance, build `scripts/build-widget-probe.sh`, install `artifacts/WidgetProbe.apk` and
follow [the probe checklist](../tests/widget_probe/README.md). It exercises configuration/cancellation, live counters,
two simultaneous instances, resize options, collection scrolling/item extras and a two-screen app navigation stack.
Then test the third-party widgets you use. Build and fixture tests do not establish real Mac desktop layering,
Android permission UI placement or compatibility with all providers; those still require Mac/Android acceptance.
