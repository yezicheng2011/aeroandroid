package dev.dan.androidsubsystem;
import android.inputmethodservice.InputMethodService;
import android.os.Handler;
import android.os.Looper;
import android.view.inputmethod.InputConnection;

public final class BridgeIme extends InputMethodService {
    private static volatile BridgeIme active;
    @Override public void onCreate() { super.onCreate(); active = this; }
    @Override public void onDestroy() { if (active == this) active = null; super.onDestroy(); }
    @Override public boolean onEvaluateInputViewShown() { return false; }
    static boolean commit(String text) {
        BridgeIme ime = active;
        if (ime == null || ime.getCurrentInputConnection() == null) return false;
        new Handler(Looper.getMainLooper()).post(() -> {
            InputConnection connection = ime.getCurrentInputConnection();
            if (connection != null) connection.commitText(text, 1);
        });
        return true;
    }
}
