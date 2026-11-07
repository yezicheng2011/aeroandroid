package dev.dan.androidsubsystem.sip;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.io.IOException;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Account secrets stay encrypted in this Android app's private storage. */
public final class AccountStore {
    private static final String ALIAS = "aeroandroid-sip-account";
    private final SharedPreferences preferences;
    public AccountStore(Context context) { preferences = context.getSharedPreferences("sip-account", Context.MODE_PRIVATE); }
    public String value(String name, String fallback) { return preferences.getString(name, fallback); }
    public boolean configured() { return !value("host", "").isEmpty() && !value("username", "").isEmpty(); }
    public boolean tls() { return preferences.getBoolean("tls", true); }
    public int port() { return preferences.getInt("port", tls() ? 5061 : 5060); }
    private static SecretKey key() throws GeneralSecurityException, IOException {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (!store.containsAlias(ALIAS)) {
            KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder(ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256).build());
            generator.generateKey();
        }
        return (SecretKey) store.getKey(ALIAS, null);
    }
    private String password() throws GeneralSecurityException, IOException {
        String saved = value("password_ciphertext", "");
        if (saved.isEmpty()) return "";
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Base64.decode(value("password_iv", ""), Base64.NO_WRAP)));
        return new String(cipher.doFinal(Base64.decode(saved, Base64.NO_WRAP)), java.nio.charset.StandardCharsets.UTF_8);
    }
    public SipClient.Config load() throws IOException {
        try {
            return new SipClient.Config(value("host", ""), port(), tls(), value("domain", ""),
                value("username", ""), password(), value("display_name", ""));
        } catch (GeneralSecurityException | IllegalArgumentException e) {
            throw new IOException("Cannot unlock SIP account. Save its settings again.", e);
        }
    }
    public void save(String host, int port, boolean tls, String domain, String username,
                     String password, String displayName) throws IOException {
        try {
            String secret = password.isEmpty() ? password() : password;
            new SipClient.Config(host, port, tls, domain, username, secret, displayName);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key());
            String encrypted = Base64.encodeToString(cipher.doFinal(secret.getBytes(java.nio.charset.StandardCharsets.UTF_8)), Base64.NO_WRAP);
            if (!preferences.edit().putString("host", host).putInt("port", port).putBoolean("tls", tls)
                    .putString("domain", domain).putString("username", username).putString("display_name", displayName)
                    .putString("password_ciphertext", encrypted)
                    .putString("password_iv", Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP)).commit()) {
                throw new IOException("SIP account could not be saved");
            }
        } catch (GeneralSecurityException | IllegalArgumentException e) {
            throw new IOException("Cannot save SIP account: " + e.getMessage(), e);
        }
    }
}
