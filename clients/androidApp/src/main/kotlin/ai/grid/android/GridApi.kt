package ai.grid.android

import android.content.Context
import android.net.wifi.WifiManager
import android.os.Build
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.SocketTimeoutException
import java.net.URL
import java.net.URLEncoder
import org.json.JSONObject

private const val DISCOVERY_PORT = 8772

internal data class DiscoveredHost(
    val name: String,
    val url: String,
    val protocol: String,
)

internal data class ThreadSummary(
    val id: String,
    val title: String,
    val updatedAt: String,
    val messageCount: Int,
)

internal data class StoredMessage(
    val id: String,
    val role: String,
    val content: String,
    val name: String,
    val args: String,
    val ui: String,
    val surfaceId: String,
)

internal data class ProviderOption(
    val id: String,
    val name: String,
    val description: String,
    val defaultUrl: String,
    val needsKey: Boolean,
    val available: Boolean,
    val keySet: Boolean,
)

internal data class ProviderInfo(
    val provider: String,
    val model: String,
    val baseUrl: String,
    val providers: List<ProviderOption>,
)

internal fun normalizePairingCode(raw: String): String =
    raw.filter { it.isDigit() }.take(6)

/** Broadcasts GRID_DISCOVER and collects hosts that answer on the LAN. */
internal fun discoverHosts(context: Context, timeoutMs: Int = 1800): List<DiscoveredHost> {
    val wifi = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
    val lock = runCatching {
        wifi?.createMulticastLock("grid-discovery")?.apply {
            setReferenceCounted(false)
            acquire()
        }
    }.getOrNull()
    val results = linkedMapOf<String, DiscoveredHost>()
    val socket = DatagramSocket()
    try {
        socket.broadcast = true
        socket.soTimeout = 300
        val payload = "GRID_DISCOVER".toByteArray(Charsets.UTF_8)
        val targets = linkedSetOf<InetAddress>()
        targets.add(InetAddress.getByName("255.255.255.255"))
        @Suppress("DEPRECATION")
        val wifiIp = runCatching {
            wifi?.connectionInfo?.ipAddress ?: 0
        }.getOrDefault(0)
        if (wifiIp != 0) {
            val a = wifiIp and 0xff
            val b = (wifiIp ushr 8) and 0xff
            val c = (wifiIp ushr 16) and 0xff
            runCatching { targets.add(InetAddress.getByName("$a.$b.$c.255")) }
        }
        val emulator = Build.FINGERPRINT.startsWith("generic") ||
            Build.HARDWARE.contains("goldfish") ||
            Build.HARDWARE.contains("ranchu")
        if (emulator) {
            runCatching { targets.add(InetAddress.getByName("10.0.2.2")) }
        }
        targets.forEach { target ->
            runCatching {
                socket.send(DatagramPacket(payload, payload.size, target, DISCOVERY_PORT))
            }
        }
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            val buffer = ByteArray(1024)
            val packet = DatagramPacket(buffer, buffer.size)
            try {
                socket.receive(packet)
            } catch (_: SocketTimeoutException) {
                continue
            }
            val text = String(packet.data, 0, packet.length, Charsets.UTF_8)
            val json = runCatching { JSONObject(text) }.getOrNull() ?: continue
            if (json.optInt("grid") != 1) continue
            val ip = packet.address?.hostAddress ?: continue
            val url = "http://$ip:${json.optInt("port", 8771)}"
            results[url] = DiscoveredHost(
                name = json.optString("name").ifBlank { ip },
                url = url,
                protocol = json.optString("protocol"),
            )
        }
    } finally {
        try {
            socket.close()
        } catch (_: Exception) {
        }
        try {
            lock?.release()
        } catch (_: Exception) {
        }
    }
    return results.values.sortedBy { it.name.lowercase() }
}

/** Redeems a short pairing code for the host API token. */
internal fun pairWithCode(baseUrl: String, rawCode: String, device: String): String {
    val code = normalizePairingCode(rawCode)
    if (code.length != 6) {
        throw IllegalArgumentException("Enter the 6-digit code shown on the host.")
    }
    val root = postJson(
        baseUrl = baseUrl,
        token = "",
        path = "/api/v1/pair",
        body = JSONObject().put("code", code).put("device", device),
    )
    return root.optString("token").takeIf { it.isNotBlank() }
        ?: throw IllegalStateException("The host did not return a token.")
}

internal fun normalizeBaseUrl(raw: String): String {
    var value = raw.filterNot { it.isWhitespace() }
    if (value.isBlank()) return value
    val lastScheme = maxOf(value.lastIndexOf("http://"), value.lastIndexOf("https://"))
    if (lastScheme > 0) value = value.substring(lastScheme)
    if (!value.startsWith("http://") && !value.startsWith("https://")) {
        value = "http://$value"
    }
    return value.trimEnd('/')
}

internal fun normalizeToken(raw: String): String =
    raw.trim()
        .removeSurrounding("\"")
        .removeSurrounding("'")
        .filterNot { it.isWhitespace() }

/**
 * Returns null when /api/v1/health answers 200, otherwise a message the
 * setup/chat screen can show. 401 is reported as an auth failure instead of
 * the misleading "API offline".
 */
internal fun healthFailure(baseUrl: String, token: String): String? {
    return try {
        val connection = URL("$baseUrl/api/v1/health").openConnection() as HttpURLConnection
        connection.requestMethod = "GET"
        connection.setRequestProperty("Authorization", "Bearer $token")
        connection.connectTimeout = 4000
        connection.readTimeout = 4000
        try {
            when (val code = connection.responseCode) {
                200 -> null
                401, 403 -> "Authentication failed (HTTP $code). Copy the current token from run/api_token and paste it again."
                else -> "Host answered HTTP $code at $baseUrl."
            }
        } finally {
            connection.disconnect()
        }
    } catch (error: Exception) {
        "Cannot reach $baseUrl. Check the URL, phone Wi-Fi and that the host is running. (${error.javaClass.simpleName})"
    }
}

internal fun fetchThreads(baseUrl: String, token: String): List<ThreadSummary> {
    val root = getJson(baseUrl, token, "/api/v1/threads")
    val array = root.optJSONArray("threads") ?: return emptyList()
    return (0 until array.length()).mapNotNull { index ->
        val item = array.optJSONObject(index) ?: return@mapNotNull null
        val id = item.optString("id").takeIf { it.isNotBlank() } ?: return@mapNotNull null
        ThreadSummary(
            id = id,
            title = item.optString("title"),
            updatedAt = item.optString("updated_at"),
            messageCount = item.optInt("message_count"),
        )
    }
}

internal fun fetchThreadMessages(
    baseUrl: String,
    token: String,
    threadId: String,
): List<StoredMessage> {
    val encoded = URLEncoder.encode(threadId, "UTF-8")
    val root = getJson(baseUrl, token, "/api/v1/threads/$encoded")
    val thread = root.optJSONObject("thread") ?: return emptyList()
    val array = thread.optJSONArray("messages") ?: return emptyList()
    return (0 until array.length()).mapNotNull { index ->
        val item = array.optJSONObject(index) ?: return@mapNotNull null
        val role = item.optString("role")
        if (role.isBlank()) return@mapNotNull null
        StoredMessage(
            id = item.optString("id"),
            role = role,
            content = item.optString("content"),
            name = item.optString("name"),
            args = item.optString("args"),
            ui = if (item.isNull("ui")) "" else item.optString("ui"),
            surfaceId = item.optString("surfaceId"),
        )
    }
}

internal fun fetchProviderInfo(baseUrl: String, token: String): ProviderInfo {
    val root = getJson(baseUrl, token, "/api/v1/provider")
    val array = root.optJSONArray("providers")
    val providers = if (array == null) {
        emptyList()
    } else {
        (0 until array.length()).mapNotNull { index ->
            val item = array.optJSONObject(index) ?: return@mapNotNull null
            val id = item.optString("id").takeIf { it.isNotBlank() } ?: return@mapNotNull null
            ProviderOption(
                id = id,
                name = item.optString("name", id),
                description = item.optString("description"),
                defaultUrl = item.optString("default_url"),
                needsKey = item.optBoolean("needs_key"),
                available = item.optBoolean("available", true),
                keySet = item.optBoolean("key_set"),
            )
        }
    }
    return ProviderInfo(
        provider = root.optString("provider"),
        model = root.optString("model"),
        baseUrl = root.optString("base_url"),
        providers = providers,
    )
}

internal fun fetchCurrentModels(baseUrl: String, token: String): List<String> {
    val root = getJson(baseUrl, token, "/api/v1/model")
    return stringList(root, "models")
}

internal fun fetchProviderModels(
    baseUrl: String,
    token: String,
    provider: String,
    providerUrl: String,
): List<String> {
    val body = JSONObject()
        .put("provider", provider)
        .put("base_url", providerUrl)
    return stringList(postJson(baseUrl, token, "/api/v1/provider/models", body), "models")
}

internal fun postModel(baseUrl: String, token: String, model: String): String {
    val root = postJson(baseUrl, token, "/api/v1/model", JSONObject().put("model", model))
    return root.optString("message").ifBlank { "Switched to $model" }
}

internal fun postProvider(
    baseUrl: String,
    token: String,
    provider: String,
    providerUrl: String,
    model: String,
): String {
    val body = JSONObject()
        .put("provider", provider)
        .put("base_url", providerUrl)
        .put("model", model)
    val root = postJson(baseUrl, token, "/api/v1/provider", body)
    return root.optString("message").ifBlank { "Switched to $provider · $model" }
}

internal fun clearThreads(baseUrl: String, token: String): Int {
    val root = postJson(baseUrl, token, "/api/v1/threads/clear", JSONObject())
    return root.optInt("cleared")
}

private fun stringList(root: JSONObject, key: String): List<String> {
    val array = root.optJSONArray(key) ?: return emptyList()
    return (0 until array.length()).mapNotNull { index ->
        array.optString(index).takeIf { it.isNotBlank() }
    }
}

private fun getJson(baseUrl: String, token: String, path: String): JSONObject {
    val connection = URL("$baseUrl$path").openConnection() as HttpURLConnection
    connection.requestMethod = "GET"
    connection.setRequestProperty("Authorization", "Bearer $token")
    connection.connectTimeout = 3000
    connection.readTimeout = 20000
    try {
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        val root = JSONObject(text.ifBlank { "{}" })
        if (code !in 200..299) {
            throw IllegalStateException(
                root.optString("error").ifBlank { "HTTP $code" },
            )
        }
        return root
    } finally {
        connection.disconnect()
    }
}

private fun postJson(
    baseUrl: String,
    token: String,
    path: String,
    body: JSONObject,
): JSONObject {
    val connection = URL("$baseUrl$path").openConnection() as HttpURLConnection
    connection.requestMethod = "POST"
    connection.doOutput = true
    if (token.isNotBlank()) {
        connection.setRequestProperty("Authorization", "Bearer $token")
    }
    connection.setRequestProperty("Content-Type", "application/json")
    connection.connectTimeout = 5000
    connection.readTimeout = 30000
    try {
        connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        val root = JSONObject(text.ifBlank { "{}" })
        if (code !in 200..299) {
            throw IllegalStateException(
                root.optString("error").ifBlank { "HTTP $code" },
            )
        }
        return root
    } finally {
        connection.disconnect()
    }
}
