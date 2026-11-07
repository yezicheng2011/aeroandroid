# SIP phone and messaging

SIP Phone and SIP Messages use your own SIP account instead of the emulator's cellular modem. The client is
original aeroandroid Java code under Apache-2.0, with no third-party SIP or codec dependency.
It does not rely on Android's deprecated `android.net.sip` service.

## Set up an account

1. Start Android and open **Mac Bridge**, then **SIP account**.
2. Enter your provider's server, port, domain, username, password and display name. Use the host/domain values
   supplied by your provider; a phone number alone is not an account configuration.
3. Prefer TLS with the provider's TLS port. TCP is available only when explicitly selected; it does not encrypt signaling.
4. Save, then connect. A foreground notification keeps registration visible. Disconnect when you do not want
   to receive calls or messages.
5. Open **SIP Phone** to dial or answer; allow Android microphone access when asked. Allow macOS microphone
   access for the subsystem/emulator when macOS prompts.
6. Open **SIP Messages** to send a text to a SIP address or a number supported by your provider.

The matching bridge install attempts to select the SIP client for Android's Phone and SMS roles. If a role is
unavailable or Android does not allow automatic selection, use the default-app buttons in SIP Phone and SIP Messages.
The original system apps are not deleted. Dial and send-to intents resolve to the SIP client once selected;
the SIP screens never silently fall back to carrier calling or texting. Phone and Messages share the account
in the Mac Bridge APK. Direct cellular `ACTION_CALL`/`TelecomManager.placeCall` requests from other apps are
not transparently rewritten into SIP, and system-managed/emergency calls are left to Android.

Passwords are encrypted with a key held in Android Keystore; other account fields and bounded message history
remain in app-private storage. They are not stored in the Git repository or sent to a project service.
Registration credentials are sent only to the configured provider, with normal TLS certificate/hostname validation
when TLS is selected. Uninstalling the bridge or resetting Android can remove the account and its encryption key.

## What the provider must support

- A persistent TCP or TLS SIP registration connection for incoming signaling.
- SIP voice calls with G.711 PCMU or PCMA and ordinary RTP media.
- SIP MESSAGE with `text/plain` for messaging. The app reports provider acceptance or rejection, not a carrier delivery receipt.
- For an account behind the emulator's NAT, connection reuse and symmetric RTP support. The bridge does not implement ICE,
  TURN, STUN discovery or a full SIP outbound proxy configuration UI.

SIP MESSAGE is not carrier SMS by itself. Sending to or receiving from an ordinary mobile number requires a
provider-supplied SMS gateway and any provider-specific addressing rules. A voice-only account may reject messages.
MMS, attachments and carrier delivery receipts are not implemented.

## Current voice scope

The client supports one active call, incoming/outgoing SIP signaling, Digest registration and authentication,
G.711 audio through Android's audio APIs, and call termination. TLS protects signaling only: RTP media is not
SRTP-encrypted. Use it with a compatible, trusted provider/network and do not assume end-to-end encryption.

Conference calls, transfers, DTMF, video, emergency service calling, WebRTC interoperability and cellular/SIM
services are outside the current implementation. This is not an emergency-calling replacement. Real provider
interop, NAT behavior and two-way Mac microphone/speaker quality need acceptance testing before relying on it.

## Validation

Host-JVM tests use a local TCP SIP peer to exercise message framing, Unicode text, authentication, registration,
call setup and hangup. G.711 and RTP helpers are tested independently. CI also compiles the full guest against
the pinned Android API and builds the native Mac UI. No private SIP account is needed for those tests.

On a Mac, validate registration over the selected transport, incoming/outgoing calls, mute/hangup, two-way audio,
incoming/outgoing text, rejected messages, disconnect/reconnect, default Phone/Messages intents and notification
behavior. Use your provider's test destination; no real-world call is placed by the repository's automated tests.
