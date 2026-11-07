package dev.dan.androidsubsystem.sip;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Role-required carrier entry points; aeroandroid messages arrive over the SIP connection. */
public final class SmsRoleReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        // No carrier SMS/MMS transport is present in this emulator. Never send a carrier fallback.
    }
}
