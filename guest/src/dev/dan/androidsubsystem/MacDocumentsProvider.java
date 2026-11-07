package dev.dan.androidsubsystem;

import android.content.Context;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.CancellationSignal;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.ParcelFileDescriptor;
import android.os.ProxyFileDescriptorCallback;
import android.os.storage.StorageManager;
import android.provider.DocumentsContract;
import android.provider.DocumentsProvider;
import android.system.ErrnoException;
import android.system.OsConstants;
import android.util.Base64;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

/** Live, user-selected Mac folders through Android's standard document picker. */
public final class MacDocumentsProvider extends DocumentsProvider {
    public static final String AUTHORITY = "dev.dan.androidsubsystem.documents";
    private static final String DIRECTORY = DocumentsContract.Document.MIME_TYPE_DIR;
    private static final int CHUNK_SIZE = 1024 * 1024;
    private static final int MAX_RESPONSE = 4 * 1024 * 1024;
    private static final String[] ROOT_COLUMNS = {
        DocumentsContract.Root.COLUMN_ROOT_ID, DocumentsContract.Root.COLUMN_DOCUMENT_ID,
        DocumentsContract.Root.COLUMN_TITLE, DocumentsContract.Root.COLUMN_SUMMARY,
        DocumentsContract.Root.COLUMN_FLAGS, DocumentsContract.Root.COLUMN_MIME_TYPES
    };
    private static final String[] DOCUMENT_COLUMNS = {
        DocumentsContract.Document.COLUMN_DOCUMENT_ID, DocumentsContract.Document.COLUMN_DISPLAY_NAME,
        DocumentsContract.Document.COLUMN_MIME_TYPE, DocumentsContract.Document.COLUMN_FLAGS,
        DocumentsContract.Document.COLUMN_SIZE, DocumentsContract.Document.COLUMN_LAST_MODIFIED
    };
    private Handler ioHandler;

    @Override public boolean onCreate() {
        HandlerThread thread = new HandlerThread("Mac file operations");
        thread.start();
        ioHandler = new Handler(thread.getLooper());
        return true;
    }

    static void notifyRoots(Context context) {
        context.getContentResolver().notifyChange(DocumentsContract.buildRootsUri(AUTHORITY), null);
    }

    private static final class RemoteFailure extends IOException {
        final int code;
        RemoteFailure(String message, int code) { super(message); this.code = code; }
    }

    private static int androidErrno(String name) {
        // Darwin and Android use different errno numbers; translate the symbolic wire value.
        switch (name) {
            case "EACCES": return OsConstants.EACCES;
            case "ENOENT": return OsConstants.ENOENT;
            case "EINVAL": return OsConstants.EINVAL;
            case "EROFS": return OsConstants.EROFS;
            case "EISDIR": return OsConstants.EISDIR;
            case "ENOTDIR": return OsConstants.ENOTDIR;
            case "EEXIST": return OsConstants.EEXIST;
            case "ENOTEMPTY": return OsConstants.ENOTEMPTY;
            case "ELOOP": return OsConstants.ELOOP;
            case "ENAMETOOLONG": return OsConstants.ENAMETOOLONG;
            case "ESTALE": return OsConstants.ESTALE;
            case "ENOSPC": return OsConstants.ENOSPC;
            case "EMFILE": return OsConstants.EMFILE;
            case "EFBIG": return OsConstants.EFBIG;
            case "ENOTSUP": case "EOPNOTSUPP": return OsConstants.EOPNOTSUPP;
            case "EPERM": return OsConstants.EPERM;
            case "EBADF": return OsConstants.EBADF;
            default: return OsConstants.EIO;
        }
    }

    private JSONObject request(String op, Object... fields) throws IOException {
        JSONObject value = new JSONObject();
        try {
            value.put("op", op);
            for (int i = 0; i < fields.length; i += 2) value.put((String) fields[i], fields[i + 1]);
        } catch (JSONException e) { throw new IOException("Invalid Mac file request", e); }
        return value;
    }

    private Object rpc(JSONObject request) throws IOException {
        String token = getContext().getSharedPreferences("bridge", 0).getString("storage_token", "");
        if (!token.matches("[0-9a-f]{64}")) throw new RemoteFailure("Mac folder sharing is not connected", OsConstants.EACCES);
        HttpURLConnection connection = (HttpURLConnection) new URL("http://127.0.0.1:7901/rpc").openConnection();
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(15000);
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.setInstanceFollowRedirects(false);
        connection.setRequestProperty("Authorization", "Bearer " + token);
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        byte[] body = request.toString().getBytes(StandardCharsets.UTF_8);
        connection.setFixedLengthStreamingMode(body.length);
        try {
            try (OutputStream output = connection.getOutputStream()) { output.write(body); }
            int status = connection.getResponseCode();
            InputStream input = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
            if (input == null) throw new IOException("Mac folder service returned no response");
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (InputStream stream = input) {
                byte[] buffer = new byte[16384];
                int count;
                while ((count = stream.read(buffer)) != -1) {
                    if (bytes.size() + count > MAX_RESPONSE) throw new IOException("Mac folder response is too large");
                    bytes.write(buffer, 0, count);
                }
            }
            JSONObject response = new JSONObject(new String(bytes.toByteArray(), StandardCharsets.UTF_8));
            if (!response.optBoolean("ok", false)) {
                throw new RemoteFailure(response.optString("error", "Mac file operation failed"),
                    androidErrno(response.optString("errno", "EIO")));
            }
            if (status != HttpURLConnection.HTTP_OK) throw new IOException("Mac folder service request failed");
            return response.get("data");
        } catch (JSONException e) { throw new IOException("Invalid Mac folder response", e);
        } finally { connection.disconnect(); }
    }

    private JSONObject object(String op, Object... fields) throws IOException {
        Object result = rpc(request(op, fields));
        if (!(result instanceof JSONObject)) throw new IOException("Expected a Mac file record");
        return (JSONObject) result;
    }

    private static FileNotFoundException missing(IOException cause) {
        FileNotFoundException error = new FileNotFoundException(cause.getMessage());
        error.initCause(cause);
        return error;
    }

    private static void column(MatrixCursor.RowBuilder row, String[] projection, String key, Object value) {
        for (String item : projection) if (key.equals(item)) { row.add(key, value); return; }
    }

    private void document(MatrixCursor cursor, String[] projection, JSONObject value) {
        boolean directory = value.optBoolean("directory");
        boolean writable = !value.optBoolean("read_only", true);
        String document = value.optString("document");
        boolean root = isRoot(document);
        int flags = 0;
        if (writable) {
            flags |= directory ? DocumentsContract.Document.FLAG_DIR_SUPPORTS_CREATE : DocumentsContract.Document.FLAG_SUPPORTS_WRITE;
            if (!root) flags |= DocumentsContract.Document.FLAG_SUPPORTS_RENAME | DocumentsContract.Document.FLAG_SUPPORTS_DELETE;
        }
        MatrixCursor.RowBuilder row = cursor.newRow();
        column(row, projection, DocumentsContract.Document.COLUMN_DOCUMENT_ID, document);
        column(row, projection, DocumentsContract.Document.COLUMN_DISPLAY_NAME, value.optString("name"));
        column(row, projection, DocumentsContract.Document.COLUMN_MIME_TYPE, directory ? DIRECTORY : value.optString("mime", "application/octet-stream"));
        column(row, projection, DocumentsContract.Document.COLUMN_FLAGS, flags);
        column(row, projection, DocumentsContract.Document.COLUMN_SIZE, directory ? null : value.optLong("size"));
        column(row, projection, DocumentsContract.Document.COLUMN_LAST_MODIFIED, value.optLong("modified_ms"));
    }

    @Override public Cursor queryRoots(String[] suppliedProjection) throws FileNotFoundException {
        String[] projection = suppliedProjection == null ? ROOT_COLUMNS : suppliedProjection;
        MatrixCursor cursor = new MatrixCursor(projection);
        try {
            Object result = rpc(request("roots"));
            if (!(result instanceof JSONArray)) throw new IOException("Expected Mac folder roots");
            JSONArray roots = (JSONArray) result;
            for (int i = 0; i < roots.length(); i++) {
                JSONObject root = roots.getJSONObject(i);
                int flags = DocumentsContract.Root.FLAG_SUPPORTS_IS_CHILD;
                if (!root.optBoolean("read_only", true)) flags |= DocumentsContract.Root.FLAG_SUPPORTS_CREATE;
                MatrixCursor.RowBuilder row = cursor.newRow();
                column(row, projection, DocumentsContract.Root.COLUMN_ROOT_ID, root.optString("id"));
                column(row, projection, DocumentsContract.Root.COLUMN_DOCUMENT_ID, root.optString("document"));
                column(row, projection, DocumentsContract.Root.COLUMN_TITLE, "Mac · " + root.optString("name"));
                column(row, projection, DocumentsContract.Root.COLUMN_SUMMARY, "Live Mac folder");
                column(row, projection, DocumentsContract.Root.COLUMN_FLAGS, flags);
                column(row, projection, DocumentsContract.Root.COLUMN_MIME_TYPES, "*/*");
            }
        } catch (IOException | JSONException e) {
            // A stopped/revoked service removes its roots instead of breaking Android's picker.
            cursor.close();
            cursor = new MatrixCursor(projection);
        }
        cursor.setNotificationUri(getContext().getContentResolver(), DocumentsContract.buildRootsUri(AUTHORITY));
        return cursor;
    }

    @Override public Cursor queryDocument(String documentId, String[] suppliedProjection) throws FileNotFoundException {
        String[] projection = suppliedProjection == null ? DOCUMENT_COLUMNS : suppliedProjection;
        MatrixCursor cursor = new MatrixCursor(projection);
        try { document(cursor, projection, object("stat", "document", documentId));
        } catch (IOException e) { cursor.close(); throw missing(e); }
        cursor.setNotificationUri(getContext().getContentResolver(), DocumentsContract.buildDocumentUri(AUTHORITY, documentId));
        return cursor;
    }

    @Override public Cursor queryChildDocuments(String parentDocumentId, String[] suppliedProjection, String sortOrder) throws FileNotFoundException {
        String[] projection = suppliedProjection == null ? DOCUMENT_COLUMNS : suppliedProjection;
        MatrixCursor cursor = new MatrixCursor(projection);
        try {
            int offset = 0;
            while (true) {
                Object result = rpc(request("list", "document", parentDocumentId, "offset", offset, "limit", 256));
                if (!(result instanceof JSONArray)) throw new IOException("Expected Mac folder contents");
                JSONArray children = (JSONArray) result;
                if (children.length() > 256) throw new IOException("Mac folder page exceeded requested size");
                for (int i = 0; i < children.length(); i++) document(cursor, projection, children.getJSONObject(i));
                if (children.length() < 256) break;
                offset += children.length();
            }
        } catch (JSONException e) { cursor.close(); throw missing(new IOException("Invalid Mac folder contents", e));
        } catch (IOException e) { cursor.close(); throw missing(e); }
        cursor.setNotificationUri(getContext().getContentResolver(), DocumentsContract.buildChildDocumentsUri(AUTHORITY, parentDocumentId));
        return cursor;
    }

    @Override public boolean isChildDocument(String parentDocumentId, String documentId) {
        try {
            object("stat", "document", parentDocumentId);
            object("stat", "document", documentId);
            String prefix = isRoot(parentDocumentId) ? parentDocumentId : parentDocumentId + "/";
            return !parentDocumentId.equals(documentId) && documentId.startsWith(prefix);
        } catch (IOException e) { return false; }
    }

    private static boolean isRoot(String documentId) {
        int separator = documentId.indexOf(':');
        return separator >= 0 && separator == documentId.length() - 1;
    }

    private void changed(String id) {
        getContext().getContentResolver().notifyChange(DocumentsContract.buildDocumentUri(AUTHORITY, id), null);
        int slash = id.lastIndexOf('/');
        String parent = slash < 0 ? id.substring(0, id.indexOf(':') + 1) : id.substring(0, slash);
        getContext().getContentResolver().notifyChange(DocumentsContract.buildChildDocumentsUri(AUTHORITY, parent), null);
    }

    @Override public String createDocument(String parentDocumentId, String mimeType, String displayName) throws FileNotFoundException {
        try {
            String id = object("create", "parent", parentDocumentId, "name", displayName, "mime", mimeType).getString("document");
            changed(id);
            return id;
        } catch (JSONException e) { throw missing(new IOException("Invalid created Mac file", e));
        } catch (IOException e) { throw missing(e); }
    }

    @Override public String renameDocument(String documentId, String displayName) throws FileNotFoundException {
        try {
            String id = object("rename", "document", documentId, "name", displayName).getString("document");
            changed(documentId); changed(id);
            return id;
        } catch (JSONException e) { throw missing(new IOException("Invalid renamed Mac file", e));
        } catch (IOException e) { throw missing(e); }
    }

    @Override public void deleteDocument(String documentId) throws FileNotFoundException {
        try { object("delete", "document", documentId); changed(documentId);
        } catch (IOException e) { throw missing(e); }
    }

    @Override public ParcelFileDescriptor openDocument(final String documentId, final String mode,
                                                       final CancellationSignal signal) throws FileNotFoundException {
        try {
            if (signal != null) signal.throwIfCanceled();
            final int access = ParcelFileDescriptor.parseMode(mode);
            final boolean readable = (access & ParcelFileDescriptor.MODE_READ_ONLY) != 0;
            final boolean writable = (access & ParcelFileDescriptor.MODE_WRITE_ONLY) != 0;
            final boolean append = (access & ParcelFileDescriptor.MODE_APPEND) != 0;
            JSONObject info = object("stat", "document", documentId);
            if (info.optBoolean("directory")) throw new IOException("A Mac folder is not a file");
            // Do not let a Mac-side atomic replacement redirect an already open descriptor's writes.
            final String identity = info.optString("file_id", "");
            if (identity.isEmpty()) throw new IOException("Mac folder service did not identify the file");
            if (writable && info.optBoolean("read_only", true)) throw new RemoteFailure("Mac folder is read-only", OsConstants.EROFS);
            if ((access & ParcelFileDescriptor.MODE_TRUNCATE) != 0) object("truncate", "document", documentId, "expected_file_id", identity, "size", 0);
            StorageManager storage = getContext().getSystemService(StorageManager.class);
            return storage.openProxyFileDescriptor(access & ParcelFileDescriptor.MODE_READ_WRITE, new ProxyFileDescriptorCallback() {
                private void check() throws ErrnoException {
                    if (signal != null && signal.isCanceled()) throw new ErrnoException("Mac file operation cancelled", OsConstants.ECANCELED);
                }
                private ErrnoException failed(IOException error) {
                    int code = error instanceof RemoteFailure ? ((RemoteFailure) error).code : OsConstants.EIO;
                    return new ErrnoException(error.getMessage(), code, error);
                }
                @Override public long onGetSize() throws ErrnoException {
                    check();
                    try { return object("stat", "document", documentId, "expected_file_id", identity).getLong("size");
                    } catch (JSONException e) { throw new ErrnoException("Invalid Mac file size", OsConstants.EIO, e);
                    } catch (IOException e) { throw failed(e); }
                }
                @Override public int onRead(long offset, int size, byte[] data) throws ErrnoException {
                    check();
                    if (!readable) throw new ErrnoException("Mac file is write-only", OsConstants.EBADF);
                    try {
                        int count = Math.min(Math.min(size, data.length), CHUNK_SIZE);
                        byte[] bytes = Base64.decode(object("read", "document", documentId, "expected_file_id", identity, "offset", offset, "size", count).getString("data"), Base64.NO_WRAP);
                        if (bytes.length > count || bytes.length > data.length) throw new IOException("Mac read exceeded requested size");
                        System.arraycopy(bytes, 0, data, 0, bytes.length);
                        return bytes.length;
                    } catch (JSONException | IllegalArgumentException e) { throw new ErrnoException("Invalid Mac file read", OsConstants.EIO, e);
                    } catch (IOException e) { throw failed(e); }
                }
                @Override public int onWrite(long offset, int size, byte[] data) throws ErrnoException {
                    check();
                    if (!writable) throw new ErrnoException("Mac file is read-only", OsConstants.EBADF);
                    try {
                        int count = Math.min(Math.min(size, data.length), CHUNK_SIZE);
                        String bytes = Base64.encodeToString(Arrays.copyOf(data, count), Base64.NO_WRAP);
                        int written = object("write", "document", documentId, "expected_file_id", identity, "offset", offset, "append", append, "data", bytes).getInt("written");
                        if (written < 0 || written > count || (count > 0 && written == 0)) throw new IOException("Invalid Mac file write length");
                        changed(documentId);
                        return written;
                    } catch (JSONException e) { throw new ErrnoException("Invalid Mac file write", OsConstants.EIO, e);
                    } catch (IOException e) { throw failed(e); }
                }
                @Override public void onFsync() throws ErrnoException {
                    check();
                    try { object("fsync", "document", documentId, "expected_file_id", identity);
                    } catch (IOException e) { throw failed(e); }
                }
                @Override public void onRelease() { if (writable) changed(documentId); }
            }, ioHandler);
        } catch (IllegalArgumentException e) { throw missing(new IOException("Unsupported Mac file mode", e));
        } catch (IOException e) { throw missing(e); }
    }
}
