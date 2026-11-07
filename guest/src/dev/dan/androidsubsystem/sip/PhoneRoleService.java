package dev.dan.androidsubsystem.sip;

import android.telecom.Call;
import android.telecom.InCallService;

/** Default-dialer eligibility. Cellular calls are never bridged into SIP implicitly. */
public final class PhoneRoleService extends InCallService {
    @Override public void onCallAdded(Call call) {
        super.onCallAdded(call);
        // SIP Phone owns explicit VoIP calls. Never disconnect or redirect OS-managed calls,
        // including the platform's emergency-call fallback, from this eligibility endpoint.
    }
}
