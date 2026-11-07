import dev.dan.androidsubsystem.sip.SipClient;
import java.io.ByteArrayOutputStream;
import java.io.Closeable;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Real TCP SIP peer tests: original test code, Apache-2.0. */
public final class SipClientTests {
    private static int assertions;
    private static void check(boolean value, String message) {
        assertions++;
        if (!value) throw new AssertionError(message);
    }
    private static <T> T take(BlockingQueue<T> queue, String message) throws Exception {
        T value = queue.poll(8, TimeUnit.SECONDS);
        check(value != null, "Timed out: " + message);
        return value;
    }
    private static final class Events implements SipClient.Listener {
        final BlockingQueue<String> states = new LinkedBlockingQueue<String>();
        final BlockingQueue<String> incoming = new LinkedBlockingQueue<String>();
        final BlockingQueue<String> ended = new LinkedBlockingQueue<String>();
        final BlockingQueue<String> messages = new LinkedBlockingQueue<String>();
        final BlockingQueue<String> statuses = new LinkedBlockingQueue<String>();
        final BlockingQueue<String> media = new LinkedBlockingQueue<String>();
        public void onState(String value) { states.add(value); }
        public void onIncomingCall(String from) { incoming.add(from); }
        public void onCallEstablished(String address, int port, int payload) { media.add(address + ":" + port + ":" + payload); }
        public void onCallEnded(String reason) { ended.add(reason); }
        public void onMessage(String from, String text) { messages.add(from + "\n" + text); }
        public void onMessageStatus(String id, boolean success, String detail) { statuses.add(id + ":" + success + ":" + detail); }
        void registered() throws Exception {
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(8);
            List<String> seen = new ArrayList<String>();
            while (System.nanoTime() < deadline) {
                String state = states.poll(200, TimeUnit.MILLISECONDS);
                if (state != null) {
                    seen.add(state);
                    if (state.toLowerCase(Locale.ROOT).equals("registered")) return;
                }
            }
            throw new AssertionError("Registration callback missing: " + seen);
        }
    }
    private static final class Frame {
        final String start;
        final Map<String, String> headers;
        final byte[] body;
        Frame(String start, Map<String, String> headers, byte[] body) { this.start = start; this.headers = headers; this.body = body; }
        String header(String name) { return headers.get(name.toLowerCase(Locale.ROOT)); }
        String text() { return new String(body, StandardCharsets.UTF_8); }
        String method() { return start.startsWith("SIP/2.0") ? header("CSeq").split(" ")[1] : start.split(" ")[0]; }
    }
    private static String line(InputStream input) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        while (true) {
            int value = input.read();
            if (value < 0) { if (bytes.size() == 0) return null; throw new EOFException("Truncated SIP line"); }
            if (value == '\n') break;
            if (value != '\r') bytes.write(value);
            if (bytes.size() > 65536) throw new IOException("SIP line too long");
        }
        return new String(bytes.toByteArray(), StandardCharsets.UTF_8);
    }
    private static Frame read(InputStream input) throws IOException {
        String start;
        do { start = line(input); } while (start != null && start.isEmpty());
        if (start == null) return null;
        Map<String, String> headers = new LinkedHashMap<String, String>();
        while (true) {
            String value = line(input);
            if (value == null) throw new EOFException("Missing SIP body");
            if (value.isEmpty()) break;
            int colon = value.indexOf(':');
            if (colon < 1) throw new IOException("Malformed header");
            headers.put(value.substring(0, colon).trim().toLowerCase(Locale.ROOT), value.substring(colon + 1).trim());
        }
        int count = Integer.parseInt(headers.get("content-length"));
        byte[] body = new byte[count];
        int offset = 0;
        while (offset < body.length) {
            int value = input.read(body, offset, body.length - offset);
            if (value < 0) throw new EOFException("Truncated SIP payload");
            offset += value;
        }
        return new Frame(start, headers, body);
    }
    private static final class Peer implements Closeable {
        final ServerSocket server;
        Socket socket;
        InputStream input;
        OutputStream output;
        Peer() throws IOException { server = new ServerSocket(0, 1, java.net.InetAddress.getByName("127.0.0.1")); server.setSoTimeout(8000); }
        int port() { return server.getLocalPort(); }
        void accept() throws IOException { socket = server.accept(); socket.setSoTimeout(8000); input = socket.getInputStream(); output = socket.getOutputStream(); }
        Frame next() throws IOException { Frame value = read(input); if (value == null) throw new EOFException("SIP client closed"); return value; }
        Frame request(String method) throws IOException {
            for (int i = 0; i < 12; i++) { Frame value = next(); if (!value.start.startsWith("SIP/2.0") && value.method().equals(method)) return value; }
            throw new IOException("No " + method + " request");
        }
        Frame response(int status, String method) throws IOException {
            for (int i = 0; i < 12; i++) { Frame value = next(); if (value.start.startsWith("SIP/2.0 " + status + " ") && value.method().equals(method)) return value; }
            throw new IOException("No " + status + " " + method + " response");
        }
        void raw(String value) throws IOException { output.write(value.getBytes(StandardCharsets.UTF_8)); output.flush(); }
        void reply(Frame request, int status, String phrase, String additional, String body) throws IOException {
            String to = request.header("To");
            if (status > 100 && !to.contains(";tag=")) to += ";tag=server-tag";
            String text = "SIP/2.0 " + status + " " + phrase + "\r\nVia: " + request.header("Via")
                + "\r\nFrom: " + request.header("From") + "\r\nTo: " + to
                + "\r\nCall-ID: " + request.header("Call-ID") + "\r\nCSeq: " + request.header("CSeq")
                + "\r\n" + additional + "Content-Length: " + body.getBytes(StandardCharsets.UTF_8).length + "\r\n\r\n" + body;
            raw(text);
        }
        public void close() throws IOException { if (socket != null) socket.close(); server.close(); }
    }
    private static SipClient client(Peer peer, Events events) {
        return new SipClient(new SipClient.Config("127.0.0.1", peer.port(), false, "example.test", "alice", "secret", "Alice"), events);
    }
    private static String digest(String value) throws Exception { return hash("MD5", value); }
    private static String hash(String algorithm, String value) throws Exception {
        byte[] result = MessageDigest.getInstance(algorithm).digest(value.getBytes(StandardCharsets.UTF_8));
        StringBuilder out = new StringBuilder();
        for (byte item : result) out.append(String.format(Locale.ROOT, "%02x", item & 255));
        return out.toString();
    }
    private static Map<String, String> digestFields(String text) {
        Map<String, String> values = new LinkedHashMap<String, String>();
        Matcher matcher = Pattern.compile("([a-zA-Z0-9_-]+)\\s*=\\s*(?:\"([^\"]*)\"|([^,\\s]+))").matcher(text);
        while (matcher.find()) values.put(matcher.group(1).toLowerCase(Locale.ROOT), matcher.group(2) != null ? matcher.group(2) : matcher.group(3));
        return values;
    }
    private static Frame register(Peer peer, Events events, boolean auth) throws Exception {
        Frame first = peer.request("REGISTER");
        check(first.start.startsWith("REGISTER sip:example.test SIP/2.0"), "REGISTER uses account domain");
        Frame finalRequest = first;
        if (auth) {
            peer.reply(first, 401, "Unauthorized", "WWW-Authenticate: Digest realm=\"example.test\", nonce=\"nonce-123\", algorithm=MD5, qop=\"auth\"\r\n", "");
            finalRequest = peer.request("REGISTER");
            String authorization = finalRequest.header("Authorization");
            check(authorization != null, "REGISTER retries with Digest authorization");
            Map<String, String> values = digestFields(authorization);
            check("alice".equals(values.get("username")), "Digest uses account username");
            check("nonce-123".equals(values.get("nonce")), "Digest uses challenge nonce");
            check("auth".equals(values.get("qop")), "Digest negotiates auth qop");
            check("00000001".equals(values.get("nc")), "Digest nonce count starts at one");
            String expected = digest(digest("alice:example.test:secret") + ":nonce-123:" + values.get("nc") + ":" + values.get("cnonce")
                + ":auth:" + digest("REGISTER:" + values.get("uri")));
            check(expected.equals(values.get("response")), "Digest response matches RFC challenge");
            check(!first.header("Via").equals(finalRequest.header("Via")), "Authenticated retry uses a new transaction branch");
            check(!first.header("CSeq").equals(finalRequest.header("CSeq")), "Authenticated retry increments CSeq");
        }
        peer.reply(finalRequest, 200, "OK", "Expires: 300\r\n", "");
        events.registered();
        return finalRequest;
    }
    private static String sdp(int port, String payloads) {
        return "v=0\r\no=pbx 1 1 IN IP4 127.0.0.1\r\ns=Test\r\nc=IN IP4 127.0.0.1\r\nt=0 0\r\nm=audio " + port
            + " RTP/AVP " + payloads + "\r\na=rtpmap:0 PCMU/8000\r\na=rtpmap:8 PCMA/8000\r\na=sendrecv\r\n";
    }
    private static String incoming(String method, String callId, int cseq, String to, String contentType, String body) {
        return method + " sip:alice@example.test SIP/2.0\r\nVia: SIP/2.0/TCP 127.0.0.1;branch=z9hG4bK-peer-" + cseq
            + "\r\nFrom: <sip:bob@example.test>;tag=caller-tag\r\nTo: " + to + "\r\nCall-ID: " + callId + "\r\nCSeq: " + cseq + " " + method
            + "\r\nContact: <sip:bob@127.0.0.1>\r\nMax-Forwards: 70\r\n" + (contentType.isEmpty() ? "" : "Content-Type: " + contentType + "\r\n")
            + "Content-Length: " + body.getBytes(StandardCharsets.UTF_8).length + "\r\n\r\n" + body;
    }
    private static void registrationAndMessages() throws Exception {
        Events events = new Events();
        try (Peer peer = new Peer()) {
            SipClient client = client(peer, events);
            try {
                client.connect(); peer.accept(); register(peer, events, true);
                String unicode = "Hello \u4e16\u754c \ud83c\udf0d";
                String id = client.sendMessage("bob", unicode);
                Frame message = peer.request("MESSAGE");
                check(message.start.startsWith("MESSAGE sip:bob@example.test SIP/2.0"), "Numeric/user target resolves against account domain");
                check(unicode.equals(message.text()), "MESSAGE preserves Unicode payload");
                check(Integer.parseInt(message.header("Content-Length")) == unicode.getBytes(StandardCharsets.UTF_8).length, "MESSAGE length counts UTF-8 bytes");
                peer.reply(message, 202, "Accepted", "", "");
                check(take(events.statuses, "outgoing message result").startsWith(id + ":true:"), "MESSAGE callback identifies accepted transaction");
                // Two frames in one write ensure stream parsing respects byte lengths and boundaries.
                peer.raw(incoming("MESSAGE", "incoming-message", 1, "<sip:alice@example.test>", "text/plain; charset=utf-8", unicode)
                    + incoming("OPTIONS", "incoming-options", 2, "<sip:alice@example.test>", "", ""));
                Frame ack = peer.response(200, "MESSAGE");
                check("incoming-message".equals(ack.header("Call-ID")), "Incoming MESSAGE receives transaction response");
                peer.response(200, "OPTIONS");
                check(take(events.messages, "incoming Unicode message").endsWith("\n" + unicode), "Incoming MESSAGE is delivered without truncation");
                boolean blocked = false;
                try { client.sendMessage("bob\r\nX-Injected: true", "x"); } catch (IllegalArgumentException | IOException expected) { blocked = true; }
                check(blocked, "CRLF target injection is rejected");
            } finally { client.close(); }
        }
    }
    private static void proxyAuthentication() throws Exception {
        Events events = new Events();
        try (Peer peer = new Peer()) {
            SipClient client = client(peer, events);
            try {
                client.connect(); peer.accept(); register(peer, events, false);
                String id = client.sendMessage("bob", "authenticate");
                Frame first = peer.request("MESSAGE");
                peer.reply(first, 407, "Proxy Authentication Required", "Proxy-Authenticate: Digest realm=\"proxy.test\", nonce=\"sha-nonce\", algorithm=SHA-256, qop=\"auth\"\r\n", "");
                Frame authenticated = peer.request("MESSAGE");
                check(authenticated.text().equals("authenticate"), "Authentication retry preserves MESSAGE payload");
                String authorization = authenticated.header("Proxy-Authorization");
                check(authorization != null, "407 uses Proxy-Authorization");
                Map<String, String> values = digestFields(authorization);
                check("SHA-256".equalsIgnoreCase(values.get("algorithm")), "Proxy Digest preserves SHA-256 algorithm");
                String expected = hash("SHA-256", hash("SHA-256", "alice:proxy.test:secret") + ":sha-nonce:" + values.get("nc") + ":" + values.get("cnonce")
                    + ":auth:" + hash("SHA-256", "MESSAGE:" + values.get("uri")));
                check(expected.equals(values.get("response")), "SHA-256 Digest matches challenge");
                check(!first.header("Via").equals(authenticated.header("Via")), "Proxy retry receives new transaction branch");
                peer.reply(authenticated, 200, "OK", "", "");
                check(take(events.statuses, "authenticated message status").startsWith(id + ":true:"), "Retry keeps the public MESSAGE transaction id");
            } finally { client.close(); }
        }
    }
    private static void outgoingCall() throws Exception {
        Events events = new Events();
        try (Peer peer = new Peer()) {
            SipClient client = client(peer, events);
            try {
                client.connect(); peer.accept(); register(peer, events, false);
                client.call("sip:bob@example.test", 42000, "127.0.0.1");
                Frame invite = peer.request("INVITE");
                check(invite.text().contains("m=audio 42000 RTP/AVP"), "Outgoing call advertises allocated RTP port");
                check(invite.text().contains("PCMU/8000"), "Outgoing call offers G.711 audio");
                Frame challenged = invite;
                peer.reply(challenged, 407, "Proxy Authentication Required", "Proxy-Authenticate: Digest realm=\"example.test\", nonce=\"call-nonce\", algorithm=MD5, qop=\"auth\"\r\n", "");
                Frame challengeAck = peer.request("ACK");
                check(challengeAck.header("Via").equals(challenged.header("Via")), "Challenge ACK uses the rejected INVITE branch");
                check(challengeAck.header("CSeq").equals(challenged.header("CSeq").replace("INVITE", "ACK")), "Challenge ACK uses rejected INVITE CSeq");
                invite = peer.request("INVITE");
                check(invite.header("Proxy-Authorization") != null, "INVITE retries proxy authentication");
                check(!invite.header("Via").equals(challenged.header("Via")), "Authenticated INVITE uses new branch");
                peer.reply(invite, 180, "Ringing", "", "");
                peer.reply(invite, 200, "OK", "Contact: <sip:bob@127.0.0.1:" + peer.port() + ";transport=tcp>\r\nContent-Type: application/sdp\r\n", sdp(43000, "0"));
                Frame ack = peer.request("ACK");
                check(ack.header("Call-ID").equals(invite.header("Call-ID")), "ACK remains in outgoing dialog");
                check(take(events.media, "outgoing media endpoint").equals("127.0.0.1:43000:0"), "SDP answer selects remote RTP endpoint and PCMU payload");
                peer.reply(invite, 200, "OK", "Contact: <sip:bob@127.0.0.1:" + peer.port() + ";transport=tcp>\r\nContent-Type: application/sdp\r\n", sdp(43000, "0"));
                Frame repeatedAck = peer.request("ACK");
                check(repeatedAck.header("CSeq").equals(ack.header("CSeq")), "Retransmitted INVITE 200 response is ACKed again");
                check(events.media.isEmpty(), "Retransmitted 200 does not start media twice");
                client.hangup();
                Frame bye = peer.request("BYE");
                check(bye.header("To").contains("server-tag"), "BYE includes remote dialog tag");
                peer.reply(bye, 407, "Proxy Authentication Required", "Proxy-Authenticate: Digest realm=\"example.test\", nonce=\"bye-nonce\", algorithm=MD5, qop=\"auth\"\r\n", "");
                Frame authenticatedBye = peer.request("BYE");
                check(authenticatedBye.header("Proxy-Authorization") != null, "Locally ended call still authenticates BYE");
                peer.reply(authenticatedBye, 200, "OK", "", "");
                take(events.ended, "outgoing call ends");
            } finally { client.close(); }
        }
    }
    private static void cancelledCall() throws Exception {
        Events events = new Events();
        try (Peer peer = new Peer()) {
            SipClient client = client(peer, events);
            try {
                client.connect(); peer.accept(); register(peer, events, false);
                client.call("bob", 46000, "127.0.0.1");
                Frame invite = peer.request("INVITE");
                peer.reply(invite, 180, "Ringing", "", "");
                client.hangup();
                Frame cancel = peer.request("CANCEL");
                check(cancel.header("Via").equals(invite.header("Via")), "CANCEL retains INVITE transaction branch");
                check(cancel.header("CSeq").equals(invite.header("CSeq").replace("INVITE", "CANCEL")), "CANCEL retains INVITE numeric CSeq");
                peer.reply(cancel, 200, "OK", "", "");
                peer.reply(invite, 487, "Request Terminated", "", "");
                Frame ack = peer.request("ACK");
                check(ack.header("CSeq").equals(invite.header("CSeq").replace("INVITE", "ACK")), "Cancelled INVITE final response is ACKed");
                take(events.ended, "cancelled call ends");
                check(events.media.isEmpty(), "A cancelled call never starts media");
            } finally { client.close(); }
        }
    }
    private static void incomingCall() throws Exception {
        Events events = new Events();
        try (Peer peer = new Peer()) {
            SipClient client = client(peer, events);
            try {
                client.connect(); peer.accept(); register(peer, events, false);
                String recordRoute = "<sip:proxy@127.0.0.1;lr>";
                peer.raw(incoming("INVITE", "incoming-call", 1, "<sip:alice@example.test>", "application/sdp", sdp(44000, "8"))
                    .replace("Max-Forwards: 70", "Record-Route: " + recordRoute + "\r\nMax-Forwards: 70"));
                check(take(events.incoming, "incoming call").contains("bob"), "Incoming call reports SIP caller");
                client.answer(45000, "127.0.0.1");
                Frame answer = peer.response(200, "INVITE");
                check(answer.text().contains("m=audio 45000 RTP/AVP"), "Answer advertises allocated RTP port");
                check(answer.header("To").contains(";tag="), "Answer creates local dialog tag");
                check(recordRoute.equals(answer.header("Record-Route")), "Incoming INVITE response preserves Record-Route");
                peer.raw(incoming("ACK", "incoming-call", 1, answer.header("To"), "", ""));
                check(take(events.media, "incoming media endpoint").equals("127.0.0.1:44000:8"), "Incoming SDP negotiates PCMA");
                peer.raw(incoming("BYE", "incoming-call", 2, answer.header("To"), "", ""));
                peer.response(200, "BYE");
                take(events.ended, "remote hangs up");
            } finally { client.close(); }
        }
    }
    private static void rejectedMessageAndMalformedStream() throws Exception {
        Events events = new Events();
        try (Peer peer = new Peer()) {
            SipClient client = client(peer, events);
            try {
                client.connect(); peer.accept(); register(peer, events, false);
                String id = client.sendMessage("bob", "denied");
                Frame message = peer.request("MESSAGE");
                peer.reply(message, 403, "Forbidden", "", "");
                check(take(events.statuses, "rejected message").startsWith(id + ":false:"), "MESSAGE errors cannot appear delivered");
                peer.raw("MESSAGE sip:alice@example.test SIP/2.0\r\nContent-Length: -1\r\n\r\n");
                // A negative body length must fail the stream rather than be treated as an empty message.
                long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(8);
                boolean failure = false;
                while (System.nanoTime() < deadline) {
                    String state = events.states.poll(250, TimeUnit.MILLISECONDS);
                    if (state != null && !state.equalsIgnoreCase("registered") && !state.equalsIgnoreCase("connecting")) { failure = true; break; }
                }
                check(failure, "Malformed framing changes the connection state");
                check(events.messages.isEmpty(), "Malformed payload is never delivered");
            } finally { client.close(); }
        }
    }
    public static void main(String[] args) throws Exception {
        registrationAndMessages();
        proxyAuthentication();
        outgoingCall();
        cancelledCall();
        incomingCall();
        rejectedMessageAndMalformedStream();
        System.out.println("SIP protocol tests passed (" + assertions + " assertions)");
    }
}
