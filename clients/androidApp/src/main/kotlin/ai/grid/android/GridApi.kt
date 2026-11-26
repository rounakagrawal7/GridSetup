package ai.grid.android

import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import org.json.JSONObject

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
    connection.setRequestProperty("Authorization", "Bearer $token")
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
