package ai.grid.android

import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONObject

internal data class SlashSubcommand(
    val name: String,
    val description: String,
    val template: String? = null,
)

internal data class SlashCommand(
    val name: String,
    val description: String,
    val template: String? = null,
    val subcommands: List<SlashSubcommand> = emptyList(),
)

internal data class SlashSuggestion(
    val label: String,
    val description: String,
    val applyText: String,
)

internal data class SlashPalette(
    val header: String,
    val suggestions: List<SlashSuggestion>,
)

/** Commands handled by POST /api/v1/command on the host. */
internal val SERVER_COMMANDS = setOf(
    "/memory", "/life", "/rea", "/plan", "/ref", "/jobs", "/persona", "/social",
    "/pb", "/export", "/save", "/comms", "/ctf", "/game", "/gcal", "/gsheet",
    "/model", "/tools", "/pair",
)

/**
 * Android's command catalog. It mirrors the desktop app minus host-only
 * actions that do not make sense on a companion (provider switching, token
 * meters, /shutdown), plus the Android-only /settings.
 */
internal val APP_COMMANDS = listOf(
    SlashCommand("/help", "Show commands and GRID tools"),
    SlashCommand("/new", "Start a new thread"),
    SlashCommand("/clear", "Clear this conversation view"),
    SlashCommand("/settings", "Change the host or token"),
    SlashCommand("/model", "Show the active and available models"),
    SlashCommand("/tools", "List every GRID tool"),
    SlashCommand("/pair", "Show the phone pairing code and LAN URL"),
    SlashCommand("/tool", "Run a tool: /tool <name> <input>", template = "/tool "),
    SlashCommand(
        "/rea",
        "Authorized passive teardown: /rea authorized <url>",
        template = "/rea authorized ",
    ),
    SlashCommand(
        "/memory",
        "Recall, add facts, show profile",
        subcommands = listOf(
            SlashSubcommand("status", "Show memory status"),
            SlashSubcommand("profile", "Show the user profile"),
            SlashSubcommand("add", "Teach a fact: <fact>", "add "),
            SlashSubcommand("forget", "Remove a fact: <text>", "forget "),
            SlashSubcommand("build-profile", "Rebuild from previous chats"),
            SlashSubcommand("clear-profile", "Clear the profile"),
            SlashSubcommand("clear", "Clear layered memory"),
        ),
    ),
    SlashCommand(
        "/life",
        "Status, goals, commitments, tick",
        subcommands = listOf(
            SlashSubcommand("status", "Current autopilot state"),
            SlashSubcommand("log", "Recent activity: [n]", "log "),
            SlashSubcommand("goals", "Active goals"),
            SlashSubcommand("goal", "add <title> | done <id>", "goal "),
            SlashSubcommand("commitments", "Open commitments"),
            SlashSubcommand("commitment", "add/done", "commitment "),
            SlashSubcommand("pause", "Pause autonomous work"),
            SlashSubcommand("resume", "Resume autonomous work"),
            SlashSubcommand("identity", "Show persona and identity"),
            SlashSubcommand("tick", "Run one autonomous cycle"),
            SlashSubcommand("awake", "Awake run (terminal): [task]", "awake "),
        ),
    ),
    SlashCommand("/plan", "Toggle planner mode"),
    SlashCommand("/ref", "Read an offloaded tool output", template = "/ref "),
    SlashCommand(
        "/jobs",
        "List/show/toggle dynamic skills",
        subcommands = listOf(
            SlashSubcommand("list", "List dynamic skills"),
            SlashSubcommand("show", "Show a skill: <name>", "show "),
            SlashSubcommand("toggle", "Enable/disable: <name>", "toggle "),
            SlashSubcommand("new", "Create a skill (terminal)"),
            SlashSubcommand("edit", "Edit a skill (terminal): <name>", "edit "),
            SlashSubcommand("delete", "Delete a skill (terminal): <name>", "delete "),
        ),
    ),
    SlashCommand(
        "/persona",
        "View or set GRID persona",
        subcommands = listOf(
            SlashSubcommand("set", "Set persona: <name>", "set "),
            SlashSubcommand("clear", "Clear the persona"),
            SlashSubcommand("status", "Show the current persona"),
        ),
    ),
    SlashCommand("/social", "Moltbook social platform"),
    SlashCommand(
        "/pb",
        "PocketBase status/start/stop/sync",
        subcommands = listOf(
            SlashSubcommand("status", "PocketBase status"),
            SlashSubcommand("start", "Start PocketBase"),
            SlashSubcommand("stop", "Stop PocketBase"),
            SlashSubcommand("install", "Download the binary"),
            SlashSubcommand("sync", "Sync memory to PocketBase"),
        ),
    ),
    SlashCommand("/export", "Export server chat (json/txt/html)", template = "/export "),
    SlashCommand("/save", "Save server conversation memory"),
    SlashCommand("/comms", "Communication tools reference"),
    SlashCommand("/ctf", "Local CTF sandbox"),
    SlashCommand("/game", "Game worlds"),
    SlashCommand("/gcal", "Google Calendar"),
    SlashCommand("/gsheet", "Google Sheets + Excel"),
)

/**
 * Merges app commands with the host tool registry. App descriptions win when
 * a name exists in both; the first non-empty subcommand list is kept so
 * /rea and /social pick up the server metadata.
 */
internal fun mergeSlashCommands(
    app: List<SlashCommand>,
    tools: List<SlashCommand>,
): List<SlashCommand> {
    return (app + tools)
        .groupBy { it.name.lowercase() }
        .map { (_, group) ->
            val base = group.first()
            val withSubcommands = group.firstOrNull { it.subcommands.isNotEmpty() }
            base.copy(
                subcommands = if (base.subcommands.isNotEmpty()) {
                    base.subcommands
                } else {
                    withSubcommands?.subcommands ?: emptyList()
                },
            )
        }
        .sortedBy { it.name }
}

internal fun buildSlashPalette(input: String, commands: List<SlashCommand>): SlashPalette? {
    val trimmed = input.trimStart()
    if (!trimmed.startsWith("/")) return null

    val hasSpace = trimmed.contains(" ")
    val commandName = trimmed.substringBefore(" ")
    val afterCommand = trimmed.substringAfter(" ", "").trimStart()
    val activeCommand = commands.firstOrNull {
        it.name.equals(commandName, ignoreCase = true)
    }

    if (!hasSpace) {
        val filtered = commands.filter {
            it.name.removePrefix("/").startsWith(
                commandName.removePrefix("/"),
                ignoreCase = true,
            )
        }
        if (filtered.isEmpty()) return null
        return SlashPalette(
            header = "COMMANDS · ${filtered.size}/${commands.size}",
            suggestions = filtered.map { command ->
                SlashSuggestion(
                    label = command.name,
                    description = command.description,
                    applyText = if (command.subcommands.isNotEmpty()) {
                        "${command.name} "
                    } else {
                        command.template ?: "${command.name} "
                    },
                )
            },
        )
    }

    if (activeCommand == null || afterCommand.contains(" ")) return null
    val filtered = activeCommand.subcommands.filter {
        it.name.startsWith(afterCommand, ignoreCase = true)
    }
    if (filtered.isEmpty()) return null
    return SlashPalette(
        header = "SUBCOMMANDS · ${activeCommand.name} · ${filtered.size}",
        suggestions = filtered.map { sub ->
            SlashSuggestion(
                label = sub.name,
                description = sub.description,
                applyText = if (sub.template != null) {
                    "${activeCommand.name} ${sub.template}"
                } else {
                    "${activeCommand.name} ${sub.name} "
                },
            )
        },
    )
}

/** Loads the host registry so tool commands and their subcommands autocomplete. */
internal fun fetchToolCommands(baseUrl: String, token: String): List<SlashCommand> {
    return try {
        val connection = URL("$baseUrl/api/v1/tools").openConnection() as HttpURLConnection
        connection.requestMethod = "GET"
        connection.setRequestProperty("Authorization", "Bearer $token")
        connection.connectTimeout = 3000
        connection.readTimeout = 8000
        try {
            if (connection.responseCode != 200) {
                emptyList()
            } else {
                val text = connection.inputStream.bufferedReader().use { it.readText() }
                val array = JSONObject(text).optJSONArray("tools") ?: return emptyList()
                (0 until array.length()).mapNotNull { index ->
                    val item = array.optJSONObject(index) ?: return@mapNotNull null
                    val name = item.optString("name").takeIf { it.isNotBlank() }
                        ?: return@mapNotNull null
                    val subs = item.optJSONArray("subcommands")
                    val subcommands = if (subs == null) {
                        emptyList()
                    } else {
                        (0 until subs.length()).mapNotNull { subIndex ->
                            val sub = subs.optJSONObject(subIndex) ?: return@mapNotNull null
                            val subName = sub.optString("name").takeIf { it.isNotBlank() }
                                ?: return@mapNotNull null
                            SlashSubcommand(
                                name = subName,
                                description = sub.optString("description"),
                                template = if (sub.isNull("template")) null else sub.optString("template"),
                            )
                        }
                    }
                    SlashCommand(
                        name = "/$name",
                        description = item.optString("description"),
                        template = "/$name ",
                        subcommands = subcommands,
                    )
                }
            }
        } finally {
            connection.disconnect()
        }
    } catch (_: Exception) {
        emptyList()
    }
}

/** Runs a host-side slash command such as /memory status or /pb status. */
internal fun postServerCommand(baseUrl: String, token: String, command: String): String {
    val connection = URL("$baseUrl/api/v1/command").openConnection() as HttpURLConnection
    connection.requestMethod = "POST"
    connection.doOutput = true
    connection.setRequestProperty("Authorization", "Bearer $token")
    connection.setRequestProperty("Content-Type", "application/json")
    connection.connectTimeout = 5000
    connection.readTimeout = 600000
    try {
        val payload = JSONObject().put("command", command).toString()
        connection.outputStream.use { it.write(payload.toByteArray(Charsets.UTF_8)) }
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        val root = JSONObject(text.ifBlank { "{}" })
        if (code in 200..299) {
            return root.optString("output").ifBlank { "(no output)" }
        }
        throw IllegalStateException(
            root.optString("error").ifBlank { "Command failed (HTTP $code)" },
        )
    } finally {
        connection.disconnect()
    }
}
