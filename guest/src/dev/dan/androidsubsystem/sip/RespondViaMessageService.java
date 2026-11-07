package dev.dan.androidsubsystem.sip;

import android.app.Service;
import android.content.Intent;
import android.os.IBinder;

/** System-only quick replies use the same SIP account and server status semantics. */
public final class RespondViaMessageService extends Service {
    @Override public int onStartCommand(Intent intent, int flags, int id) {
        if (intent != null && intent.getData() != null) {
            String body = intent.getStringExtra(Intent.EXTRA_TEXT);
            if (body != null && !body.isEmpty()) {
                try {
                    SipService.command(this, SipService.SEND, SipScreens.recipient(intent.getData().getSchemeSpecificPart()), body);
                } catch (RuntimeException error) {
                    new MessageStore(this).add(java.util.UUID.randomUUID().toString(),
                        intent.getData().getSchemeSpecificPart(), body, false, "Failed: open SIP Messages to connect your account");
                }
            }
        }
        stopSelf(id); return START_NOT_STICKY;
    }
    @Override public IBinder onBind(Intent intent) { return null; }
}
