package dev.dan.androidsubsystem.sip;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Required default-messaging role endpoint; this emulator has no carrier MMS gateway. */
public final class MmsRoleReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) { }
}
