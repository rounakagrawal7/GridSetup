package ai.grid.android

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Stores the API token encrypted with an Android Keystore AES/GCM key.
 * The URL is not secret and stays in normal preferences.
 */
class TokenStore(context: Context) {
    private val prefs = context.getSharedPreferences("grid_client", Context.MODE_PRIVATE)

    fun loadUrl(): String = prefs.getString(KEY_URL, DEFAULT_URL) ?: DEFAULT_URL

    fun saveUrl(url: String) {
        prefs.edit().putString(KEY_URL, url.trim()).apply()
    }

    fun loadToken(): String {
        val stored = prefs.getString(KEY_TOKEN, "") ?: ""
        if (stored.isEmpty()) return ""
        return try {
            decrypt(stored)
        } catch (_: Exception) {
            ""
        }
    }

    fun saveToken(token: String) {
        val trimmed = token.trim()
        if (trimmed.isEmpty()) {
            prefs.edit().remove(KEY_TOKEN).apply()
            return
        }
        try {
            prefs.edit().putString(KEY_TOKEN, encrypt(trimmed)).apply()
        } catch (_: Exception) {
            // Keep the old value if the keystore is unavailable.
        }
    }

    private fun secretKey(): SecretKey {
        val keyStore = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE)
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return generator.generateKey()
    }

    private fun encrypt(text: String): String {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val iv = cipher.iv
        val encrypted = cipher.doFinal(text.toByteArray(Charsets.UTF_8))
        return Base64.encodeToString(iv + encrypted, Base64.NO_WRAP)
    }

    private fun decrypt(encoded: String): String {
        val bytes = Base64.decode(encoded, Base64.NO_WRAP)
        require(bytes.size > IV_BYTES)
        val iv = bytes.copyOfRange(0, IV_BYTES)
        val ciphertext = bytes.copyOfRange(IV_BYTES, bytes.size)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(128, iv))
        return cipher.doFinal(ciphertext).toString(Charsets.UTF_8)
    }

    companion object {
        const val DEFAULT_URL = "http://10.0.2.2:8771"
        private const val KEY_URL = "base_url"
        private const val KEY_TOKEN = "api_token"
        private const val KEYSTORE = "AndroidKeyStore"
        private const val KEY_ALIAS = "grid_api_token"
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
        private const val IV_BYTES = 12
    }
}
