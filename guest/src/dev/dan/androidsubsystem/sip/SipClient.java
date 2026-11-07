package dev.dan.androidsubsystem.sip;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

/** Original Apache-2.0 SIP signaling client. TCP/TLS, one G.711 call and SIP MESSAGE. */
public final class SipClient {
    private static final int MAX_BODY = 1024 * 1024;
    private static final int MAX_HEADERS = 65536;
    private static final String ALLOW = "INVITE, ACK, CANCEL, BYE, OPTIONS, MESSAGE";

    public static final class Config {
        public final String host, domain, username, password, displayName;
        public final int port;
        public final boolean tls;
        public Config(String host, int port, boolean tls, String domain, String username, String password, String displayName) {
            this.host = clean(host, "SIP server");
            this.domain = clean(domain, "SIP domain");
            this.username = clean(username, "SIP username");
            this.password = password == null ? "" : clean(password, "SIP password");
            this.displayName = displayName == null ? "" : clean(displayName, "Display name");
            if (host.isEmpty() || domain.isEmpty() || username.isEmpty() || port < 1 || port > 65535
                    || !domain.matches("[A-Za-z0-9.\\-\\[\\]:]+")
                    || !username.matches("[A-Za-z0-9_.!~*'()+%\\-]+")
                    || host.matches(".*[\\s/<>@].*")) throw new IllegalArgumentException("Invalid SIP account");
            this.port = port; this.tls = tls;
        }
    }

    public interface Listener {
        void onState(String state);
        void onIncomingCall(String from);
        void onCallEstablished(String address, int port, int payload);
        void onCallEnded(String reason);
        void onMessage(String from, String text);
        void onMessageStatus(String id, boolean success, String detail);
    }

    private final Config config;
    private final Listener listener;
    private final Object stateLock = new Object();
    private final Object outputLock = new Object();
    private final AtomicInteger sequence = new AtomicInteger(1);
    private final Map<String, Pending> pending = new ConcurrentHashMap<>();
    private final Map<String, CachedResponse> responses = new ConcurrentHashMap<>();
    private final Map<String, CachedResponse> inviteAcks = new ConcurrentHashMap<>();
    private final String registrationId = random() + "@aeroandroid";
    private final String registrationTag = random();
    private Socket socket;
    private OutputStream output;
    private ScheduledExecutorService timer;
    private volatile boolean closed = true;
    private volatile boolean registered;
    private volatile long refreshAt;
    private volatile long lastWrite;
    private Dialog dialog;

    public SipClient(Config config, Listener listener) {
        if (config == null || listener == null) throw new IllegalArgumentException("A SIP account and listener are required");
        this.config = config; this.listener = listener;
    }

    public void connect() throws IOException {
        synchronized (stateLock) {
            if (!closed) return;
            listener.onState("connecting");
            Socket connection = config.tls ? SSLSocketFactory.getDefault().createSocket() : new Socket();
            try {
                connection.connect(new InetSocketAddress(config.host, config.port), 10000);
                connection.setTcpNoDelay(true);
                connection.setKeepAlive(true);
                if (connection instanceof SSLSocket) {
                    SSLSocket secure = (SSLSocket) connection;
                    SSLParameters parameters = secure.getSSLParameters();
                    parameters.setEndpointIdentificationAlgorithm("HTTPS");
                    secure.setSSLParameters(parameters);
                    secure.setSoTimeout(10000);
                    secure.startHandshake();
                    secure.setSoTimeout(0);
                }
                socket = connection;
                output = connection.getOutputStream();
                closed = false;
                registered = false;
                refreshAt = Long.MAX_VALUE;
                timer = Executors.newSingleThreadScheduledExecutor(r -> {
                    Thread thread = new Thread(r, "SIP maintenance"); thread.setDaemon(true); return thread;
                });
                Thread reader = new Thread(() -> readLoop(connection), "SIP signaling");
                reader.setDaemon(true); reader.start();
                timer.scheduleAtFixedRate(this::maintain, 1, 1, TimeUnit.SECONDS);
                register();
            } catch (IOException | RuntimeException error) {
                try { connection.close(); } catch (IOException ignored) { }
                fail("SIP connection failed");
                throw error;
            }
        }
    }

    public String getLocalAddress() throws IOException {
        synchronized (stateLock) {
            requireConnected();
            return socket.getLocalAddress().getHostAddress();
        }
    }

    private String localEndpoint() throws IOException {
        requireConnected();
        String address = socket.getLocalAddress().getHostAddress();
        return (address.indexOf(':') >= 0 ? "[" + address + "]" : address) + ":" + socket.getLocalPort();
    }

    private String ownUri() { return "sip:" + config.username + "@" + config.domain; }
    private String contact() throws IOException {
        return "<sip:" + config.username + "@" + localEndpoint() + ";transport=" + (config.tls ? "tls" : "tcp") + ">";
    }
    private String from(String tag) {
        return (config.displayName.isEmpty() ? "" : quote(config.displayName) + " ") + "<" + ownUri() + ">;tag=" + tag;
    }
    private void register() throws IOException {
        Pending request = new Pending("REGISTER", "sip:" + config.domain, registrationId, sequence.getAndIncrement());
        request.from = from(registrationTag);
        request.to = "<" + ownUri() + ">";
        request.expires = 600;
        transmit(request);
        refreshAt = Long.MAX_VALUE;
    }

    public void call(String target, int localRtpPort, String localAddress) throws IOException {
        String uri = target(target);
        String offer = sdp(localRtpPort, localAddress, -1);
        synchronized (stateLock) {
            requireRegistered();
            if (dialog != null) throw new IOException("Another SIP call is active");
            Dialog next = new Dialog();
            next.callId = random() + "@aeroandroid";
            next.localTag = random(); next.remoteTarget = uri;
            next.localFrom = from(next.localTag); next.remoteTo = "<" + uri + ">";
            Pending request = new Pending("INVITE", uri, next.callId, sequence.getAndIncrement());
            request.from = next.localFrom; request.to = next.remoteTo;
            request.body = offer.getBytes(StandardCharsets.UTF_8); request.type = "application/sdp";
            request.dialog = next; next.invite = request;
            dialog = next;
            try { transmit(request); } catch (IOException error) { dialog = null; throw error; }
        }
    }

    public void answer(int localRtpPort, String localAddress) throws IOException {
        synchronized (stateLock) {
            requireConnected();
            Dialog current = dialog;
            if (current == null || !current.incoming || current.accepted) throw new IOException("No incoming SIP call to answer");
            String answer = sdp(localRtpPort, localAddress, current.media.payload);
            current.accepted = true;
            respond(current.incomingInvite, 200, "OK", current.localTag, answer.getBytes(StandardCharsets.UTF_8), "application/sdp");
            current.acceptedAt = System.currentTimeMillis();
        }
    }

    public void hangup() throws IOException {
        synchronized (stateLock) {
            Dialog current = dialog;
            if (current == null) return;
            if (current.established || (current.incoming && current.accepted)) {
                sendBye(current);
                endCall(current, "Call ended");
            } else if (current.incoming) {
                respond(current.incomingInvite, 486, "Busy Here", current.localTag, null, null);
                endCall(current, "Call declined");
            } else {
                current.cancelled = true;
                // CANCEL follows a provisional response; otherwise remember the user's intent.
                if (current.provisional) sendCancel(current);
                endCall(current, "Call cancelled");
            }
        }
    }

    public String sendMessage(String target, String text) throws IOException {
        String uri = target(target);
        if (text == null || text.getBytes(StandardCharsets.UTF_8).length > 65536) throw new IOException("Message exceeds 64 KiB");
        synchronized (stateLock) {
            requireRegistered();
            Pending request = new Pending("MESSAGE", uri, random() + "@aeroandroid", sequence.getAndIncrement());
            request.from = from(random()); request.to = "<" + uri + ">";
            request.body = text.getBytes(StandardCharsets.UTF_8); request.type = "text/plain; charset=utf-8";
            request.messageId = random();
            transmit(request);
            return request.messageId;
        }
    }

    public void close() {
        synchronized (stateLock) {
            if (closed) return;
            // Do not perform blocking unregister transactions during Android service shutdown.
            disconnect("disconnected");
        }
    }

    private void requireConnected() throws IOException {
        if (closed || socket == null || socket.isClosed()) throw new IOException("SIP account is not connected");
    }
    private void requireRegistered() throws IOException {
        requireConnected();
        if (!registered) throw new IOException("SIP account is not registered");
    }

    private void transmit(Pending request) throws IOException {
        requireConnected();
        request.branch = "z9hG4bK" + random();
        request.sentAt = System.currentTimeMillis();
        pending.put(request.branch, request);
        try { write(requestBytes(request)); }
        catch (IOException error) { pending.remove(request.branch); throw error; }
    }

    private byte[] requestBytes(Pending request) throws IOException {
        StringBuilder headers = new StringBuilder(request.method).append(' ').append(request.uri).append(" SIP/2.0\r\n")
                .append("Via: SIP/2.0/").append(config.tls ? "TLS" : "TCP").append(' ').append(localEndpoint())
                .append(";branch=").append(request.branch).append(";rport\r\n")
                .append("Max-Forwards: 70\r\nFrom: ").append(request.from).append("\r\nTo: ").append(request.to)
                .append("\r\nCall-ID: ").append(request.callId).append("\r\nCSeq: ").append(request.cseq).append(' ').append(request.method)
                .append("\r\nContact: ").append(contact()).append("\r\nUser-Agent: aeroandroid\r\nAllow: ").append(ALLOW).append("\r\n");
        if (request.expires >= 0) headers.append("Expires: ").append(request.expires).append("\r\n");
        for (String route : request.routes) headers.append("Route: ").append(route).append("\r\n");
        if (request.authorization != null) headers.append(request.proxyAuthorization ? "Proxy-Authorization: " : "Authorization: ")
                .append(request.authorization).append("\r\n");
        if (request.type != null) headers.append("Content-Type: ").append(request.type).append("\r\n");
        headers.append("Content-Length: ").append(request.body.length).append("\r\n\r\n");
        return packet(headers.toString(), request.body);
    }

    private void write(byte[] bytes) throws IOException {
        synchronized (outputLock) {
            if (closed || output == null) throw new IOException("SIP transport is closed");
            output.write(bytes); output.flush(); lastWrite = System.currentTimeMillis();
        }
    }

    private void readLoop(Socket connection) {
        try {
            InputStream input = new BufferedInputStream(connection.getInputStream());
            while (!closed && socket == connection) {
                Message message = readMessage(input);
                synchronized (stateLock) {
                    if (closed || socket != connection) return;
                    if (message.status > 0) response(message); else incoming(message);
                }
            }
        } catch (IOException | RuntimeException error) {
            synchronized (stateLock) {
                if (!closed && socket == connection) fail("SIP transport disconnected");
            }
        }
    }

    private void response(Message message) throws IOException {
        String branch = parameter(message.first("via"), "branch");
        Pending request = pending.get(branch);
        if (request == null) {
            CachedResponse ack = inviteAcks.get(message.first("call-id") + "|" + message.first("cseq") + "|" + parameter(message.first("to"), "tag"));
            if (ack != null && message.status >= 200) write(ack.packet);
            return;
        }
        if (!request.callId.equals(message.first("call-id"))
                || !message.first("cseq").equals(request.cseq + " " + request.method)) return;
        Dialog current = request.dialog;
        if (message.status < 200) {
            if (current != null && request.method.equals("INVITE")) {
                current.provisional = true;
                if (current.cancelled) sendCancel(current);
            }
            return;
        }
        pending.remove(branch);
        if ((message.status == 401 || message.status == 407) && request.retries == 0) {
            if (request.method.equals("INVITE")) acknowledgeFailure(request, message);
            String challenge = message.first(message.status == 407 ? "proxy-authenticate" : "www-authenticate");
            try {
                request.authorization = digest(challenge, request.method, request.uri);
            } catch (IOException error) {
                rejected(request, "SIP authentication is not supported by this server"); return;
            }
            request.proxyAuthorization = message.status == 407;
            request.retries++;
            request.cseq = sequence.getAndIncrement();
            if (request.method.equals("INVITE") && current != null && current.cancelled) { endCall(current, "Call cancelled"); return; }
            transmit(request);
            return;
        }
        boolean success = message.status >= 200 && message.status < 300;
        if (request.method.equals("REGISTER")) {
            if (success) {
                registered = true;
                int expiry = expiry(message, 600);
                refreshAt = System.currentTimeMillis() + Math.max(1, expiry * 8L / 10) * 1000;
                listener.onState("registered");
            } else rejected(request, "Registration rejected (" + message.status + ")");
        } else if (request.method.equals("MESSAGE")) {
            listener.onMessageStatus(request.messageId, success, success ? "Accepted by SIP server" : "Message rejected (" + message.status + ")");
        } else if (request.method.equals("INVITE") && current != null) {
            if (!success) {
                acknowledgeFailure(request, message);
                endCall(current, "Call rejected (" + message.status + ")");
                return;
            }
            current.remoteTo = message.first("to");
            current.remoteTag = parameter(current.remoteTo, "tag");
            String remoteContact = address(message.first("contact"));
            if (!remoteContact.isEmpty()) current.remoteTarget = safeUri(remoteContact);
            current.routes = routeHeaders(message, true);
            Media media;
            try { media = media(message); }
            catch (IOException error) {
                sendAck(current, request.cseq);
                sendBye(current); endCall(current, "Unsupported audio offer"); return;
            }
            current.media = media;
            current.established = true;
            sendAck(current, request.cseq);
            if (current.cancelled) { sendBye(current); endCall(current, "Call cancelled"); }
            else listener.onCallEstablished(media.address, media.port, media.payload);
        }
    }

    private void rejected(Pending request, String reason) {
        if (request.method.equals("REGISTER")) {
            registered = false; refreshAt = Long.MAX_VALUE; listener.onState("error: " + reason);
        } else if (request.method.equals("MESSAGE")) listener.onMessageStatus(request.messageId, false, reason);
        else if (request.dialog != null) endCall(request.dialog, reason);
    }

    private void incoming(Message message) throws IOException {
        String method = message.method;
        String cacheKey = message.transaction();
        CachedResponse cached = responses.get(cacheKey);
        if (cached != null && !method.equals("ACK")) { write(cached.packet); return; }
        if (message.first("via").isEmpty() || message.first("from").isEmpty() || message.first("to").isEmpty()
                || message.first("call-id").isEmpty() || !message.first("cseq").matches("[0-9]+ " + method)) {
            throw new IOException("Malformed SIP request");
        }
        if (method.equals("OPTIONS")) { respond(message, 200, "OK", null, null, null); return; }
        if (method.equals("MESSAGE")) {
            if (!message.first("content-type").toLowerCase(Locale.ROOT).startsWith("text/plain")) {
                respond(message, 415, "Unsupported Media Type", null, null, null); return;
            }
            if (message.body.length > 65536) { respond(message, 413, "Content Too Large", null, null, null); return; }
            respond(message, 200, "OK", null, null, null);
            listener.onMessage(address(message.first("from")), new String(message.body, StandardCharsets.UTF_8));
            return;
        }
        Dialog current = dialog;
        if (method.equals("INVITE")) {
            if (current != null) { respond(message, 486, "Busy Here", null, null, null); return; }
            Media audio;
            try { audio = media(message); }
            catch (IOException error) { respond(message, 488, "Not Acceptable Here", null, null, null); return; }
            Dialog next = new Dialog();
            next.incoming = true; next.incomingInvite = message; next.media = audio;
            next.callId = message.first("call-id"); next.localTag = random();
            next.remoteTag = parameter(message.first("from"), "tag");
            next.localFrom = withTag(message.first("to"), next.localTag); next.remoteTo = message.first("from");
            String remoteContact = address(message.first("contact"));
            next.remoteTarget = safeUri(remoteContact.isEmpty() ? address(next.remoteTo) : remoteContact);
            next.routes = routeHeaders(message, false);
            dialog = next;
            respond(message, 180, "Ringing", next.localTag, null, null);
            listener.onIncomingCall(address(message.first("from")));
            return;
        }
        if (current == null || !current.callId.equals(message.first("call-id"))) {
            if (!method.equals("ACK")) respond(message, 481, "Call/Transaction Does Not Exist", null, null, null);
            return;
        }
        if (method.equals("CANCEL") && current.incoming) {
            if (!message.first("cseq").split(" ")[0].equals(current.incomingInvite.first("cseq").split(" ")[0])
                    || !parameter(message.first("via"), "branch").equals(parameter(current.incomingInvite.first("via"), "branch"))) {
                respond(message, 481, "Call/Transaction Does Not Exist", null, null, null); return;
            }
            respond(message, 200, "OK", current.localTag, null, null);
            if (!current.accepted) {
                respond(current.incomingInvite, 487, "Request Terminated", current.localTag, null, null);
                endCall(current, "Caller cancelled");
            }
        } else if (method.equals("ACK") && current.incoming && current.accepted && !current.established) {
            if (!current.localTag.equals(parameter(message.first("to"), "tag"))
                    || !current.remoteTag.equals(parameter(message.first("from"), "tag"))
                    || !message.first("cseq").split(" ")[0].equals(current.incomingInvite.first("cseq").split(" ")[0])) return;
            current.established = true;
            listener.onCallEstablished(current.media.address, current.media.port, current.media.payload);
        } else if (method.equals("BYE")) {
            if (!current.localTag.equals(parameter(message.first("to"), "tag"))
                    || !current.remoteTag.equals(parameter(message.first("from"), "tag"))) {
                respond(message, 481, "Call/Transaction Does Not Exist", null, null, null); return;
            }
            respond(message, 200, "OK", current.localTag, null, null);
            endCall(current, "Remote party ended the call");
        } else if (!method.equals("ACK")) respond(message, 405, "Method Not Allowed", current.localTag, null, null);
    }

    private void respond(Message request, int status, String reason, String tag, byte[] suppliedBody, String type) throws IOException {
        byte[] body = suppliedBody == null ? new byte[0] : suppliedBody;
        StringBuilder headers = new StringBuilder("SIP/2.0 ").append(status).append(' ').append(reason).append("\r\n");
        for (String via : request.all("via")) headers.append("Via: ").append(via).append("\r\n");
        if (request.method.equals("INVITE")) {
            for (String route : request.all("record-route")) headers.append("Record-Route: ").append(route).append("\r\n");
        }
        headers.append("From: ").append(request.first("from")).append("\r\nTo: ")
                .append(tag == null ? request.first("to") : withTag(request.first("to"), tag))
                .append("\r\nCall-ID: ").append(request.first("call-id")).append("\r\nCSeq: ").append(request.first("cseq"))
                .append("\r\nContact: ").append(contact()).append("\r\nAllow: ").append(ALLOW).append("\r\n");
        if (type != null) headers.append("Content-Type: ").append(type).append("\r\n");
        headers.append("Content-Length: ").append(body.length).append("\r\n\r\n");
        byte[] bytes = packet(headers.toString(), body);
        responses.put(request.transaction(), new CachedResponse(bytes));
        write(bytes);
    }

    private void acknowledgeFailure(Pending invite, Message response) throws IOException {
        Pending ack = new Pending("ACK", invite.uri, invite.callId, invite.cseq);
        ack.from = invite.from; ack.to = response.first("to"); ack.branch = invite.branch; ack.routes = invite.routes;
        byte[] bytes = requestBytes(ack);
        inviteAcks.put(invite.callId + "|" + invite.cseq + " INVITE|" + parameter(response.first("to"), "tag"), new CachedResponse(bytes));
        write(bytes);
    }
    private void sendAck(Dialog current, int cseq) throws IOException {
        Pending ack = dialogRequest(current, "ACK", cseq);
        ack.branch = "z9hG4bK" + random();
        byte[] bytes = requestBytes(ack);
        inviteAcks.put(current.callId + "|" + cseq + " INVITE|" + parameter(current.remoteTo, "tag"), new CachedResponse(bytes));
        write(bytes);
    }
    private void sendBye(Dialog current) throws IOException {
        transmit(dialogRequest(current, "BYE", sequence.getAndIncrement()));
    }
    private void sendCancel(Dialog current) throws IOException {
        if (current.cancelSent) return;
        Pending invite = current.invite;
        Pending cancel = new Pending("CANCEL", invite.uri, invite.callId, invite.cseq);
        cancel.from = invite.from; cancel.to = invite.to; cancel.branch = invite.branch; cancel.routes = invite.routes;
        write(requestBytes(cancel)); current.cancelSent = true;
    }
    private Pending dialogRequest(Dialog current, String method, int cseq) {
        Pending request = new Pending(method, current.remoteTarget, current.callId, cseq);
        request.from = current.localFrom; request.to = current.remoteTo; request.routes = current.routes;
        request.dialog = current;
        return request;
    }
    private void endCall(Dialog current, String reason) {
        if (dialog == current) dialog = null;
        if (!current.ended) { current.ended = true; listener.onCallEnded(reason); }
    }

    private void maintain() {
        synchronized (stateLock) {
            if (closed) return;
            try {
                long now = System.currentTimeMillis();
                for (Map.Entry<String, Pending> entry : pending.entrySet()) {
                    if (now - entry.getValue().sentAt > 32000 && pending.remove(entry.getKey(), entry.getValue())) {
                        rejected(entry.getValue(), "SIP request timed out");
                    }
                }
                responses.entrySet().removeIf(entry -> now - entry.getValue().created > 64000);
                inviteAcks.entrySet().removeIf(entry -> now - entry.getValue().created > 64000);
                if (registered && now >= refreshAt) register();
                if (now - lastWrite > 25000) write("\r\n\r\n".getBytes(StandardCharsets.US_ASCII));
                Dialog current = dialog;
                if (current != null && current.incoming) {
                    if (current.accepted && !current.established && now - current.acceptedAt > 32000) {
                        sendBye(current); endCall(current, "Call acknowledgement timed out");
                    } else if (!current.accepted && now - current.created > 60000) {
                        respond(current.incomingInvite, 480, "Temporarily Unavailable", current.localTag, null, null);
                        endCall(current, "Incoming call timed out");
                    }
                }
            } catch (IOException | RuntimeException error) { fail("SIP transport disconnected"); }
        }
    }
    private void fail(String reason) { disconnect("error: " + reason); }
    private void disconnect(String state) {
        if (closed && socket == null) { listener.onState(state); return; }
        closed = true; registered = false;
        if (timer != null) { timer.shutdownNow(); timer = null; }
        Socket previous = socket; socket = null;
        synchronized (outputLock) { output = null; }
        if (previous != null) try { previous.close(); } catch (IOException ignored) { }
        if (dialog != null) endCall(dialog, "SIP connection closed");
        for (Pending request : pending.values()) {
            if (request.messageId != null) listener.onMessageStatus(request.messageId, false, "SIP connection closed");
        }
        pending.clear(); responses.clear(); inviteAcks.clear(); listener.onState(state);
    }

    private String target(String value) throws IOException {
        if (value == null) throw new IOException("Enter a SIP destination");
        String trimmed = value.trim();
        if (!trimmed.startsWith("sip:") && !trimmed.startsWith("sips:")) {
            trimmed = "sip:" + trimmed + (trimmed.indexOf('@') < 0 ? "@" + config.domain : "");
        }
        String uri = safeUri(trimmed);
        if (uri.startsWith("sips:") && !config.tls) throw new IOException("This destination requires a TLS account");
        return uri;
    }
    private static String safeUri(String value) throws IOException {
        if (value == null || value.length() > 2048 || !value.matches("sips?:[A-Za-z0-9_.!~*'()+%\\-]+@[A-Za-z0-9.\\-\\[\\]:]+(?:;[A-Za-z0-9_-]+(?:=[A-Za-z0-9._~!$&'()*+,:=@%\\[\\]\\-]+)?)*")) {
            throw new IOException("Invalid SIP destination");
        }
        return value;
    }

    private String digest(String challenge, String method, String uri) throws IOException {
        if (!challenge.regionMatches(true, 0, "Digest ", 0, 7)) throw new IOException("Unsupported SIP authentication");
        Map<String, String> values = digestParameters(challenge.substring(7));
        String realm = values.get("realm"), nonce = values.get("nonce");
        if (realm == null || nonce == null || nonce.isEmpty()) throw new IOException("Invalid SIP challenge");
        String algorithm = values.containsKey("algorithm") ? values.get("algorithm") : "MD5";
        String hashAlgorithm = algorithm.toUpperCase(Locale.ROOT);
        boolean session = hashAlgorithm.endsWith("-SESS");
        if (session) hashAlgorithm = hashAlgorithm.substring(0, hashAlgorithm.length() - 5);
        if (!hashAlgorithm.equals("MD5") && !hashAlgorithm.equals("SHA-256")) throw new IOException("Unsupported SIP digest algorithm");
        String qop = values.get("qop");
        if (qop != null) {
            boolean auth = false;
            for (String choice : qop.split(",")) if (choice.trim().equalsIgnoreCase("auth")) auth = true;
            if (!auth) throw new IOException("Unsupported SIP digest quality of protection");
            qop = "auth";
        }
        String cnonce = random(), nc = "00000001";
        String a1 = hash(hashAlgorithm, config.username + ":" + realm + ":" + config.password);
        if (session) a1 = hash(hashAlgorithm, a1 + ":" + nonce + ":" + cnonce);
        String a2 = hash(hashAlgorithm, method + ":" + uri);
        String result = hash(hashAlgorithm, a1 + ":" + nonce + ":" + (qop == null ? "" : nc + ":" + cnonce + ":auth:") + a2);
        String authorization = "Digest username=" + quote(config.username) + ", realm=" + quote(realm) + ", nonce=" + quote(nonce)
                + ", uri=" + quote(uri) + ", response=" + quote(result) + ", algorithm=" + algorithm;
        if (qop != null) authorization += ", qop=auth, nc=" + nc + ", cnonce=" + quote(cnonce);
        else if (session) authorization += ", cnonce=" + quote(cnonce);
        if (values.containsKey("opaque")) authorization += ", opaque=" + quote(values.get("opaque"));
        return authorization;
    }
    private static Map<String, String> digestParameters(String input) throws IOException {
        Map<String, String> values = new LinkedHashMap<>();
        int at = 0;
        while (at < input.length()) {
            while (at < input.length() && (input.charAt(at) == ',' || Character.isWhitespace(input.charAt(at)))) at++;
            if (at == input.length()) break;
            int equals = input.indexOf('=', at);
            if (equals < 0) throw new IOException("Invalid SIP digest parameter");
            String name = input.substring(at, equals).trim().toLowerCase(Locale.ROOT);
            at = equals + 1;
            while (at < input.length() && Character.isWhitespace(input.charAt(at))) at++;
            StringBuilder value = new StringBuilder();
            if (at < input.length() && input.charAt(at) == '"') {
                at++; boolean ended = false;
                while (at < input.length()) {
                    char letter = input.charAt(at++);
                    if (letter == '"') { ended = true; break; }
                    if (letter == '\\' && at < input.length()) letter = input.charAt(at++);
                    value.append(letter);
                }
                if (!ended) throw new IOException("Invalid quoted SIP digest parameter");
            } else {
                int comma = input.indexOf(',', at);
                int end = comma < 0 ? input.length() : comma;
                value.append(input.substring(at, end).trim()); at = end;
            }
            if (!name.matches("[a-z0-9_-]+")) throw new IOException("Invalid SIP digest parameter");
            values.put(name, value.toString());
            while (at < input.length() && Character.isWhitespace(input.charAt(at))) at++;
            if (at < input.length() && input.charAt(at) != ',') throw new IOException("Invalid SIP digest separator");
        }
        return values;
    }
    private static String hash(String algorithm, String value) throws IOException {
        try {
            byte[] bytes = MessageDigest.getInstance(algorithm).digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder result = new StringBuilder();
            for (byte item : bytes) result.append(String.format(Locale.ROOT, "%02x", item & 255));
            return result.toString();
        } catch (NoSuchAlgorithmException error) { throw new IOException("SIP digest algorithm is unavailable", error); }
    }

    private static String sdp(int port, String address, int payload) throws IOException {
        if (port < 1 || port > 65535 || address == null || !address.matches("[0-9A-Fa-f:.]+")) throw new IOException("Invalid local audio endpoint");
        String family = address.indexOf(':') >= 0 ? "IP6" : "IP4";
        String codecs = payload < 0 ? "0 8" : Integer.toString(payload);
        return "v=0\r\no=- " + System.currentTimeMillis() + " 1 IN " + family + " " + address + "\r\ns=aeroandroid\r\nc=IN "
                + family + " " + address + "\r\nt=0 0\r\nm=audio " + port + " RTP/AVP " + codecs
                + "\r\na=rtpmap:0 PCMU/8000\r\na=rtpmap:8 PCMA/8000\r\na=sendrecv\r\na=ptime:20\r\n";
    }
    private static Media media(Message message) throws IOException {
        if (!message.first("content-type").toLowerCase(Locale.ROOT).startsWith("application/sdp")) throw new IOException("SIP call has no SDP");
        String body = new String(message.body, StandardCharsets.UTF_8);
        String sessionAddress = null, mediaAddress = null;
        int port = 0, codec = -1;
        boolean audio = false, found = false;
        for (String line : body.split("\\r?\\n")) {
            if (line.startsWith("m=")) {
                if (found) break;
                String[] fields = line.substring(2).trim().split("\\s+");
                audio = fields.length >= 4 && fields[0].equals("audio") && fields[2].equals("RTP/AVP");
                if (audio) {
                    try { port = Integer.parseInt(fields[1]); } catch (NumberFormatException error) { throw new IOException("Invalid remote audio port"); }
                    for (int i = 3; i < fields.length; i++) if (fields[i].equals("0") || fields[i].equals("8")) { codec = Integer.parseInt(fields[i]); break; }
                    found = true;
                }
            } else if (line.startsWith("c=IN IP4 ") || line.startsWith("c=IN IP6 ")) {
                String remote = line.substring(9).trim();
                if (!found) sessionAddress = remote; else if (audio) mediaAddress = remote;
            } else if (found && (line.equals("a=inactive") || line.equals("a=sendonly") || line.equals("a=recvonly"))) {
                throw new IOException("One-way audio and hold are not supported");
            }
        }
        String remote = mediaAddress == null ? sessionAddress : mediaAddress;
        if (!found || codec < 0 || port < 1 || port > 65535 || remote == null || !remote.matches("[0-9A-Fa-f:.]+")
                || remote.equals("0.0.0.0") || remote.equals("::")) throw new IOException("No supported G.711 audio endpoint");
        return new Media(remote, port, codec);
    }

    private static Message readMessage(InputStream input) throws IOException {
        String first;
        do { first = line(input); } while (first.isEmpty());
        Message result = new Message();
        if (first.startsWith("SIP/2.0 ")) {
            if (!first.matches("SIP/2\\.0 [1-6][0-9]{2}(?: .*)?")) throw new IOException("Invalid SIP response");
            result.status = Integer.parseInt(first.substring(8, 11));
        } else {
            String[] fields = first.split(" ", -1);
            if (fields.length != 3 || !fields[0].matches("[A-Z]+") || !fields[2].equals("SIP/2.0")) throw new IOException("Invalid SIP request line");
            result.method = fields[0]; result.uri = fields[1];
        }
        int count = first.length();
        String previous = null;
        for (;;) {
            String header = line(input); count += header.length() + 2;
            if (count > MAX_HEADERS) throw new IOException("SIP headers are too large");
            if (header.isEmpty()) break;
            if ((header.charAt(0) == ' ' || header.charAt(0) == '\t') && previous != null) {
                List<String> values = result.headers.get(previous);
                int last = values.size() - 1; values.set(last, values.get(last) + " " + header.trim());
                continue;
            }
            int colon = header.indexOf(':');
            if (colon < 1) throw new IOException("Invalid SIP header");
            previous = header.substring(0, colon).trim().toLowerCase(Locale.ROOT);
            if (!previous.matches("[a-z0-9-]+")) throw new IOException("Invalid SIP header name");
            previous = canonical(previous);
            if (!result.headers.containsKey(previous)) result.headers.put(previous, new ArrayList<>());
            result.headers.get(previous).add(header.substring(colon + 1).trim());
        }
        int length = 0;
        List<String> lengths = result.all("content-length");
        if (!lengths.isEmpty()) {
            if (lengths.size() != 1 || !lengths.get(0).matches("[0-9]{1,7}")) throw new IOException("Invalid SIP content length");
            length = Integer.parseInt(lengths.get(0));
        }
        if (length > MAX_BODY) throw new IOException("SIP body is too large");
        result.body = new byte[length];
        int position = 0;
        while (position < length) {
            int size = input.read(result.body, position, length - position);
            if (size < 0) throw new EOFException("Incomplete SIP body");
            position += size;
        }
        return result;
    }
    private static String line(InputStream input) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        for (;;) {
            int value = input.read();
            if (value < 0) throw new EOFException("SIP transport closed");
            if (value == '\n') {
                byte[] line = bytes.toByteArray();
                if (line.length == 0 || line[line.length - 1] != '\r') throw new IOException("SIP requires CRLF framing");
                return new String(line, 0, line.length - 1, StandardCharsets.UTF_8);
            }
            if (value == 0 || bytes.size() >= 8192) throw new IOException("Invalid SIP header line");
            bytes.write(value);
        }
    }
    private static String canonical(String name) {
        switch (name) {
            case "v": return "via"; case "f": return "from"; case "t": return "to"; case "i": return "call-id";
            case "m": return "contact"; case "l": return "content-length"; case "c": return "content-type";
            default: return name;
        }
    }
    private static String parameter(String header, String name) {
        for (String field : header.split(";")) {
            int equals = field.indexOf('=');
            if (equals > 0 && field.substring(0, equals).trim().equalsIgnoreCase(name)) return field.substring(equals + 1).trim();
        }
        return "";
    }
    private static String address(String header) {
        int open = header.indexOf('<'), close = header.indexOf('>');
        if (open >= 0 && close > open) return header.substring(open + 1, close);
        int semicolon = header.indexOf(';'); return (semicolon < 0 ? header : header.substring(0, semicolon)).trim();
    }
    private static String withTag(String header, String tag) {
        return parameter(header, "tag").isEmpty() ? header + ";tag=" + tag : header;
    }
    private static List<String> routeHeaders(Message message, boolean reverse) {
        List<String> routes = new ArrayList<>();
        for (String value : message.all("record-route")) {
            for (String route : value.split(",(?=\\s*<)")) routes.add(route.trim());
        }
        if (reverse) Collections.reverse(routes);
        return routes;
    }
    private static int expiry(Message response, int fallback) {
        String contact = response.first("contact");
        String expires = parameter(contact, "expires");
        if (expires.isEmpty()) expires = response.first("expires");
        try { return Math.max(1, Math.min(86400, Integer.parseInt(expires))); }
        catch (NumberFormatException ignored) { return fallback; }
    }
    private static String clean(String value, String field) {
        if (value == null || value.indexOf('\r') >= 0 || value.indexOf('\n') >= 0 || value.indexOf('\0') >= 0) throw new IllegalArgumentException("Invalid " + field);
        return value;
    }
    private static String quote(String value) { return '"' + clean(value, "SIP header").replace("\\", "\\\\").replace("\"", "\\\"") + '"'; }
    private static String random() { return UUID.randomUUID().toString().replace("-", ""); }
    private static byte[] packet(String headers, byte[] body) {
        byte[] prefix = headers.getBytes(StandardCharsets.UTF_8);
        byte[] packet = new byte[prefix.length + body.length];
        System.arraycopy(prefix, 0, packet, 0, prefix.length); System.arraycopy(body, 0, packet, prefix.length, body.length);
        return packet;
    }

    private static final class Message {
        int status;
        String method, uri;
        byte[] body;
        final Map<String, List<String>> headers = new LinkedHashMap<>();
        String first(String name) { List<String> values = headers.get(name); return values == null || values.isEmpty() ? "" : values.get(0); }
        List<String> all(String name) { List<String> values = headers.get(name); return values == null ? Collections.emptyList() : values; }
        String transaction() { return parameter(first("via"), "branch") + "|" + first("call-id") + "|" + first("cseq"); }
    }
    private static final class Pending {
        final String method, uri, callId;
        int cseq, retries, expires = -1;
        String from, to, branch, authorization, type, messageId;
        boolean proxyAuthorization;
        byte[] body = new byte[0];
        List<String> routes = Collections.emptyList();
        long sentAt;
        Dialog dialog;
        Pending(String method, String uri, String callId, int cseq) { this.method = method; this.uri = uri; this.callId = callId; this.cseq = cseq; }
    }
    private static final class Dialog {
        String callId, localTag, remoteTag = "", localFrom, remoteTo, remoteTarget;
        boolean incoming, accepted, established, provisional, cancelled, cancelSent, ended;
        Message incomingInvite;
        Pending invite;
        Media media;
        long created = System.currentTimeMillis(), acceptedAt;
        List<String> routes = Collections.emptyList();
    }
    private static final class Media {
        final String address; final int port, payload;
        Media(String address, int port, int payload) { this.address = address; this.port = port; this.payload = payload; }
    }
    private static final class CachedResponse {
        final byte[] packet; final long created = System.currentTimeMillis();
        CachedResponse(byte[] packet) { this.packet = packet; }
    }
}
