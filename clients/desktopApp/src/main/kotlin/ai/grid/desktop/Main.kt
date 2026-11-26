// Compose UI functions use PascalCase by convention.
@file:Suppress("FunctionName")

package ai.grid.desktop

import ai.grid.shared.GridAgentClient
import ai.grid.shared.GridEvent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.VerticalScrollbar
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollbarAdapter
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.isShiftPressed
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import java.awt.Desktop
import java.awt.Toolkit
import java.awt.datatransfer.StringSelection
import java.io.File
import java.net.HttpURLConnection
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlin.time.Duration.Companion.milliseconds

private val Background = Color(0xFF0B0F0C)
private val Panel = Color(0xFF111813)
private val PanelRaised = Color(0xFF162119)
private val GridGreen = Color(0xFF00FF88)
private val GridGreenDim = Color(0xFF7CF7B0)
private val Muted = Color(0xFF8A9B8F)
private val Danger = Color(0xFFFF6B6B)
private val Warning = Color(0xFFFFD166)

private data class SlashSubcommand(
    val name: String,
    val description: String,
    val template: String? = null,
)

private data class SlashCommand(
    val name: String,
    val description: String,
    val template: String? = null,
    val subcommands: List<SlashSubcommand> = emptyList(),
)

private enum class ToolKind { Command, Edit, Read, Tool }

private fun toolKind(name: String): ToolKind {
    return when (name.lowercase()) {
        "run_command", "run_code" -> ToolKind.Command
        "write_file", "delete_file", "create_directory", "save_skill", "delete_skill" ->
            ToolKind.Edit
        "read_file", "document_read", "file_search", "list_directory", "get_cwd",
        "ref_read", "skill_read", "skill_search", "list_skills",
        "memory_recall", "memory_status", "db_query", "db_analytics" ->
            ToolKind.Read
        else -> ToolKind.Tool
    }
}

private val SLASH_COMMANDS = listOf(
    SlashCommand("/help", "Show available commands and tools"),
    SlashCommand("/new", "Start a new thread"),
    SlashCommand("/clear", "Clear the current conversation"),
    SlashCommand("/exit", "Save memory and close GRID"),
    SlashCommand("/shutdown", "Save and stop the GRID host"),
    SlashCommand("/model", "Show the active model and how to switch"),
    SlashCommand("/provider", "Switch LLM provider"),
    SlashCommand("/tokens", "Show session token and timing stats"),
    SlashCommand(
        "/rea",
        "Authorized passive teardown: /rea authorized <url>",
        template = "/rea authorized ",
    ),
    SlashCommand("/tools", "List every GRID tool"),
    SlashCommand("/pair", "Show the phone pairing code and LAN URL"),
    SlashCommand("/tool", "Run a tool: /tool <name> <input>", template = "/tool "),
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
    SlashCommand("/export", "Export server chat (json/txt/html)"),
    SlashCommand("/save", "Save server conversation memory"),
    SlashCommand("/comms", "Communication tools reference"),
    SlashCommand("/ctf", "Local CTF sandbox"),
    SlashCommand("/game", "Game worlds"),
    SlashCommand("/gcal", "Google Calendar"),
    SlashCommand("/gsheet", "Google Sheets + Excel"),
)

private val SERVER_COMMANDS = setOf(
    "/memory", "/life", "/plan", "/ref", "/jobs", "/persona", "/social",
    "/pb", "/export", "/save", "/comms", "/ctf", "/game", "/gcal", "/gsheet",
    "/pair",
)

private sealed interface Item {
    data class User(val text: String) : Item
    data class Assistant(
        val id: String,
        val text: String,
        val durationMs: Long = 0,
        val tokens: Int = 0,
        val estimated: Boolean = false,
    ) : Item
    data class Tool(
        val callId: String,
        val name: String,
        val args: String,
        val result: String?,
        val ui: String? = null,
        val surfaceId: String = "",
    ) : Item
    data class Artifact(val path: String) : Item
    data class Ui(
        val surfaceId: String,
        val root: String,
        val artifactPath: String = "",
        val fallback: String = "",
    ) : Item
    data class Activity(
        val commands: Int = 0,
        val edits: Int = 0,
        val reads: Int = 0,
        val thoughts: Int = 0,
        val tools: Int = 0,
        val running: Boolean = true,
    ) : Item {
        val total: Int get() = commands + edits + reads + tools
    }
    data class Approval(
        val id: String,
        val tool: String,
        val input: String,
        val risk: String,
        val resolved: Boolean = false,
    ) : Item
    data class Error(val message: String) : Item
    data class Note(val text: String) : Item
}

fun main(args: Array<String>) {
    application {
        val baseUrl = argument(args, "--url") ?: "http://127.0.0.1:8771"
        val token = loadToken(args)
        val projectRoot = argument(args, "--root")?.let { File(it) } ?: findProjectRoot()
        Window(
            onCloseRequest = ::exitApplication,
            title = "GRID",
            state = rememberWindowState(width = 1180.dp, height = 820.dp),
        ) {
            MaterialTheme(
                colorScheme = darkColorScheme(
                    primary = GridGreen,
                    onPrimary = Color.Black,
                    background = Background,
                    onBackground = Color.White,
                    surface = Panel,
                    onSurface = Color.White,
                )
            ) {
                App(baseUrl.trimEnd('/'), token, projectRoot, onExit = ::exitApplication)
            }
        }
    }
}

@Composable
private fun App(
    baseUrl: String,
    initialToken: String,
    projectRoot: File?,
    onExit: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    val items = remember { mutableStateListOf<Item>() }
    val listState = rememberLazyListState()
    val inputFocus = remember { FocusRequester() }
    var token by remember { mutableStateOf(initialToken) }
    var apiOnline by remember { mutableStateOf<Boolean?>(null) }
    var refreshTick by remember { mutableStateOf(0) }
    var input by remember { mutableStateOf(TextFieldValue("")) }
    var busy by remember { mutableStateOf(false) }
    var runJob by remember { mutableStateOf<Job?>(null) }
    var commandBusy by remember { mutableStateOf(false) }
    var confirmShutdown by remember { mutableStateOf(false) }
    var confirmClearHistory by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("Ready") }
    var threadId by remember { mutableStateOf(GridAgentClient.newThreadId()) }
    var model by remember { mutableStateOf("") }
    var models by remember { mutableStateOf(emptyList<String>()) }
    var provider by remember { mutableStateOf("") }
    var providerInfo by remember { mutableStateOf<ProviderInfo?>(null) }
    var showProviderDialog by remember { mutableStateOf(false) }
    var showPairDialog by remember { mutableStateOf(false) }
    var threads by remember { mutableStateOf(emptyList<ThreadSummary>()) }
    var tools by remember { mutableStateOf(emptyList<ToolInfo>()) }
    var totalTokens by remember { mutableStateOf(0) }
    var lastLatency by remember { mutableStateOf(0L) }
    var lastTokens by remember { mutableStateOf(0) }
    var runCount by remember { mutableStateOf(0) }
    var currentAssistantId by remember { mutableStateOf<String?>(null) }
    var pendingStats by remember { mutableStateOf<GridEvent.Stats?>(null) }
    var setupProvider by remember { mutableStateOf("ollama") }
    var setupUrl by remember { mutableStateOf(providerDefaultUrl("ollama")) }
    var setupKey by remember { mutableStateOf("") }
    var setupModel by remember { mutableStateOf("") }
    var setupModels by remember { mutableStateOf(emptyList<String>()) }
    var setupKeySet by remember { mutableStateOf(false) }
    var setupBusy by remember { mutableStateOf(false) }
    var setupMessage by remember { mutableStateOf("") }
    val client = remember(baseUrl, token) { GridAgentClient(baseUrl, token) }

    LaunchedEffect(baseUrl, token, refreshTick) {
        var candidate = token
        if (candidate.isBlank()) {
            candidate = withContext(Dispatchers.IO) { loadToken(emptyArray()) }
            if (candidate.isNotBlank()) {
                token = candidate
                return@LaunchedEffect
            }
        }
        if (candidate.isBlank()) {
            apiOnline = false
            status = "Setup required"
            return@LaunchedEffect
        }
        val online = withContext(Dispatchers.IO) { apiHealthy(baseUrl, candidate) }
        if (!online) {
            apiOnline = false
            status = "Host offline"
            return@LaunchedEffect
        }
        apiOnline = true
        status = "Ready"
        val pInfo = withContext(Dispatchers.IO) { fetchProviderInfo(baseUrl, candidate) }
        if (pInfo != null) {
            provider = pInfo.provider
            providerInfo = pInfo
        }
        val info = withContext(Dispatchers.IO) { fetchModelInfo(baseUrl, candidate) }
        if (info != null) {
            model = info.model
            models = info.models
        }
        val toolList = withContext(Dispatchers.IO) { fetchTools(baseUrl, candidate) }
        if (toolList != null) tools = toolList
        val threadList = withContext(Dispatchers.IO) { fetchThreads(baseUrl, candidate) }
        if (threadList != null) threads = threadList
    }

    LaunchedEffect(projectRoot, apiOnline) {
        if (apiOnline != false) return@LaunchedEffect
        val root = projectRoot ?: return@LaunchedEffect
        val cfg = readConfig(root)
        val savedProvider = cfg["backend_type"]?.jsonPrimitive?.contentOrNull ?: "ollama"
        setupProvider = savedProvider
        setupUrl = cfg["base_url"]?.jsonPrimitive?.contentOrNull
            ?: providerDefaultUrl(savedProvider)
        setupModel = cfg["model"]?.jsonPrimitive?.contentOrNull ?: ""
        setupKeySet = when (savedProvider) {
            "openrouter" -> !cfg["openrouter_api_key"]?.jsonPrimitive?.contentOrNull.isNullOrBlank()
            "openai" -> !cfg["openai_api_key"]?.jsonPrimitive?.contentOrNull.isNullOrBlank()
            else -> true
        }
    }

    LaunchedEffect(apiOnline) {
        if (apiOnline == true) inputFocus.requestFocus()
    }

    fun activityIndex(): Int = items.indexOfLast { it is Item.Activity }

    fun addDuringRun(item: Item) {
        val index = activityIndex()
        if (index >= 0) items.add(index, item) else items.add(item)
    }

    fun updateActivity(transform: (Item.Activity) -> Item.Activity) {
        val index = activityIndex()
        if (index >= 0) {
            items[index] = transform(items[index] as Item.Activity)
        }
    }

    fun recordTool(name: String) {
        updateActivity { activity ->
            when (toolKind(name)) {
                ToolKind.Command -> activity.copy(
                    commands = activity.commands + 1,
                    thoughts = activity.thoughts + 1,
                )
                ToolKind.Edit -> activity.copy(
                    edits = activity.edits + 1,
                    thoughts = activity.thoughts + 1,
                )
                ToolKind.Read -> activity.copy(
                    reads = activity.reads + 1,
                    thoughts = activity.thoughts + 1,
                )
                ToolKind.Tool -> activity.copy(
                    tools = activity.tools + 1,
                    thoughts = activity.thoughts + 1,
                )
            }
        }
    }

    fun finishActivity() {
        val index = activityIndex()
        if (index < 0) return
        val activity = items[index] as Item.Activity
        if (activity.total == 0) {
            items.removeAt(index)
        } else if (activity.running) {
            items[index] = activity.copy(running = false)
        }
    }

    fun handle(event: GridEvent) {
        when (event) {
            is GridEvent.RunStarted -> {
                threadId = event.threadId
                status = "Running ${event.runId.take(10)}"
                currentAssistantId = null
                pendingStats = null
            }
            is GridEvent.StepStarted -> status = "Step: ${event.name}"
            is GridEvent.StepFinished -> status = "Working"
            is GridEvent.MessageStarted -> {
                currentAssistantId = event.messageId
                if (items.none { it is Item.Assistant && it.id == event.messageId }) {
                    val stats = pendingStats
                    items.add(
                        Item.Assistant(
                            event.messageId,
                            "",
                            durationMs = stats?.durationMs ?: 0,
                            tokens = stats?.totalTokens ?: 0,
                            estimated = stats?.estimated ?: false,
                        )
                    )
                    pendingStats = null
                }
            }
            is GridEvent.TextDelta -> {
                currentAssistantId = event.messageId
                val index = items.indexOfLast { it is Item.Assistant && it.id == event.messageId }
                if (index >= 0) {
                    val old = items[index] as Item.Assistant
                    items[index] = old.copy(text = old.text + event.delta)
                } else {
                    val stats = pendingStats
                    items.add(
                        Item.Assistant(
                            event.messageId,
                            event.delta,
                            durationMs = stats?.durationMs ?: 0,
                            tokens = stats?.totalTokens ?: 0,
                            estimated = stats?.estimated ?: false,
                        )
                    )
                    pendingStats = null
                }
            }
            is GridEvent.MessageFinished -> Unit
            is GridEvent.ToolStarted -> {
                addDuringRun(Item.Tool(event.callId, event.name, "", null))
                recordTool(event.name)
            }
            is GridEvent.ToolArgs -> {
                val index = items.indexOfLast { it is Item.Tool && it.callId == event.callId }
                if (index >= 0) {
                    val old = items[index] as Item.Tool
                    items[index] = old.copy(args = old.args + event.delta)
                }
            }
            is GridEvent.ToolEnded -> Unit
            is GridEvent.ToolResult -> {
                val index = items.indexOfLast { it is Item.Tool && it.callId == event.callId }
                if (index >= 0) {
                    val old = items[index] as Item.Tool
                    items[index] = old.copy(result = event.content)
                }
            }
            is GridEvent.Activity -> status = event.activityType
            is GridEvent.Artifact -> {
                val richRea = items.any {
                    it is Item.Tool && it.name == "rea" && it.ui != null
                }
                if (!richRea) addDuringRun(Item.Artifact(event.path))
            }
            is GridEvent.ApprovalRequired -> addDuringRun(
                Item.Approval(
                    id = event.approvalId,
                    tool = event.tool,
                    input = event.input,
                    risk = event.risk,
                )
            )
            is GridEvent.Stats -> {
                finishActivity()
                totalTokens += event.totalTokens
                lastLatency = event.durationMs
                lastTokens = event.totalTokens
                runCount += 1
                pendingStats = event
                val id = currentAssistantId
                if (id != null) {
                    val index = items.indexOfLast { it is Item.Assistant && it.id == id }
                    if (index >= 0) {
                        val old = items[index] as Item.Assistant
                        items[index] = old.copy(
                            durationMs = event.durationMs,
                            tokens = event.totalTokens,
                            estimated = event.estimated,
                        )
                        pendingStats = null
                    }
                }
            }
            is GridEvent.Ui -> {
                if (event.root.isNotBlank()) {
                    if (event.toolCallId.isNotBlank()) {
                        val index = items.indexOfLast {
                            it is Item.Tool && it.callId == event.toolCallId
                        }
                        if (index >= 0) {
                            val old = items[index] as Item.Tool
                            items[index] = old.copy(
                                ui = event.root,
                                surfaceId = event.surfaceId,
                            )
                        } else {
                            addDuringRun(
                                Item.Ui(
                                    surfaceId = event.surfaceId,
                                    root = event.root,
                                    artifactPath = event.artifactPath,
                                    fallback = event.fallback,
                                )
                            )
                        }
                    } else {
                        if (event.artifactPath.isNotBlank()) {
                            val artifactIndex = items.indexOfLast {
                                it is Item.Artifact && it.path == event.artifactPath
                            }
                            if (artifactIndex >= 0) items.removeAt(artifactIndex)
                        }
                        addDuringRun(
                            Item.Ui(
                                surfaceId = event.surfaceId,
                                root = event.root,
                                artifactPath = event.artifactPath,
                                fallback = event.fallback,
                            )
                        )
                    }
                }
            }
            is GridEvent.Custom -> Unit
            is GridEvent.RunFinished -> {
                finishActivity()
                busy = false
                status = "Ready"
                currentAssistantId = null
                pendingStats = null
                scope.launch {
                    val list = withContext(Dispatchers.IO) {
                        fetchThreads(baseUrl, token)
                    }
                    if (list != null) threads = list
                }
            }
            is GridEvent.Error -> {
                finishActivity()
                items.add(Item.Error(event.message))
                busy = false
                status = "Error"
                currentAssistantId = null
                pendingStats = null
            }
            is GridEvent.Other -> Unit
        }
    }

    fun send(promptOverride: String? = null) {
        val prompt = (promptOverride ?: input.text).trim()
        if (prompt.isEmpty() || busy || commandBusy) return
        if (promptOverride == null) input = TextFieldValue("")
        items.add(Item.User(prompt))
        items.add(Item.Activity())
        busy = true
        status = "Sending"
        runJob = scope.launch {
            try {
                client.run(prompt, threadId).collect { handle(it) }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                finishActivity()
                val message = connectionAwareMessage(error, baseUrl)
                items.add(Item.Error(message))
                status = if (message.startsWith("GRID API is offline")) "API offline" else "Error"
            } finally {
                finishActivity()
                busy = false
                runJob = null
            }
        }
    }

    fun runServerCommand(raw: String) {
        val command = raw.trim()
        if (command.isEmpty() || commandBusy) return
        commandBusy = true
        status = "Running ${command.substringBefore(" ")}"
        scope.launch {
            try {
                val output = withContext(Dispatchers.IO) {
                    postCommand(baseUrl, token, command)
                }
                items.add(Item.Note(output))
                status = "Ready"
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                items.add(Item.Error(connectionAwareMessage(error, baseUrl)))
                status = "Error"
            } finally {
                commandBusy = false
            }
        }
    }

    fun saveAndExit() {
        if (busy) {
            items.add(Item.Note("Wait for the current response to finish before /exit."))
            return
        }
        if (commandBusy) return
        commandBusy = true
        status = "Saving memory..."
        scope.launch {
            try {
                val output = withContext(Dispatchers.IO) {
                    postCommand(baseUrl, token, "/save")
                }
                items.add(Item.Note("$output\nClosing GRID."))
                status = "Saved"
                delay(900)
                onExit()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                items.add(
                    Item.Error(
                        "Could not save before exit: ${connectionAwareMessage(error, baseUrl)}"
                    )
                )
                status = "Exit cancelled"
                commandBusy = false
            }
        }
    }

    fun shutdownHost() {
        if (busy) {
            items.add(Item.Note("Wait for the current response to finish before /shutdown."))
            return
        }
        if (commandBusy) return
        commandBusy = true
        status = "Stopping GRID host..."
        scope.launch {
            try {
                val output = withContext(Dispatchers.IO) {
                    postShutdown(baseUrl, token)
                }
                items.add(Item.Note("$output\nDesktop closing."))
                status = "Host stopped"
                delay(900)
                onExit()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                items.add(
                    Item.Error(
                        "Shutdown failed: ${connectionAwareMessage(error, baseUrl)}"
                    )
                )
                status = "Shutdown failed"
                commandBusy = false
            }
        }
    }

    fun openProviderDialog() {
        if (busy || commandBusy) {
            items.add(Item.Note("Wait for the current response to finish before switching providers."))
            return
        }
        showProviderDialog = true
    }

    fun selectSetupProvider(id: String) {
        val changed = setupProvider != id
        setupProvider = id
        if (changed) setupModel = ""
        if (setupUrl.isBlank() || DEFAULT_PROVIDERS.any { it.defaultUrl == setupUrl }) {
            setupUrl = providerDefaultUrl(id)
        }
        setupModels = emptyList()
        setupKey = ""
        setupKeySet = projectRoot?.let { hasProviderKey(it, id) } ?: false
    }

    fun loadSetupModels() {
        if (setupBusy) return
        if (setupProvider == "ollama" && setupUrl.isBlank()) {
            setupMessage = "Enter the Ollama URL first."
            return
        }
        setupBusy = true
        setupMessage = "Loading models..."
        scope.launch {
            try {
                val list = withContext(Dispatchers.IO) {
                    fetchModelsDirect(setupProvider, setupUrl, setupKey)
                }
                setupModels = list
                if (setupModel.isBlank() && list.isNotEmpty()) setupModel = list.first()
                setupMessage = if (list.isEmpty()) {
                    "No models found. Check the URL, server and API key."
                } else {
                    "${list.size} models loaded."
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                setupMessage = "Could not load models: ${error.message}"
            } finally {
                setupBusy = false
            }
        }
    }

    fun startLocalHost() {
        if (setupBusy) return
        val root = projectRoot
        if (root == null) {
            setupMessage = "Project root not found. Start the desktop from the GRID folder or pass --root."
            return
        }
        if (setupUrl.isBlank() || setupModel.isBlank()) {
            setupMessage = "Provider URL and model are required."
            return
        }
        if (providerNeedsKey(setupProvider) && setupKey.isBlank() && !setupKeySet) {
            setupMessage = "${providerLabel(setupProvider)} API key is required."
            return
        }
        setupBusy = true
        setupMessage = "Writing config..."
        scope.launch {
            try {
                withContext(Dispatchers.IO) {
                    writeConfig(root, setupProvider, setupUrl, setupModel, setupKey)
                    val existing = readToken(root).ifBlank { token }
                    if (!apiHealthy(baseUrl, existing)) {
                        startHost(root)
                    }
                }
                setupMessage = "Starting GRID host..."
                val found = withContext(Dispatchers.IO) {
                    repeat(90) {
                        val candidate = readToken(root).ifBlank { loadToken(emptyArray()) }
                        if (candidate.isNotBlank() && apiHealthy(baseUrl, candidate)) {
                            return@withContext candidate
                        }
                        delay(500)
                    }
                    ""
                }
                if (found.isBlank()) {
                    setupMessage = "Host did not start. Check run/desktop_host.log."
                    setupBusy = false
                } else {
                    token = found
                    setupMessage = "Connected."
                    setupBusy = false
                    refreshTick += 1
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                setupMessage = "Could not start host: ${error.message}"
                setupBusy = false
            }
        }
    }

    fun retryHost() {
        if (setupBusy) return
        setupBusy = true
        setupMessage = "Checking host..."
        scope.launch {
            try {
                val candidate = withContext(Dispatchers.IO) {
                    projectRoot?.let { readToken(it) }.orEmpty()
                        .ifBlank { loadToken(emptyArray()) }
                }
                if (candidate.isBlank()) {
                    setupMessage = "No API token found. Start the host first."
                } else {
                    val online = withContext(Dispatchers.IO) {
                        apiHealthy(baseUrl, candidate)
                    }
                    if (online) {
                        token = candidate
                        setupMessage = "Connected."
                        refreshTick += 1
                    } else {
                        setupMessage = "Host is still offline at $baseUrl."
                    }
                }
            } finally {
                setupBusy = false
            }
        }
    }

    fun handleSlashCommand(raw: String): Boolean {
        val command = raw.trim()
        if (!command.startsWith("/")) return false
        val name = command.substringBefore(" ").lowercase()
        val args = command.substringAfter(" ", "").trim()
        val toolName = name.removePrefix("/")
        when {
            name == "/help" -> items.add(
                Item.Note(
                    "Slash commands:\n" +
                        SLASH_COMMANDS.joinToString("\n") {
                            "  ${it.name.padEnd(10)} = ${it.description}"
                        } +
                        "\n\nPlus ${tools.size} GRID tools (type /tools).\n" +
                        "Type / to autocomplete; ↑↓ select, Tab complete."
                )
            )
            name == "/new" -> {
                threadId = GridAgentClient.newThreadId()
                items.clear()
                status = "Ready"
            }
            name == "/clear" -> {
                items.clear()
                status = "Ready"
            }
            name == "/exit" || name == "/quit" -> saveAndExit()
            name == "/shutdown" -> {
                if (busy) {
                    items.add(
                        Item.Note("Wait for the current response to finish before /shutdown.")
                    )
                } else if (!commandBusy) {
                    confirmShutdown = true
                }
            }
            name == "/model" -> items.add(
                Item.Note(
                    "Active model: ${model.ifBlank { "(unknown)" }}\n" +
                        "Available: ${models.joinToString(", ").ifBlank { "(none detected)" }}\n" +
                        "Use Change model in the sidebar to switch."
                )
            )
            name == "/provider" -> openProviderDialog()
            name == "/tokens" -> items.add(
                Item.Note(
                    "Session: $runCount runs · ${formatTokens(totalTokens)} tokens\n" +
                        "Last: ${formatDuration(lastLatency)} · ${formatTokens(lastTokens)} tokens"
                )
            )
            name == "/tools" -> scope.launch {
                val list = withContext(Dispatchers.IO) { fetchTools(baseUrl, token) } ?: tools
                if (list.isEmpty()) {
                    items.add(Item.Error("Could not load the tool registry."))
                } else {
                    items.add(
                        Item.Note(
                            "GRID tools (${list.size}):\n" +
                                list.joinToString("\n") {
                                    "  ${it.name.padEnd(22)} = ${it.description}"
                                }
                        )
                    )
                }
            }
            name == "/tool" -> {
                val parts = args.split(Regex("\\s+"), limit = 2)
                if (parts.isEmpty() || parts[0].isBlank()) {
                    items.add(Item.Note("Usage: /tool <name> <input>"))
                } else {
                    val rest = parts.getOrNull(1).orEmpty()
                    send(("${parts[0]} $rest").trim())
                }
            }
            name == "/rea" -> {
                when {
                    args.isBlank() -> items.add(
                        Item.Note("Usage: /rea authorized <url> | authorize|revoke|list|status")
                    )
                    args == "list" ||
                        args == "status" ||
                        args == "help" ||
                        args.startsWith("authorize ") ||
                        args.startsWith("revoke ") -> runServerCommand("/rea $args")
                    args.startsWith("authorized ") -> send("rea $args")
                    else -> send("rea authorized $args")
                }
            }
            name in SERVER_COMMANDS -> runServerCommand(command)
            tools.any { it.name == toolName } -> {
                send(("$toolName $args").trim())
            }
            else -> items.add(
                Item.Note("Unknown command: $name\nType /help for available commands.")
            )
        }
        return true
    }

    fun resolveApproval(index: Int, approval: Item.Approval, decision: String) {
        if (approval.resolved) return
        items[index] = approval.copy(resolved = true)
        scope.launch {
            val ok = withContext(Dispatchers.IO) {
                postApproval(baseUrl, token, approval.id, decision)
            }
            if (!ok) {
                items[index] = approval.copy(resolved = false)
                items.add(Item.Error("Approval request failed. Is GRID --api still running?"))
            }
        }
    }

    fun stopRun() {
        if (!busy) return
        runJob?.cancel()
        runJob = null
        busy = false
        finishActivity()
        status = "Stopped"
    }

    fun openThread(id: String) {
        if (busy) {
            stopRun()
        }
        if (commandBusy) {
            items.add(Item.Note("Wait for the current command to finish before opening a thread."))
            return
        }
        if (id == threadId) return
        scope.launch {
            status = "Loading thread..."
            val messages = withContext(Dispatchers.IO) {
                fetchThreadMessages(baseUrl, token, id)
            }
            if (messages == null) {
                items.add(Item.Error("Could not load that thread."))
                status = "Error"
                return@launch
            }
            threadId = id
            items.clear()
            messages.forEach { message ->
                when (message.role) {
                    "user" -> items.add(Item.User(message.content))
                    "assistant" -> if (message.content.isNotBlank()) {
                        items.add(Item.Assistant(message.id, message.content))
                    }
                    "tool" -> if (message.name.isNotBlank()) {
                        items.add(
                            Item.Tool(
                                callId = message.id,
                                name = message.name,
                                args = message.args,
                                result = message.content.ifBlank { "(no output)" },
                                ui = message.ui.ifBlank { null },
                                surfaceId = message.surfaceId,
                            )
                        )
                    }
                }
            }
            status = "Ready"
        }
    }

    fun refreshThreads() {
        scope.launch {
            val list = withContext(Dispatchers.IO) {
                fetchThreads(baseUrl, token)
            }
            if (list != null) threads = list
        }
    }

    fun clearHistory() {
        if (busy) {
            items.add(Item.Note("Stop the current response before clearing history."))
            return
        }
        if (commandBusy) return
        scope.launch {
            commandBusy = true
            status = "Clearing history..."
            try {
                val result = withContext(Dispatchers.IO) {
                    clearThreadHistory(baseUrl, token)
                }
                threads = emptyList()
                threadId = GridAgentClient.newThreadId()
                items.clear()
                items.add(Item.Note(result.message))
                status = "Ready"
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                items.add(
                    Item.Error(
                        "Could not clear history: ${connectionAwareMessage(error, baseUrl)}"
                    )
                )
                status = "Error"
            } finally {
                commandBusy = false
            }
        }
    }

    fun sendUiAction(surfaceId: String, action: String, payload: String) {
        scope.launch {
            try {
                val message = withContext(Dispatchers.IO) {
                    postUiAction(baseUrl, token, surfaceId, action, payload)
                }
                items.add(Item.Note(message))
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                items.add(
                    Item.Error(
                        "UI action failed: ${connectionAwareMessage(error, baseUrl)}"
                    )
                )
            }
        }
    }

    fun resolveUiApproval(approvalId: String, decision: String) {
        scope.launch {
            val ok = withContext(Dispatchers.IO) {
                postApproval(baseUrl, token, approvalId, decision)
            }
            items.add(
                if (ok) {
                    Item.Note("Approval sent: $decision")
                } else {
                    Item.Error("Approval request failed.")
                }
            )
        }
    }

    fun changeModel(requested: String) {
        if (busy || commandBusy) {
            items.add(Item.Note("Wait for the current response to finish before switching models."))
            return
        }
        scope.launch {
            val ok = withContext(Dispatchers.IO) {
                postModel(baseUrl, token, requested)
            }
            if (ok) {
                model = requested
                status = "Model: $requested"
            } else {
                items.add(Item.Error("Could not switch model. Check that GRID --api is running."))
            }
        }
    }

    when (apiOnline) {
        null -> HostLoadingScreen()
        false -> SetupScreen(
            baseUrl = baseUrl,
            projectRoot = projectRoot,
            provider = setupProvider,
            url = setupUrl,
            apiKey = setupKey,
            model = setupModel,
            models = setupModels,
            keySet = setupKeySet,
            busy = setupBusy,
            message = setupMessage,
            onProvider = { selectSetupProvider(it) },
            onUrl = { setupUrl = it },
            onApiKey = { setupKey = it },
            onModel = { setupModel = it },
            onLoadModels = { loadSetupModels() },
            onStart = { startLocalHost() },
            onRetry = { retryHost() },
        )
        true -> Row(Modifier.fillMaxSize().background(Background)) {
        Sidebar(
            status = status,
            threadId = threadId,
            baseUrl = baseUrl,
            tokenReady = token.isNotBlank(),
            model = model,
            models = models,
            provider = provider,
            threads = threads,
            activeThreadId = threadId,
            totalTokens = totalTokens,
            lastLatency = lastLatency,
            lastTokens = lastTokens,
            runCount = runCount,
            onModelChange = { changeModel(it) },
            onProviderChange = { openProviderDialog() },
            onPairPhone = { showPairDialog = true },
            onThreadOpen = { openThread(it) },
            onRefreshThreads = { refreshThreads() },
            onClearHistory = {
                if (busy || commandBusy) {
                    items.add(
                        Item.Note("Stop the current response before clearing history.")
                    )
                } else {
                    confirmClearHistory = true
                }
            },
            onNewThread = {
                threadId = GridAgentClient.newThreadId()
                items.clear()
                status = "Ready"
            },
            onQuickPrompt = {
                input = TextFieldValue("")
                send(it)
            },
        )
        Column(Modifier.weight(1f).fillMaxHeight().padding(18.dp)) {
            Header(status = status, threadId = threadId)
            Spacer(Modifier.height(12.dp))
            LaunchedEffect(items.size) {
                if (items.isNotEmpty()) {
                    listState.animateScrollToItem(items.lastIndex)
                }
            }
            Box(Modifier.weight(1f).fillMaxWidth()) {
                LazyColumn(
                    state = listState,
                    modifier = Modifier.fillMaxSize().padding(end = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    itemsIndexed(items) { index, item ->
                        when (item) {
                            is Item.User -> UserBubble(item.text)
                            is Item.Assistant -> AssistantBubble(item)
                            is Item.Tool -> ToolCard(
                                item = item,
                                onAction = { action, payload ->
                                    sendUiAction(
                                        item.surfaceId.ifBlank { "tool:${item.callId}" },
                                        action,
                                        payload,
                                    )
                                },
                                onApproval = { id, decision ->
                                    resolveUiApproval(id, decision)
                                },
                                onOpenArtifact = { openPath(it) },
                            )
                            is Item.Artifact -> ArtifactCard(item.path)
                            is Item.Ui -> UiSurfaceCard(
                                item = item,
                                onAction = { action, payload ->
                                    sendUiAction(item.surfaceId, action, payload)
                                },
                                onApproval = { id, decision ->
                                    resolveUiApproval(id, decision)
                                },
                                onOpenArtifact = { openPath(it) },
                            )
                            is Item.Activity -> ActivityCard(item)
                            is Item.Approval -> ApprovalCard(
                                approval = item,
                                onApprove = { resolveApproval(index, item, "approve") },
                                onDeny = { resolveApproval(index, item, "deny") },
                            )
                            is Item.Error -> ErrorCard(item.message)
                            is Item.Note -> NoteCard(item.text)
                        }
                    }
                }
                VerticalScrollbar(
                    adapter = rememberScrollbarAdapter(listState),
                    modifier = Modifier.align(Alignment.CenterEnd).fillMaxHeight(),
                )
            }
            Spacer(Modifier.height(12.dp))
            Composer(
                input = input,
                busy = busy || commandBusy,
                runActive = busy,
                enabled = token.isNotBlank(),
                focusRequester = inputFocus,
                tools = tools,
                onInput = { input = it },
                onCommand = { handleSlashCommand(it) },
                onSend = { send() },
                onStop = { stopRun() },
            )
        }
    }
    }
    if (confirmShutdown) {
        AlertDialog(
            onDismissRequest = { confirmShutdown = false },
            title = { Text("Stop GRID host?") },
            text = {
                Text(
                    "This saves memory, then stops the API host, autopilot and " +
                        "Android connectivity. The desktop will close."
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmShutdown = false
                        shutdownHost()
                    }
                ) {
                    Text("Shut down", color = Danger)
                }
            },
            dismissButton = {
                TextButton(onClick = { confirmShutdown = false }) {
                    Text("Cancel", color = Muted)
                }
            },
            containerColor = PanelRaised,
            titleContentColor = Color.White,
            textContentColor = Muted,
        )
    }
    if (showProviderDialog) {
        ProviderDialog(
            baseUrl = baseUrl,
            token = token,
            currentProvider = provider,
            currentModel = model,
            currentBaseUrl = providerInfo?.baseUrl ?: providerDefaultUrl(provider),
            serverProviders = providerInfo?.providers ?: DEFAULT_PROVIDERS,
            onDismiss = { showProviderDialog = false },
            onSwitched = { newProvider, newModel, newModels ->
                provider = newProvider
                model = newModel
                models = newModels
                showProviderDialog = false
                status = "Provider: ${providerLabel(newProvider)}"
                items.add(
                    Item.Note("Switched to ${providerLabel(newProvider)} · $newModel")
                )
                scope.launch {
                    providerInfo = withContext(Dispatchers.IO) {
                        fetchProviderInfo(baseUrl, token)
                    }
                }
            },
        )
    }
    if (showPairDialog) {
        PairPhoneDialog(
            baseUrl = baseUrl,
            token = token,
            onDismiss = { showPairDialog = false },
        )
    }
    if (confirmClearHistory) {
        AlertDialog(
            onDismissRequest = { confirmClearHistory = false },
            title = { Text("Clear thread history?") },
            text = {
                Text(
                    "This deletes saved conversations only. Memory, user profile, " +
                        "persona, goals and config are not touched."
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmClearHistory = false
                        clearHistory()
                    }
                ) {
                    Text("Clear", color = Danger)
                }
            },
            dismissButton = {
                TextButton(onClick = { confirmClearHistory = false }) {
                    Text("Cancel", color = Muted)
                }
            },
            containerColor = PanelRaised,
            titleContentColor = Color.White,
            textContentColor = Muted,
        )
    }
}

@Composable
private fun HostLoadingScreen() {
    Box(Modifier.fillMaxSize().background(Background), contentAlignment = Alignment.Center) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            CircularProgressIndicator(
                modifier = Modifier.size(18.dp),
                color = GridGreen,
                strokeWidth = 2.dp,
            )
            Spacer(Modifier.width(10.dp))
            Text("Connecting to GRID host…", color = Muted, fontSize = 13.sp)
        }
    }
}

@Composable
private fun SetupScreen(
    baseUrl: String,
    projectRoot: File?,
    provider: String,
    url: String,
    apiKey: String,
    model: String,
    models: List<String>,
    keySet: Boolean,
    busy: Boolean,
    message: String,
    onProvider: (String) -> Unit,
    onUrl: (String) -> Unit,
    onApiKey: (String) -> Unit,
    onModel: (String) -> Unit,
    onLoadModels: () -> Unit,
    onStart: () -> Unit,
    onRetry: () -> Unit,
) {
    Box(
        Modifier.fillMaxSize().background(Background).padding(24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Surface(
            color = Panel,
            shape = RoundedCornerShape(16.dp),
            modifier = Modifier.widthIn(max = 620.dp).fillMaxWidth(0.86f),
        ) {
            Column(Modifier.padding(24.dp)) {
                Text("Start GRID", color = Color.White, fontSize = 26.sp, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(4.dp))
                Text(
                    "Choose a provider. GRID writes config.json and starts the local host for you.",
                    color = Muted,
                    fontSize = 12.sp,
                )
                Spacer(Modifier.height(18.dp))
                ProviderForm(
                    providers = DEFAULT_PROVIDERS,
                    provider = provider,
                    url = url,
                    apiKey = apiKey,
                    keySet = keySet,
                    model = model,
                    models = models,
                    busy = busy,
                    onProvider = onProvider,
                    onUrl = onUrl,
                    onApiKey = onApiKey,
                    onModel = onModel,
                    onLoadModels = onLoadModels,
                )
                Spacer(Modifier.height(16.dp))
                Button(
                    onClick = onStart,
                    enabled = !busy,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = GridGreen,
                        contentColor = Color.Black,
                    ),
                    modifier = Modifier.fillMaxWidth().height(44.dp),
                ) {
                    Text(if (busy) "Working…" else "Start GRID host")
                }
                Spacer(Modifier.height(8.dp))
                OutlinedButton(
                    onClick = onRetry,
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Connect to a running host") }
                if (message.isNotBlank()) {
                    Spacer(Modifier.height(10.dp))
                    Text(
                        message,
                        color = GridGreenDim,
                        fontSize = 11.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                }
                Spacer(Modifier.height(10.dp))
                Text(
                    "Endpoint: $baseUrl",
                    color = Muted,
                    fontSize = 10.sp,
                    fontFamily = FontFamily.Monospace,
                )
                if (projectRoot == null) {
                    Spacer(Modifier.height(6.dp))
                    Text(
                        "Project root not found. Start the desktop from the GRID folder or pass --root.",
                        color = Danger,
                        fontSize = 11.sp,
                    )
                }
            }
        }
    }
}

@Composable
private fun ProviderForm(
    providers: List<ProviderOption>,
    provider: String,
    url: String,
    apiKey: String,
    keySet: Boolean,
    model: String,
    models: List<String>,
    busy: Boolean,
    onProvider: (String) -> Unit,
    onUrl: (String) -> Unit,
    onApiKey: (String) -> Unit,
    onModel: (String) -> Unit,
    onLoadModels: () -> Unit,
) {
    var providerMenu by remember { mutableStateOf(false) }
    var modelMenu by remember { mutableStateOf(false) }
    val selected = providers.firstOrNull { it.id == provider }
        ?: providers.firstOrNull()
        ?: DEFAULT_PROVIDERS.first()

    Text("PROVIDER", color = Muted, fontSize = 10.sp, letterSpacing = 1.5.sp)
    Spacer(Modifier.height(4.dp))
    Box {
        OutlinedButton(
            onClick = { providerMenu = true },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(
                selected.name,
                fontSize = 12.sp,
                color = if (selected.available) Color.White else Muted,
            )
            Spacer(Modifier.weight(1f))
            Text("▾", color = Muted, fontSize = 12.sp)
        }
        DropdownMenu(
            expanded = providerMenu,
            onDismissRequest = { providerMenu = false },
        ) {
            providers.forEach { option ->
                DropdownMenuItem(
                    text = {
                        Column {
                            Text(
                                option.name,
                                fontSize = 12.sp,
                                color = if (option.available) Color.White else Muted,
                            )
                            Text(
                                if (option.available) option.description else "Not installed",
                                fontSize = 10.sp,
                                color = Muted,
                            )
                        }
                    },
                    enabled = option.available,
                    onClick = {
                        providerMenu = false
                        onProvider(option.id)
                    },
                )
            }
        }
    }
    Spacer(Modifier.height(10.dp))
    OutlinedTextField(
        value = url,
        onValueChange = onUrl,
        label = { Text("Base URL") },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
    )
    if (selected.needsKey) {
        Spacer(Modifier.height(10.dp))
        OutlinedTextField(
            value = apiKey,
            onValueChange = onApiKey,
            label = { Text("API key") },
            placeholder = {
                Text(if (keySet) "Saved — leave blank to keep" else "Required", color = Muted)
            },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth(),
        )
    }
    Spacer(Modifier.height(10.dp))
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.weight(1f)) {
            OutlinedTextField(
                value = model,
                onValueChange = onModel,
                label = { Text("Model") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                trailingIcon = {
                    Text(
                        "▾",
                        color = Muted,
                        fontSize = 12.sp,
                        modifier = Modifier
                            .clickable {
                                if (models.isEmpty()) onLoadModels() else modelMenu = true
                            }
                            .padding(horizontal = 8.dp, vertical = 4.dp),
                    )
                },
            )
            DropdownMenu(
                expanded = modelMenu,
                onDismissRequest = { modelMenu = false },
            ) {
                models.take(120).forEach { candidate ->
                    DropdownMenuItem(
                        text = { Text(candidate, fontSize = 11.sp) },
                        onClick = {
                            onModel(candidate)
                            modelMenu = false
                        },
                    )
                }
            }
        }
        Spacer(Modifier.width(8.dp))
        OutlinedButton(onClick = onLoadModels, enabled = !busy) {
            Text(if (busy) "…" else "Refresh", fontSize = 11.sp)
        }
    }
    if (models.isNotEmpty()) {
        Spacer(Modifier.height(4.dp))
        Text(
            "${models.size} models available",
            color = Muted,
            fontSize = 9.sp,
            fontFamily = FontFamily.Monospace,
        )
    }
}

@Composable
private fun ProviderDialog(
    baseUrl: String,
    token: String,
    currentProvider: String,
    currentModel: String,
    currentBaseUrl: String,
    serverProviders: List<ProviderOption>,
    onDismiss: () -> Unit,
    onSwitched: (String, String, List<String>) -> Unit,
) {
    val scope = rememberCoroutineScope()
    var provider by remember {
        mutableStateOf(currentProvider.ifBlank { "ollama" })
    }
    var url by remember {
        mutableStateOf(currentBaseUrl.ifBlank { providerDefaultUrl(provider) })
    }
    var apiKey by remember { mutableStateOf("") }
    var keySet by remember {
        mutableStateOf(serverProviders.firstOrNull { it.id == provider }?.keySet ?: false)
    }
    var model by remember { mutableStateOf(currentModel) }
    var models by remember { mutableStateOf(emptyList<String>()) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var reloadKey by remember { mutableStateOf(0) }

    fun selectProvider(id: String) {
        if (provider != id) model = ""
        provider = id
        if (url.isBlank() || DEFAULT_PROVIDERS.any { it.defaultUrl == url }) {
            url = providerDefaultUrl(id)
        }
        apiKey = ""
        keySet = serverProviders.firstOrNull { it.id == id }?.keySet ?: false
        models = emptyList()
        reloadKey += 1
    }

    fun loadModels() {
        if (busy) return
        busy = true
        message = "Loading models..."
        scope.launch {
            try {
                val list = withContext(Dispatchers.IO) {
                    postProviderModels(baseUrl, token, provider, url, apiKey)
                }
                models = list
                if (model.isBlank() && list.isNotEmpty()) model = list.first()
                message = if (list.isEmpty()) {
                    "No models found. Check the URL and API key."
                } else {
                    "${list.size} models loaded."
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                message = error.message ?: "Could not load models."
            } finally {
                busy = false
            }
        }
    }

    fun switchProvider() {
        if (busy) return
        if (model.isBlank()) {
            message = "Model is required."
            return
        }
        busy = true
        message = "Switching provider..."
        scope.launch {
            try {
                withContext(Dispatchers.IO) {
                    postProvider(baseUrl, token, provider, url, model, apiKey)
                }
                val list = models.ifEmpty { listOf(model) }
                onSwitched(provider, model, list)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                message = error.message ?: "Provider switch failed."
                busy = false
            }
        }
    }

    LaunchedEffect(reloadKey) {
        loadModels()
    }

    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text("Change provider") },
        text = {
            Column {
                ProviderForm(
                    providers = serverProviders,
                    provider = provider,
                    url = url,
                    apiKey = apiKey,
                    keySet = keySet,
                    model = model,
                    models = models,
                    busy = busy,
                    onProvider = { selectProvider(it) },
                    onUrl = { url = it },
                    onApiKey = { apiKey = it },
                    onModel = { model = it },
                    onLoadModels = { loadModels() },
                )
                if (message.isNotBlank()) {
                    Spacer(Modifier.height(8.dp))
                    Text(message, color = Muted, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { switchProvider() }, enabled = !busy) {
                Text("Switch", color = GridGreen)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !busy) {
                Text("Cancel", color = Muted)
            }
        },
        containerColor = PanelRaised,
        titleContentColor = Color.White,
        textContentColor = Muted,
    )
}

@Composable
private fun PairPhoneDialog(
    baseUrl: String,
    token: String,
    onDismiss: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    var info by remember { mutableStateOf<PairingInfo?>(null) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("Loading pairing code…") }
    var remaining by remember { mutableStateOf(0) }
    var copied by remember { mutableStateOf("") }

    fun load(rotate: Boolean) {
        if (busy) return
        busy = true
        message = if (rotate) "Generating a new code…" else "Loading pairing code…"
        scope.launch {
            try {
                info = withContext(Dispatchers.IO) {
                    fetchPairingInfo(baseUrl, token, rotate)
                }
                message = ""
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                message = error.message ?: "Could not load a pairing code."
            } finally {
                busy = false
            }
        }
    }

    fun copy(label: String, value: String) {
        if (value.isBlank()) return
        copyToClipboard(value)
        copied = label
    }

    LaunchedEffect(Unit) { load(false) }
    LaunchedEffect(info) {
        var left = info?.expiresIn ?: 0
        remaining = left
        while (left > 0) {
            delay(1000)
            left -= 1
            remaining = left
        }
    }
    LaunchedEffect(copied) {
        if (copied.isNotBlank()) {
            delay(1500)
            copied = ""
        }
    }

    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text("Pair Android phone") },
        text = {
            Column {
                Text(
                    "1. Open GRID on the phone and tap Find GRID on Wi-Fi.",
                    color = Muted,
                    fontSize = 11.sp,
                )
                Spacer(Modifier.height(10.dp))
                Text("2. Or enter this host URL:", color = Muted, fontSize = 10.sp)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        info?.url ?: "…",
                        color = GridGreenDim,
                        fontSize = 11.sp,
                        fontFamily = FontFamily.Monospace,
                        modifier = Modifier.weight(1f),
                    )
                    TextButton(
                        onClick = { info?.let { copy("url", it.url) } },
                        enabled = info != null,
                    ) {
                        Text(
                            if (copied == "url") "Copied" else "Copy",
                            color = if (copied == "url") GridGreen else Muted,
                            fontSize = 9.sp,
                        )
                    }
                }
                if (info?.url?.contains("127.0.0.1") == true ||
                    info?.url?.contains("localhost") == true
                ) {
                    Text(
                        "Host is loopback-only. Set api.host to 0.0.0.0 and restart.",
                        color = Warning,
                        fontSize = 10.sp,
                    )
                }
                Spacer(Modifier.height(12.dp))
                Text("3. Enter this one-time code:", color = Muted, fontSize = 10.sp)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        info?.code ?: "------",
                        color = GridGreen,
                        fontSize = 32.sp,
                        fontWeight = FontWeight.Bold,
                        fontFamily = FontFamily.Monospace,
                        letterSpacing = 6.sp,
                        modifier = Modifier.weight(1f),
                    )
                    TextButton(
                        onClick = { info?.let { copy("code", it.code) } },
                        enabled = info != null,
                    ) {
                        Text(
                            if (copied == "code") "Copied" else "Copy",
                            color = if (copied == "code") GridGreen else Muted,
                            fontSize = 9.sp,
                        )
                    }
                }
                Text(
                    when {
                        info == null -> message
                        remaining > 0 ->
                            "Valid ${remaining / 60}m ${remaining % 60}s · one-time"
                        else -> "Code expired — generate a new one."
                    },
                    color = if (info != null && remaining == 0) Warning else Muted,
                    fontSize = 10.sp,
                    fontFamily = FontFamily.Monospace,
                )
                if (info != null && message.isNotBlank()) {
                    Text(message, color = Danger, fontSize = 10.sp)
                }
                Spacer(Modifier.height(10.dp))
                Text(
                    "The phone stores the host token in the Android Keystore. " +
                        "The code cannot be reused.",
                    color = Muted,
                    fontSize = 9.sp,
                )
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) { Text("Close") }
        },
        dismissButton = {
            TextButton(onClick = { load(true) }, enabled = !busy) {
                Text("New code", color = GridGreen)
            }
        },
        containerColor = PanelRaised,
        titleContentColor = Color.White,
        textContentColor = Muted,
    )
}

@Composable
private fun Sidebar(
    status: String,
    threadId: String,
    baseUrl: String,
    tokenReady: Boolean,
    model: String,
    models: List<String>,
    provider: String,
    threads: List<ThreadSummary>,
    activeThreadId: String,
    totalTokens: Int,
    lastLatency: Long,
    lastTokens: Int,
    runCount: Int,
    onModelChange: (String) -> Unit,
    onProviderChange: () -> Unit,
    onPairPhone: () -> Unit,
    onThreadOpen: (String) -> Unit,
    onRefreshThreads: () -> Unit,
    onClearHistory: () -> Unit,
    onNewThread: () -> Unit,
    onQuickPrompt: (String) -> Unit,
) {
    var modelMenu by remember { mutableStateOf(false) }
    Column(
        Modifier
            .width(250.dp)
            .fillMaxHeight()
            .background(Panel)
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
    ) {
        Text("GRID", color = GridGreen, fontSize = 30.sp, fontWeight = FontWeight.Bold)
        Text("LOCAL AGENT HOST", color = Muted, fontSize = 11.sp, letterSpacing = 2.sp)
        Spacer(Modifier.height(22.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(9.dp)
                    .background(if (tokenReady) GridGreen else Danger, RoundedCornerShape(50))
            )
            Spacer(Modifier.width(8.dp))
            Text(status, color = Color.White, fontSize = 13.sp)
        }
        Spacer(Modifier.height(14.dp))
        Text("THREAD", color = Muted, fontSize = 10.sp, letterSpacing = 1.5.sp)
        SelectionContainer {
            Text(threadId, color = GridGreenDim, fontSize = 11.sp, fontFamily = FontFamily.Monospace)
        }
        Spacer(Modifier.height(14.dp))
        Text("ENDPOINT", color = Muted, fontSize = 10.sp, letterSpacing = 1.5.sp)
        Text(baseUrl, color = GridGreenDim, fontSize = 11.sp, fontFamily = FontFamily.Monospace)
        Spacer(Modifier.height(12.dp))
        Text("PROVIDER", color = Muted, fontSize = 10.sp, letterSpacing = 1.5.sp)
        Text(
            providerLabel(provider),
            color = GridGreenDim,
            fontSize = 11.sp,
            fontFamily = FontFamily.Monospace,
            maxLines = 1,
        )
        Box {
            OutlinedButton(
                onClick = onProviderChange,
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Change provider", fontSize = 11.sp) }
        }
        Spacer(Modifier.height(12.dp))
        Text("MODEL", color = Muted, fontSize = 10.sp, letterSpacing = 1.5.sp)
        Text(
            model.ifBlank { "(unknown)" },
            color = GridGreenDim,
            fontSize = 11.sp,
            fontFamily = FontFamily.Monospace,
            maxLines = 1,
        )
        Box {
            OutlinedButton(
                onClick = { modelMenu = true },
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Change model", fontSize = 11.sp) }
            DropdownMenu(
                expanded = modelMenu,
                onDismissRequest = { modelMenu = false },
            ) {
                if (models.isEmpty()) {
                    DropdownMenuItem(
                        text = { Text("No models found", fontSize = 12.sp) },
                        onClick = { modelMenu = false },
                    )
                }
                models.forEach { candidate ->
                    DropdownMenuItem(
                        text = { Text(candidate, fontSize = 12.sp) },
                        onClick = {
                            modelMenu = false
                            onModelChange(candidate)
                        },
                    )
                }
            }
        }
        Spacer(Modifier.height(12.dp))
        Text("TOKEN METER", color = Muted, fontSize = 10.sp, letterSpacing = 1.5.sp)
        Text(
            "${formatTokens(totalTokens)} total · $runCount runs",
            color = GridGreenDim,
            fontSize = 11.sp,
            fontFamily = FontFamily.Monospace,
        )
        Text(
            "last ${formatDuration(lastLatency)} · ${formatTokens(lastTokens)} tok",
            color = Muted,
            fontSize = 10.sp,
            fontFamily = FontFamily.Monospace,
        )
        Spacer(Modifier.height(14.dp))
        Button(
            onClick = onNewThread,
            colors = ButtonDefaults.buttonColors(containerColor = PanelRaised, contentColor = GridGreen),
            modifier = Modifier.fillMaxWidth(),
        ) { Text("New thread") }
        Spacer(Modifier.height(8.dp))
        OutlinedButton(
            onClick = onPairPhone,
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Pair phone", fontSize = 11.sp) }
        Spacer(Modifier.height(10.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("HISTORY", color = Muted, fontSize = 10.sp, letterSpacing = 1.5.sp)
            Spacer(Modifier.weight(1f))
            Text(
                "Refresh",
                color = Muted,
                fontSize = 9.sp,
                modifier = Modifier
                    .clickable { onRefreshThreads() }
                    .padding(horizontal = 4.dp, vertical = 2.dp),
            )
            Text(
                "Clear",
                color = Danger,
                fontSize = 9.sp,
                modifier = Modifier
                    .clickable { onClearHistory() }
                    .padding(horizontal = 4.dp, vertical = 2.dp),
            )
        }
        if (threads.isEmpty()) {
            Text("No saved threads", color = Muted, fontSize = 10.sp)
        } else {
            threads.take(12).forEach { thread ->
                Column(
                    Modifier
                        .fillMaxWidth()
                        .clickable { onThreadOpen(thread.id) }
                        .padding(vertical = 3.dp)
                ) {
                    Text(
                        thread.title.ifBlank { "Untitled" },
                        color = if (thread.id == activeThreadId) GridGreen else GridGreenDim,
                        fontSize = 11.sp,
                        maxLines = 1,
                    )
                    Text(
                        "${thread.messageCount} messages",
                        color = Muted,
                        fontSize = 9.sp,
                    )
                }
            }
        }
        Spacer(Modifier.height(12.dp))
        Text("QUICK START", color = Muted, fontSize = 10.sp, letterSpacing = 1.5.sp)
        Spacer(Modifier.height(8.dp))
        listOf(
            "system info",
            "ping 127.0.0.1",
            "rea authorized http://127.0.0.1:8765/",
        ).forEach { prompt ->
            OutlinedButton(
                onClick = { onQuickPrompt(prompt) },
                modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp),
            ) {
                Text(prompt, fontSize = 11.sp, maxLines = 2)
            }
        }
        Spacer(Modifier.weight(1f))
        if (!tokenReady) {
            Text(
                "Missing run/api_token.\nStart: python grid_agent.py --api --no-input",
                color = Danger,
                fontSize = 11.sp,
            )
        } else {
            Text("AG-UI 1.0 · local only", color = Muted, fontSize = 10.sp)
        }
    }
}

@Composable
private fun Header(status: String, threadId: String) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text("Command Center", color = Color.White, fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
            Text(threadId, color = Muted, fontSize = 11.sp, fontFamily = FontFamily.Monospace)
        }
        Text(status, color = GridGreenDim, fontSize = 12.sp)
    }
    Spacer(Modifier.height(10.dp))
    HorizontalDivider(color = PanelRaised)
}

@Composable
private fun UserBubble(text: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
        Surface(
            color = Color(0xFF123326),
            shape = RoundedCornerShape(14.dp),
            modifier = Modifier.fillMaxWidth(0.78f),
        ) {
            Box(Modifier.padding(start = 13.dp, top = 10.dp, end = 10.dp, bottom = 13.dp)) {
                Text(
                    text,
                    color = Color.White,
                    modifier = Modifier.padding(end = 26.dp),
                    fontSize = 14.sp,
                )
                CopyButton(
                    text = text,
                    modifier = Modifier.align(Alignment.TopEnd),
                    tint = Color.White.copy(alpha = 0.6f),
                )
            }
        }
    }
}

@Composable
private fun AssistantBubble(item: Item.Assistant) {
    Surface(
        color = PanelRaised,
        shape = RoundedCornerShape(14.dp),
        modifier = Modifier.fillMaxWidth(0.9f),
    ) {
        Column(Modifier.padding(14.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
                SelectionContainer(Modifier.weight(1f)) {
                    Text(
                        item.text.ifBlank { "…" },
                        color = Color.White,
                        fontSize = 14.sp,
                        lineHeight = 21.sp,
                    )
                }
                Spacer(Modifier.width(8.dp))
                CopyButton(text = item.text)
            }
            if (item.durationMs > 0 || item.tokens > 0) {
                Spacer(Modifier.height(6.dp))
                Text(
                    "${formatDuration(item.durationMs)} · " +
                        "${formatTokens(item.tokens)}${if (item.estimated) " est." else ""} tokens",
                    color = Muted,
                    fontSize = 10.sp,
                    fontFamily = FontFamily.Monospace,
                )
            }
        }
    }
}

@Composable
private fun CopyButton(
    text: String,
    modifier: Modifier = Modifier,
    tint: Color = Muted,
) {
    var copied by remember { mutableStateOf(false) }
    LaunchedEffect(copied) {
        if (copied) {
            delay(1_400)
            copied = false
        }
    }
    Row(
        modifier = modifier
            .clip(RoundedCornerShape(6.dp))
            .clickable {
                copyToClipboard(text)
                copied = true
            }
            .padding(4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (copied) {
            Box(Modifier.size(14.dp), contentAlignment = Alignment.Center) {
                Text("✓", color = GridGreen, fontSize = 12.sp)
            }
        } else {
            CopyIcon(tint)
        }
    }
}

@Composable
private fun CopyIcon(tint: Color) {
    Canvas(Modifier.size(14.dp)) {
        val stroke = 1.4.dp.toPx()
        val radius = CornerRadius(2.dp.toPx(), 2.dp.toPx())
        drawRoundRect(
            color = tint,
            topLeft = Offset(size.width * 0.30f, size.height * 0.08f),
            size = Size(size.width * 0.58f, size.height * 0.64f),
            cornerRadius = radius,
            style = Stroke(width = stroke),
        )
        drawRoundRect(
            color = tint,
            topLeft = Offset(size.width * 0.12f, size.height * 0.28f),
            size = Size(size.width * 0.58f, size.height * 0.64f),
            cornerRadius = radius,
            style = Stroke(width = stroke),
        )
    }
}

private fun copyToClipboard(text: String) {
    try {
        Toolkit.getDefaultToolkit().systemClipboard.setContents(StringSelection(text), null)
    } catch (_: Exception) {
    }
}

@Composable
private fun ToolCard(
    item: Item.Tool,
    onAction: (String, String) -> Unit,
    onApproval: (String, String) -> Unit,
    onOpenArtifact: (String) -> Unit,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color(0xFF0F1A13)),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(13.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("TOOL", color = GridGreen, fontSize = 10.sp, letterSpacing = 1.5.sp)
                Spacer(Modifier.width(8.dp))
                Text(item.name, color = Color.White, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.weight(1f))
                if (item.result == null) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(14.dp),
                        color = GridGreen,
                        strokeWidth = 2.dp,
                    )
                } else {
                    CopyButton(item.result)
                }
            }
            if (!item.ui.isNullOrBlank()) {
                Spacer(Modifier.height(8.dp))
                GridUiRenderer(
                    surfaceId = item.surfaceId.ifBlank { "tool:${item.callId}" },
                    root = item.ui,
                    fallback = item.result.orEmpty(),
                    onAction = onAction,
                    onApproval = onApproval,
                    onOpenArtifact = onOpenArtifact,
                )
            } else {
                if (item.args.isNotBlank()) {
                    Spacer(Modifier.height(7.dp))
                    Text(item.args, color = Muted, fontSize = 11.sp, fontFamily = FontFamily.Monospace)
                }
                item.result?.let { result ->
                    Spacer(Modifier.height(9.dp))
                    HorizontalDivider(color = PanelRaised)
                    Spacer(Modifier.height(8.dp))
                    SelectionContainer {
                        Text(
                            result.take(1600),
                            color = GridGreenDim,
                            fontSize = 11.sp,
                            fontFamily = FontFamily.Monospace,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun UiSurfaceCard(
    item: Item.Ui,
    onAction: (String, String) -> Unit,
    onApproval: (String, String) -> Unit,
    onOpenArtifact: (String) -> Unit,
) {
    GridUiRenderer(
        surfaceId = item.surfaceId,
        root = item.root,
        fallback = item.fallback,
        onAction = onAction,
        onApproval = onApproval,
        onOpenArtifact = onOpenArtifact,
    )
}

@Composable
private fun GridUiRenderer(
    surfaceId: String,
    root: String,
    fallback: String,
    onAction: (String, String) -> Unit,
    onApproval: (String, String) -> Unit,
    onOpenArtifact: (String) -> Unit,
) {
    val node = remember(root) {
        runCatching { Json.parseToJsonElement(root).jsonObject }.getOrNull()
    }
    if (node == null) {
        UiFallback(fallback)
    } else {
        GridUiNode(
            node = node,
            surfaceId = surfaceId,
            fallback = fallback,
            onAction = onAction,
            onApproval = onApproval,
            onOpenArtifact = onOpenArtifact,
        )
    }
}

@Composable
private fun UiFallback(text: String) {
    SelectionContainer {
        Text(
            text.ifBlank { "Unsupported UI surface." },
            color = GridGreenDim,
            fontSize = 11.sp,
            fontFamily = FontFamily.Monospace,
        )
    }
}

private fun JsonObject.uiString(key: String): String =
    this[key]?.jsonPrimitive?.contentOrNull ?: ""

private fun JsonObject.uiArray(key: String): List<JsonObject> =
    (this[key] as? kotlinx.serialization.json.JsonArray)
        ?.mapNotNull { it as? JsonObject }
        ?: emptyList()

private fun uiToneColor(tone: String): Color = when (tone) {
    "success" -> Color(0xFF102A19)
    "warning" -> Color(0xFF2A2410)
    "danger" -> Color(0xFF2A1414)
    else -> Color(0xFF101A13)
}

@Composable
private fun GridUiNode(
    node: JsonObject,
    surfaceId: String,
    fallback: String,
    onAction: (String, String) -> Unit,
    onApproval: (String, String) -> Unit,
    onOpenArtifact: (String) -> Unit,
) {
    when (node.uiString("type")) {
        "card" -> UiCard(node, surfaceId, fallback, onAction, onApproval, onOpenArtifact)
        "markdown" -> UiMarkdown(node.uiString("text"))
        "keyValue" -> UiKeyValue(node)
        "table" -> UiTable(node)
        "button" -> UiButton(node, onAction)
        "form" -> UiForm(node, onAction)
        "approval" -> UiApproval(node, onApproval)
        "artifact" -> UiArtifact(node, onOpenArtifact)
        "chart" -> UiChart(node)
        else -> UiFallback(fallback)
    }
}

@Composable
private fun UiCard(
    node: JsonObject,
    surfaceId: String,
    fallback: String,
    onAction: (String, String) -> Unit,
    onApproval: (String, String) -> Unit,
    onOpenArtifact: (String) -> Unit,
) {
    val title = node.uiString("title")
    val subtitle = node.uiString("subtitle")
    val tone = node.uiString("tone")
    Surface(
        color = uiToneColor(tone),
        shape = RoundedCornerShape(10.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(12.dp)) {
            if (title.isNotBlank()) {
                Text(
                    title,
                    color = Color.White,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                )
            }
            if (subtitle.isNotBlank()) {
                Spacer(Modifier.height(2.dp))
                Text(subtitle, color = Muted, fontSize = 10.sp)
            }
            val children = node.uiArray("children")
            if (children.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    children.forEach { child ->
                        GridUiNode(
                            node = child,
                            surfaceId = surfaceId,
                            fallback = fallback,
                            onAction = onAction,
                            onApproval = onApproval,
                            onOpenArtifact = onOpenArtifact,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun UiMarkdown(text: String) {
    if (text.isBlank()) return
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        var inCode = false
        text.lines().forEach { raw ->
            val line = raw.trimEnd()
            if (line.trimStart().startsWith("```")) {
                inCode = !inCode
                return@forEach
            }
            when {
                inCode -> Text(
                    line,
                    color = GridGreenDim,
                    fontSize = 11.sp,
                    fontFamily = FontFamily.Monospace,
                )
                line.startsWith("### ") -> Text(
                    line.removePrefix("### "),
                    color = Color.White,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.SemiBold,
                )
                line.startsWith("## ") || line.startsWith("# ") -> Text(
                    line.removePrefix("## ").removePrefix("# "),
                    color = Color.White,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                )
                line.startsWith("- ") || line.startsWith("* ") -> Row {
                    Text("• ", color = GridGreen, fontSize = 11.sp)
                    SelectionContainer {
                        Text(line.drop(2), color = GridGreenDim, fontSize = 11.sp)
                    }
                }
                line.isBlank() -> Spacer(Modifier.height(3.dp))
                else -> SelectionContainer {
                    Text(line, color = GridGreenDim, fontSize = 11.sp, lineHeight = 17.sp)
                }
            }
        }
    }
}

@Composable
private fun UiKeyValue(node: JsonObject) {
    val items = node.uiArray("items")
    if (items.isEmpty()) return
    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
        items.forEach { item ->
            val label = item.uiString("label")
            val value = item.uiString("value")
            Row(Modifier.fillMaxWidth()) {
                Text(
                    label,
                    color = Muted,
                    fontSize = 10.sp,
                    modifier = Modifier.width(145.dp),
                )
                SelectionContainer(Modifier.weight(1f)) {
                    Text(
                        value.ifBlank { "—" },
                        color = GridGreenDim,
                        fontSize = 11.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                }
            }
        }
    }
}

@Composable
private fun UiTable(node: JsonObject) {
    val columns = (node["columns"] as? kotlinx.serialization.json.JsonArray)
        ?.mapNotNull { it.jsonPrimitive.contentOrNull }
        ?: emptyList()
    val rows = (node["rows"] as? kotlinx.serialization.json.JsonArray)
        ?.map { row ->
            (row as? kotlinx.serialization.json.JsonArray)
                ?.mapNotNull { it.jsonPrimitive.contentOrNull }
                ?: emptyList()
        }
        ?: emptyList()
    if (columns.isEmpty() && rows.isEmpty()) return
    val scroll = rememberScrollState()
    Column(Modifier.fillMaxWidth().horizontalScroll(scroll)) {
        Row(
            Modifier
                .background(PanelRaised, RoundedCornerShape(4.dp))
                .padding(horizontal = 6.dp, vertical = 5.dp)
        ) {
            columns.forEach { column ->
                Text(
                    column,
                    color = GridGreen,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.width(150.dp),
                )
            }
        }
        rows.forEach { row ->
            Row(Modifier.padding(horizontal = 6.dp, vertical = 4.dp)) {
                row.forEach { cell ->
                    Text(
                        cell,
                        color = GridGreenDim,
                        fontSize = 10.sp,
                        fontFamily = FontFamily.Monospace,
                        modifier = Modifier.width(150.dp),
                    )
                }
            }
            HorizontalDivider(color = PanelRaised)
        }
    }
}

@Composable
private fun UiButton(node: JsonObject, onAction: (String, String) -> Unit) {
    val label = node.uiString("label").ifBlank { "Action" }
    val action = node.uiString("action").ifBlank { "noop" }
    val payload = node["payload"]?.toString() ?: "{}"
    val style = node.uiString("style")
    val onClick = { onAction(action, payload) }
    when (style) {
        "primary" -> Button(
            onClick = onClick,
            colors = ButtonDefaults.buttonColors(containerColor = GridGreen, contentColor = Color.Black),
        ) { Text(label, fontSize = 11.sp) }
        "danger" -> OutlinedButton(onClick = onClick) {
            Text(label, color = Danger, fontSize = 11.sp)
        }
        else -> OutlinedButton(onClick = onClick) {
            Text(label, fontSize = 11.sp)
        }
    }
}

@Composable
private fun UiForm(node: JsonObject, onAction: (String, String) -> Unit) {
    val fields = node.uiArray("fields")
    val initial = remember(node) {
        buildMap {
            fields.forEach { field ->
                val name = field.uiString("name")
                if (name.isNotBlank()) {
                    val value = field.uiString("value")
                    val options = (field["options"] as? kotlinx.serialization.json.JsonArray)
                        ?.mapNotNull { it.jsonPrimitive.contentOrNull }
                        ?: emptyList()
                    put(name, value.ifBlank { options.firstOrNull() ?: "" })
                }
            }
        }
    }
    var values by remember(node) { mutableStateOf(initial) }
    var openSelect by remember(node) { mutableStateOf("") }
    val title = node.uiString("title")
    val action = node.uiString("action").ifBlank { "form.submit" }
    val submitLabel = node.uiString("submitLabel").ifBlank { "Submit" }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (title.isNotBlank()) {
            Text(title, color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
        }
        fields.forEach { field ->
            val name = field.uiString("name")
            val label = field.uiString("label").ifBlank { name }
            val type = field.uiString("type")
            val value = values[name].orEmpty()
            when (type) {
                "toggle" -> Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(label, color = GridGreenDim, fontSize = 11.sp, modifier = Modifier.weight(1f))
                    Switch(
                        checked = value == "true",
                        onCheckedChange = { values = values + (name to if (it) "true" else "false") },
                    )
                }
                "select" -> {
                    val options = (field["options"] as? kotlinx.serialization.json.JsonArray)
                        ?.mapNotNull { it.jsonPrimitive.contentOrNull }
                        ?: emptyList()
                    Box {
                        OutlinedButton(
                            onClick = { openSelect = name },
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Text(value.ifBlank { label }, fontSize = 11.sp)
                            Spacer(Modifier.weight(1f))
                            Text("▾", color = Muted, fontSize = 11.sp)
                        }
                        DropdownMenu(
                            expanded = openSelect == name,
                            onDismissRequest = { openSelect = "" },
                        ) {
                            options.forEach { option ->
                                DropdownMenuItem(
                                    text = { Text(option, fontSize = 11.sp) },
                                    onClick = {
                                        values = values + (name to option)
                                        openSelect = ""
                                    },
                                )
                            }
                        }
                    }
                }
                else -> OutlinedTextField(
                    value = value,
                    onValueChange = { values = values + (name to it) },
                    label = { Text(label, fontSize = 11.sp) },
                    singleLine = true,
                    visualTransformation = if (type == "password") {
                        PasswordVisualTransformation()
                    } else {
                        androidx.compose.ui.text.input.VisualTransformation.None
                    },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
        Button(
            onClick = {
                val payload = buildJsonObject {
                    values.forEach { (key, value) -> put(key, value) }
                }.toString()
                onAction(action, payload)
            },
            colors = ButtonDefaults.buttonColors(containerColor = GridGreen, contentColor = Color.Black),
        ) {
            Text(submitLabel, fontSize = 11.sp)
        }
    }
}

@Composable
private fun UiApproval(node: JsonObject, onApproval: (String, String) -> Unit) {
    var resolved by remember(node) { mutableStateOf("") }
    val approvalId = node.uiString("approvalId")
    val tool = node.uiString("tool")
    val risk = node.uiString("risk")
    val input = node.uiString("input")
    Surface(
        color = Color(0xFF231E10),
        shape = RoundedCornerShape(10.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(12.dp)) {
            Text("APPROVAL REQUIRED", color = Warning, fontSize = 10.sp, letterSpacing = 1.5.sp)
            Spacer(Modifier.height(5.dp))
            Text(tool, color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
            Text("risk: $risk", color = Muted, fontSize = 10.sp)
            if (input.isNotBlank()) {
                Spacer(Modifier.height(6.dp))
                SelectionContainer {
                    Text(
                        input.take(1200),
                        color = GridGreenDim,
                        fontSize = 10.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                }
            }
            Spacer(Modifier.height(9.dp))
            if (resolved.isNotBlank()) {
                Text("Answered: $resolved", color = GridGreenDim, fontSize = 11.sp)
            } else {
                Row {
                    Button(
                        onClick = {
                            resolved = "approve"
                            onApproval(approvalId, "approve")
                        },
                        colors = ButtonDefaults.buttonColors(
                            containerColor = GridGreen,
                            contentColor = Color.Black,
                        ),
                    ) { Text("Approve", fontSize = 11.sp) }
                    Spacer(Modifier.width(8.dp))
                    OutlinedButton(onClick = {
                        resolved = "deny"
                        onApproval(approvalId, "deny")
                    }) { Text("Deny", fontSize = 11.sp) }
                }
            }
        }
    }
}

@Composable
private fun UiArtifact(node: JsonObject, onOpenArtifact: (String) -> Unit) {
    val path = node.uiString("path")
    val label = node.uiString("label").ifBlank { "Open" }
    val kind = node.uiString("kind")
    Card(
        colors = CardDefaults.cardColors(containerColor = Color(0xFF102016)),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(
                    kind.ifBlank { "ARTIFACT" }.uppercase(),
                    color = GridGreen,
                    fontSize = 9.sp,
                    letterSpacing = 1.2.sp,
                )
                Spacer(Modifier.height(3.dp))
                SelectionContainer {
                    Text(
                        path,
                        color = GridGreenDim,
                        fontSize = 10.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                }
            }
            Spacer(Modifier.width(8.dp))
            OutlinedButton(onClick = { onOpenArtifact(path) }) {
                Text(label, fontSize = 10.sp)
            }
        }
    }
}

@Composable
private fun UiChart(node: JsonObject) {
    val labels = (node["labels"] as? kotlinx.serialization.json.JsonArray)
        ?.mapNotNull { it.jsonPrimitive.contentOrNull }
        ?: emptyList()
    val values = (node["values"] as? kotlinx.serialization.json.JsonArray)
        ?.mapNotNull { it.jsonPrimitive.doubleOrNull }
        ?: emptyList()
    if (values.isEmpty()) return
    val max = values.maxOrNull()?.coerceAtLeast(1.0) ?: 1.0
    val title = node.uiString("title")
    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
        if (title.isNotBlank()) {
            Text(title, color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
        }
        Row(
            modifier = Modifier.fillMaxWidth().height(96.dp),
            verticalAlignment = Alignment.Bottom,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            values.forEachIndexed { index, value ->
                Column(
                    modifier = Modifier.weight(1f),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Box(
                        Modifier
                            .fillMaxWidth(0.55f)
                            .height((value / max * 72.0).toFloat().dp)
                            .background(GridGreen, RoundedCornerShape(2.dp))
                    )
                    Spacer(Modifier.height(3.dp))
                    Text(
                        labels.getOrNull(index).orEmpty(),
                        color = Muted,
                        fontSize = 8.sp,
                        maxLines = 1,
                    )
                }
            }
        }
    }
}

@Composable
private fun ArtifactCard(path: String) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color(0xFF102016)),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("REA REPORT", color = GridGreen, fontSize = 10.sp, letterSpacing = 1.5.sp)
                Spacer(Modifier.height(4.dp))
                SelectionContainer {
                    Text(path, color = GridGreenDim, fontSize = 11.sp, fontFamily = FontFamily.Monospace)
                }
            }
            Spacer(Modifier.width(12.dp))
            OutlinedButton(onClick = { openPath(path) }) { Text("Open") }
        }
    }
}

@Composable
private fun ApprovalCard(
    approval: Item.Approval,
    onApprove: () -> Unit,
    onDeny: () -> Unit,
) {
    var armed by remember(approval.id) { mutableStateOf(false) }
    LaunchedEffect(approval.id) {
        delay(600.milliseconds)
        armed = true
    }
    Card(
        colors = CardDefaults.cardColors(containerColor = Color(0xFF231E10)),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(14.dp)) {
            Text("APPROVAL REQUIRED", color = Warning, fontSize = 10.sp, letterSpacing = 1.5.sp)
            Spacer(Modifier.height(6.dp))
            Text(approval.tool, color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
            Text("risk: ${approval.risk}", color = Muted, fontSize = 11.sp)
            Spacer(Modifier.height(7.dp))
            SelectionContainer {
                Text(
                    approval.input,
                    color = GridGreenDim,
                    fontSize = 11.sp,
                    fontFamily = FontFamily.Monospace,
                )
            }
            Spacer(Modifier.height(11.dp))
            if (approval.resolved) {
                Text("Answered", color = GridGreenDim, fontSize = 12.sp)
            } else {
                Row {
                    Button(
                        onClick = onApprove,
                        enabled = armed,
                        colors = ButtonDefaults.buttonColors(containerColor = GridGreen, contentColor = Color.Black),
                    ) { Text("Approve") }
                    Spacer(Modifier.width(8.dp))
                    OutlinedButton(onClick = onDeny, enabled = armed) { Text("Deny") }
                }
            }
        }
    }
}

@Composable
private fun ActivityCard(activity: Item.Activity) {
    var dots by remember(activity.running) { mutableStateOf(1) }
    var seconds by remember(activity.running) { mutableStateOf(0) }
    LaunchedEffect(activity.running) {
        if (!activity.running) return@LaunchedEffect
        while (true) {
            delay(450)
            dots = (dots % 3) + 1
        }
    }
    LaunchedEffect(activity.running) {
        if (!activity.running) return@LaunchedEffect
        while (true) {
            delay(1_000)
            seconds += 1
        }
    }
    val summary = activityText(activity)
    val label = when {
        activity.total == 0 -> "Thinking" + ".".repeat(dots)
        else -> "+$summary"
    }
    Surface(
        color = Color(0xFF0E1711),
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (activity.running) {
                CircularProgressIndicator(
                    modifier = Modifier.size(13.dp),
                    color = GridGreen,
                    strokeWidth = 2.dp,
                )
            } else {
                Text("✓", color = GridGreenDim, fontSize = 11.sp)
            }
            Spacer(Modifier.width(9.dp))
            Text(
                label,
                color = if (activity.running) GridGreenDim else Muted,
                fontSize = 11.sp,
                fontFamily = FontFamily.Monospace,
            )
            if (activity.running && seconds > 0) {
                Spacer(Modifier.width(8.dp))
                Text("${seconds}s", color = Muted, fontSize = 10.sp)
            }
        }
    }
}

private fun activityText(activity: Item.Activity): String {
    val parts = mutableListOf<String>()
    fun add(count: Int, singular: String, plural: String) {
        if (count > 0) parts.add("$count ${if (count == 1) singular else plural}")
    }
    add(activity.commands, "command", "commands")
    add(activity.edits, "edit", "edits")
    add(activity.thoughts, "thought", "thoughts")
    add(activity.reads, "read", "reads")
    add(activity.tools, "tool", "tools")
    return parts.joinToString(" · ")
}

@Composable
private fun ErrorCard(message: String) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color(0xFF2A1414)),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(message, color = Danger, modifier = Modifier.padding(13.dp), fontSize = 12.sp)
    }
}

@Composable
private fun NoteCard(message: String) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color(0xFF102016)),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Box(Modifier.padding(start = 13.dp, top = 10.dp, end = 10.dp, bottom = 13.dp)) {
            SelectionContainer(Modifier.padding(end = 26.dp)) {
                Text(
                    message,
                    color = GridGreenDim,
                    fontSize = 12.sp,
                    fontFamily = FontFamily.Monospace,
                )
            }
            CopyButton(
                text = message,
                modifier = Modifier.align(Alignment.TopEnd),
            )
        }
    }
}

private data class PaletteEntry(
    val label: String,
    val description: String,
    val applyText: String,
    val executeText: String? = null,
)

@Composable
private fun Composer(
    input: TextFieldValue,
    busy: Boolean,
    runActive: Boolean,
    enabled: Boolean,
    focusRequester: FocusRequester,
    tools: List<ToolInfo>,
    onInput: (TextFieldValue) -> Unit,
    onCommand: (String) -> Boolean,
    onSend: () -> Unit,
    onStop: () -> Unit,
) {
    val text = input.text
    val toolCommands = tools.map {
        SlashCommand(
            "/${it.name}",
            it.description,
            template = "/${it.name} ",
            subcommands = it.subcommands,
        )
    }
    val allCommands = (SLASH_COMMANDS + toolCommands)
        .groupBy { it.name.lowercase() }
        .map { (_, group) ->
            val app = group.first()
            val withSubs = group.firstOrNull { it.subcommands.isNotEmpty() }
            app.copy(
                subcommands = if (app.subcommands.isNotEmpty()) {
                    app.subcommands
                } else {
                    withSubs?.subcommands ?: emptyList()
                }
            )
        }
    val trimmed = text.trimStart()
    val startsWithSlash = trimmed.startsWith("/")
    val commandName = trimmed.substringBefore(" ")
    val afterCommand = trimmed.substringAfter(" ", "").trimStart()
    val activeCommand = allCommands.firstOrNull {
        it.name.equals(commandName, ignoreCase = true)
    }
    val hasSpace = trimmed.contains(" ")
    val showCommandMode = startsWithSlash && !hasSpace
    val showSubMode = startsWithSlash &&
        hasSpace &&
        activeCommand != null &&
        !afterCommand.contains(" ")
    val filteredCommands = allCommands.filter {
        it.name.removePrefix("/").startsWith(
            commandName.removePrefix("/"),
            ignoreCase = true,
        )
    }
    val filteredSubcommands = if (showSubMode) {
        activeCommand.subcommands.filter {
            it.name.startsWith(afterCommand, ignoreCase = true)
        }
    } else {
        emptyList()
    }
    var dismissed by remember { mutableStateOf(false) }
    var selected by remember { mutableStateOf(0) }
    val suggestionState = rememberLazyListState()
    val suggestions: List<PaletteEntry> = when {
        showCommandMode -> filteredCommands.map { command ->
            PaletteEntry(
                label = command.name,
                description = command.description,
                applyText = if (command.subcommands.isNotEmpty()) {
                    "${command.name} "
                } else {
                    command.template ?: "${command.name} "
                },
                executeText = if (command.template == null && command.subcommands.isEmpty()) {
                    command.name
                } else {
                    null
                },
            )
        }
        showSubMode -> filteredSubcommands.map { sub ->
            val args = sub.template
            PaletteEntry(
                label = sub.name,
                description = sub.description,
                applyText = if (args != null) {
                    "${commandName} $args"
                } else {
                    "$commandName ${sub.name} "
                },
                executeText = if (args == null) "$commandName ${sub.name}" else null,
            )
        }
        else -> emptyList()
    }
    val showSuggestions = !dismissed && suggestions.isNotEmpty()

    LaunchedEffect(text) {
        selected = 0
        dismissed = false
        if (suggestions.isNotEmpty()) suggestionState.scrollToItem(0)
    }

    LaunchedEffect(selected, suggestions.size) {
        if (suggestions.isNotEmpty()) {
            suggestionState.animateScrollToItem(selected.coerceIn(0, suggestions.lastIndex))
        }
    }

    fun apply(entry: PaletteEntry) {
        onInput(TextFieldValue(entry.applyText, TextRange(entry.applyText.length)))
        selected = 0
        dismissed = false
    }

    Column(Modifier.fillMaxWidth()) {
        if (showSuggestions) {
            Surface(
                color = PanelRaised,
                shape = RoundedCornerShape(10.dp),
                modifier = Modifier.fillMaxWidth().padding(bottom = 6.dp),
            ) {
                Column(Modifier.padding(6.dp)) {
                    Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 3.dp)) {
                        Text(
                            if (showSubMode) {
                                "SUBCOMMANDS · $commandName · ${suggestions.size}"
                            } else {
                                "COMMANDS · ${suggestions.size}/${allCommands.size}"
                            },
                            color = GridGreen,
                            fontSize = 9.sp,
                            letterSpacing = 1.2.sp,
                        )
                        Spacer(Modifier.weight(1f))
                        Text("↑↓ select · Tab complete · Esc close", color = Muted, fontSize = 9.sp)
                    }
                    LazyColumn(
                        state = suggestionState,
                        modifier = Modifier.fillMaxWidth().heightIn(max = 280.dp),
                    ) {
                        itemsIndexed(suggestions) { index, entry ->
                            Row(
                                Modifier
                                    .fillMaxWidth()
                                    .background(
                                        if (index == selected) Color(0xFF173B27) else Color.Transparent,
                                        RoundedCornerShape(6.dp),
                                    )
                                    .clickable { apply(entry) }
                                    .padding(horizontal = 8.dp, vertical = 7.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Text(
                                    entry.label,
                                    color = GridGreen,
                                    fontSize = 12.sp,
                                    fontFamily = FontFamily.Monospace,
                                    modifier = Modifier.width(140.dp),
                                )
                                Text("= ${entry.description}", color = Muted, fontSize = 11.sp)
                            }
                        }
                    }
                }
            }
        }
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom) {
            OutlinedTextField(
                value = input,
                onValueChange = onInput,
                modifier = Modifier.weight(1f).focusRequester(focusRequester).onPreviewKeyEvent { event ->
                    if (!enabled || event.type != KeyEventType.KeyDown) {
                        false
                    } else if (showSuggestions) {
                        when (event.key) {
                            Key.DirectionDown, Key.NumPadDirectionDown -> {
                                selected = (selected + 1) % suggestions.size
                                true
                            }
                            Key.DirectionUp, Key.NumPadDirectionUp -> {
                                selected = (selected - 1 + suggestions.size) % suggestions.size
                                true
                            }
                            Key.Tab -> {
                                apply(suggestions[selected])
                                true
                            }
                            Key.Escape -> {
                                dismissed = true
                                true
                            }
                            Key.Enter -> {
                                if (event.isShiftPressed) {
                                    false
                                } else {
                                    val entry = suggestions[selected]
                                    val current = text.trim()
                                    if (showSubMode && entry.executeText != null) {
                                        onCommand(entry.executeText)
                                        onInput(TextFieldValue(""))
                                    } else if (
                                        entry.executeText != null &&
                                        current.equals(entry.executeText, ignoreCase = true)
                                    ) {
                                        onCommand(current)
                                        onInput(TextFieldValue(""))
                                    } else {
                                        apply(entry)
                                    }
                                    true
                                }
                            }
                            else -> false
                        }
                    } else if (event.key == Key.Enter && !event.isShiftPressed) {
                        val trimmed = text.trim()
                        if (trimmed.startsWith("/")) {
                            onCommand(trimmed)
                            onInput(TextFieldValue(""))
                        } else {
                            onSend()
                        }
                        true
                    } else {
                        false
                    }
                },
                placeholder = {
                    Text("Ask GRID or type / for commands…", color = Muted)
                },
                maxLines = 4,
                enabled = enabled,
            )
            Spacer(Modifier.width(10.dp))
            if (runActive) {
                OutlinedButton(
                    onClick = onStop,
                    modifier = Modifier.height(56.dp),
                ) {
                    Text("Stop", color = Danger)
                }
            } else {
                Button(
                    onClick = {
                        val trimmed = text.trim()
                        if (trimmed.startsWith("/")) {
                            onCommand(trimmed)
                            onInput(TextFieldValue(""))
                        } else {
                            onSend()
                        }
                    },
                    enabled = enabled && !busy && text.isNotBlank(),
                    colors = ButtonDefaults.buttonColors(containerColor = GridGreen, contentColor = Color.Black),
                    modifier = Modifier.height(56.dp),
                ) {
                    if (busy) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(18.dp),
                            color = Color.Black,
                            strokeWidth = 2.dp,
                        )
                    } else {
                        Text("Send")
                    }
                }
            }
        }
    }
}

private data class ProviderOption(
    val id: String,
    val name: String,
    val description: String,
    val defaultUrl: String,
    val needsKey: Boolean,
    val available: Boolean = true,
    val keySet: Boolean = false,
)

private val DEFAULT_PROVIDERS = listOf(
    ProviderOption(
        "ollama",
        "Ollama",
        "Local models on this machine",
        "http://localhost:11434",
        needsKey = false,
    ),
    ProviderOption(
        "lm_studio",
        "LM Studio",
        "Local OpenAI-compatible server",
        "http://localhost:1234/v1",
        needsKey = false,
    ),
    ProviderOption(
        "openrouter",
        "OpenRouter",
        "Cloud models via openrouter.ai",
        "https://openrouter.ai/api/v1",
        needsKey = true,
    ),
    ProviderOption(
        "openai",
        "OpenAI",
        "OpenAI or OpenAI-compatible API",
        "https://api.openai.com/v1",
        needsKey = true,
    ),
)

private data class ProviderInfo(
    val provider: String,
    val model: String,
    val baseUrl: String,
    val providers: List<ProviderOption>,
)

private data class ThreadSummary(
    val id: String,
    val title: String,
    val updatedAt: String,
    val messageCount: Int,
)

private data class StoredMessage(
    val id: String,
    val role: String,
    val content: String,
    val name: String = "",
    val args: String = "",
    val ui: String = "",
    val surfaceId: String = "",
)

private data class ClearHistoryResult(
    val cleared: Int,
    val message: String,
)

private fun providerLabel(id: String): String =
    DEFAULT_PROVIDERS.firstOrNull { it.id == id }?.name ?: id.ifBlank { "unknown" }

private fun providerDefaultUrl(id: String): String =
    DEFAULT_PROVIDERS.firstOrNull { it.id == id }?.defaultUrl ?: ""

private fun providerNeedsKey(id: String): Boolean =
    DEFAULT_PROVIDERS.firstOrNull { it.id == id }?.needsKey ?: false

private data class ModelInfo(val model: String, val models: List<String>)

private data class ToolInfo(
    val name: String,
    val description: String,
    val subcommands: List<SlashSubcommand> = emptyList(),
)

private fun fetchTools(baseUrl: String, token: String): List<ToolInfo>? {
    return try {
        val connection = URI.create("$baseUrl/api/v1/tools").toURL().openConnection() as HttpURLConnection
        connection.requestMethod = "GET"
        connection.setRequestProperty("Authorization", "Bearer $token")
        connection.connectTimeout = 3000
        connection.readTimeout = 5000
        try {
            if (connection.responseCode != 200) {
                null
            } else {
                val root = Json
                    .parseToJsonElement(connection.inputStream.bufferedReader().readText())
                    .jsonObject
                root["tools"]?.jsonArray
                    ?.mapNotNull { element ->
                        val item = element.jsonObject
                        val name = item["name"]?.jsonPrimitive?.contentOrNull ?: return@mapNotNull null
                        val description = item["description"]?.jsonPrimitive?.contentOrNull ?: ""
                        val subcommands = item["subcommands"]?.jsonArray?.mapNotNull { subElement ->
                            val sub = subElement.jsonObject
                            val subName = sub["name"]?.jsonPrimitive?.contentOrNull
                                ?: return@mapNotNull null
                            SlashSubcommand(
                                name = subName,
                                description = sub["description"]?.jsonPrimitive?.contentOrNull ?: "",
                                template = sub["template"]?.jsonPrimitive?.contentOrNull,
                            )
                        } ?: emptyList()
                        ToolInfo(name, description, subcommands)
                    }
            }
        } finally {
            connection.disconnect()
        }
    } catch (_: Exception) {
        null
    }
}

private fun clearThreadHistory(
    baseUrl: String,
    token: String,
): ClearHistoryResult {
    val connection = URI.create("$baseUrl/api/v1/threads/clear")
        .toURL().openConnection() as HttpURLConnection
    connection.requestMethod = "POST"
    connection.doOutput = true
    connection.setRequestProperty("Authorization", "Bearer $token")
    connection.setRequestProperty("Content-Type", "application/json")
    connection.connectTimeout = 5000
    connection.readTimeout = 15000
    return try {
        connection.outputStream.use { it.write(ByteArray(0)) }
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        val root = Json.parseToJsonElement(text.ifBlank { "{}" }).jsonObject
        if (code !in 200..299) {
            throw IllegalStateException(
                root["error"]?.jsonPrimitive?.contentOrNull
                    ?: "Could not clear history (HTTP $code)"
            )
        }
        ClearHistoryResult(
            cleared = root["cleared"]?.jsonPrimitive?.intOrNull ?: 0,
            message = root["message"]?.jsonPrimitive?.contentOrNull
                ?: "Thread history cleared. Memory and persona were not changed.",
        )
    } finally {
        connection.disconnect()
    }
}

private fun fetchThreads(baseUrl: String, token: String): List<ThreadSummary>? {
    return try {
        val connection = URI.create("$baseUrl/api/v1/threads").toURL().openConnection() as HttpURLConnection
        connection.requestMethod = "GET"
        connection.setRequestProperty("Authorization", "Bearer $token")
        connection.connectTimeout = 3000
        connection.readTimeout = 10000
        try {
            if (connection.responseCode != 200) {
                null
            } else {
                val root = Json
                    .parseToJsonElement(connection.inputStream.bufferedReader().readText())
                    .jsonObject
                root["threads"]?.jsonArray?.mapNotNull { element ->
                    val item = element.jsonObject
                    val id = item["id"]?.jsonPrimitive?.contentOrNull
                        ?: return@mapNotNull null
                    ThreadSummary(
                        id = id,
                        title = item["title"]?.jsonPrimitive?.contentOrNull ?: "",
                        updatedAt = item["updated_at"]?.jsonPrimitive?.contentOrNull ?: "",
                        messageCount = item["message_count"]?.jsonPrimitive?.intOrNull ?: 0,
                    )
                }
            }
        } finally {
            connection.disconnect()
        }
    } catch (_: Exception) {
        null
    }
}

private fun fetchThreadMessages(
    baseUrl: String,
    token: String,
    threadId: String,
): List<StoredMessage>? {
    return try {
        val connection = URI.create("$baseUrl/api/v1/threads/$threadId")
            .toURL().openConnection() as HttpURLConnection
        connection.requestMethod = "GET"
        connection.setRequestProperty("Authorization", "Bearer $token")
        connection.connectTimeout = 3000
        connection.readTimeout = 15000
        try {
            if (connection.responseCode != 200) {
                null
            } else {
                val root = Json
                    .parseToJsonElement(connection.inputStream.bufferedReader().readText())
                    .jsonObject
                val thread = root["thread"]?.jsonObject ?: return null
                thread["messages"]?.jsonArray?.mapNotNull { element ->
                    val item = element.jsonObject
                    val role = item["role"]?.jsonPrimitive?.contentOrNull
                        ?: return@mapNotNull null
                    val content = item["content"]?.jsonPrimitive?.contentOrNull ?: ""
                    StoredMessage(
                        id = item["id"]?.jsonPrimitive?.contentOrNull
                            ?: GridAgentClient.newId("msg"),
                        role = role,
                        content = content,
                        name = item["name"]?.jsonPrimitive?.contentOrNull ?: "",
                        args = item["args"]?.jsonPrimitive?.contentOrNull ?: "",
                        ui = item["ui"]?.toString()?.takeUnless { it == "null" } ?: "",
                        surfaceId = item["surfaceId"]?.jsonPrimitive?.contentOrNull ?: "",
                    )
                }
            }
        } finally {
            connection.disconnect()
        }
    } catch (_: Exception) {
        null
    }
}

private fun fetchProviderInfo(baseUrl: String, token: String): ProviderInfo? {
    return try {
        val connection = URI.create("$baseUrl/api/v1/provider").toURL().openConnection() as HttpURLConnection
        connection.requestMethod = "GET"
        connection.setRequestProperty("Authorization", "Bearer $token")
        connection.connectTimeout = 3000
        connection.readTimeout = 10000
        try {
            if (connection.responseCode != 200) {
                null
            } else {
                val root = Json
                    .parseToJsonElement(connection.inputStream.bufferedReader().readText())
                    .jsonObject
                val providers = root["providers"]?.jsonArray?.mapNotNull { element ->
                    val item = element.jsonObject
                    val id = item["id"]?.jsonPrimitive?.contentOrNull
                        ?: return@mapNotNull null
                    ProviderOption(
                        id = id,
                        name = item["name"]?.jsonPrimitive?.contentOrNull ?: id,
                        description = item["description"]?.jsonPrimitive?.contentOrNull ?: "",
                        defaultUrl = item["default_url"]?.jsonPrimitive?.contentOrNull
                            ?: providerDefaultUrl(id),
                        needsKey = item["needs_key"]?.jsonPrimitive?.booleanOrNull ?: false,
                        available = item["available"]?.jsonPrimitive?.booleanOrNull ?: true,
                        keySet = item["key_set"]?.jsonPrimitive?.booleanOrNull ?: false,
                    )
                } ?: DEFAULT_PROVIDERS
                ProviderInfo(
                    provider = root["provider"]?.jsonPrimitive?.contentOrNull ?: "",
                    model = root["model"]?.jsonPrimitive?.contentOrNull ?: "",
                    baseUrl = root["base_url"]?.jsonPrimitive?.contentOrNull ?: "",
                    providers = providers,
                )
            }
        } finally {
            connection.disconnect()
        }
    } catch (_: Exception) {
        null
    }
}

private data class PairingInfo(
    val url: String,
    val code: String,
    val expiresIn: Int,
)

private fun fetchPairingInfo(
    baseUrl: String,
    token: String,
    rotate: Boolean,
): PairingInfo {
    val path = if (rotate) "/api/v1/pair/rotate" else "/api/v1/pair/code"
    val connection = URI.create("$baseUrl$path").toURL().openConnection() as HttpURLConnection
    connection.requestMethod = if (rotate) "POST" else "GET"
    connection.setRequestProperty("Authorization", "Bearer $token")
    connection.connectTimeout = 5000
    connection.readTimeout = 10000
    try {
        if (rotate) {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json")
            connection.outputStream.use { it.write("{}".toByteArray(Charsets.UTF_8)) }
        }
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        val root = Json.parseToJsonElement(text.ifBlank { "{}" }).jsonObject
        if (code !in 200..299) {
            throw IllegalStateException(
                root["error"]?.jsonPrimitive?.contentOrNull
                    ?: "Could not load a pairing code (HTTP $code)"
            )
        }
        return PairingInfo(
            url = root["url"]?.jsonPrimitive?.contentOrNull ?: "",
            code = root["code"]?.jsonPrimitive?.contentOrNull ?: "",
            expiresIn = root["expires_in"]?.jsonPrimitive?.intOrNull ?: 0,
        )
    } finally {
        connection.disconnect()
    }
}

private fun postProviderModels(
    baseUrl: String,
    token: String,
    provider: String,
    providerUrl: String,
    apiKey: String,
): List<String> {
    val connection = URI.create("$baseUrl/api/v1/provider/models").toURL().openConnection() as HttpURLConnection
    connection.requestMethod = "POST"
    connection.doOutput = true
    connection.setRequestProperty("Authorization", "Bearer $token")
    connection.setRequestProperty("Content-Type", "application/json")
    connection.connectTimeout = 5000
    connection.readTimeout = 30000
    return try {
        val payload = buildJsonObject {
            put("provider", provider)
            put("base_url", providerUrl)
            if (apiKey.isNotBlank()) put("api_key", apiKey)
        }.toString()
        connection.outputStream.use { it.write(payload.toByteArray(Charsets.UTF_8)) }
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        val root = Json.parseToJsonElement(text.ifBlank { "{}" }).jsonObject
        if (code !in 200..299) {
            throw IllegalStateException(
                root["error"]?.jsonPrimitive?.contentOrNull ?: "Could not load models (HTTP $code)"
            )
        }
        root["models"]?.jsonArray
            ?.mapNotNull { it.jsonPrimitive.contentOrNull }
            ?: emptyList()
    } finally {
        connection.disconnect()
    }
}

private fun postProvider(
    baseUrl: String,
    token: String,
    provider: String,
    providerUrl: String,
    model: String,
    apiKey: String,
): String {
    val connection = URI.create("$baseUrl/api/v1/provider").toURL().openConnection() as HttpURLConnection
    connection.requestMethod = "POST"
    connection.doOutput = true
    connection.setRequestProperty("Authorization", "Bearer $token")
    connection.setRequestProperty("Content-Type", "application/json")
    connection.connectTimeout = 5000
    connection.readTimeout = 30000
    try {
        val payload = buildJsonObject {
            put("provider", provider)
            put("base_url", providerUrl)
            put("model", model)
            if (apiKey.isNotBlank()) put("api_key", apiKey)
        }.toString()
        connection.outputStream.use { it.write(payload.toByteArray(Charsets.UTF_8)) }
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        val root = Json.parseToJsonElement(text.ifBlank { "{}" }).jsonObject
        if (code in 200..299) {
            return root["message"]?.jsonPrimitive?.contentOrNull
                ?: "Switched to ${providerLabel(provider)} · $model"
        }
        throw IllegalStateException(
            root["error"]?.jsonPrimitive?.contentOrNull ?: "Provider switch failed (HTTP $code)"
        )
    } finally {
        connection.disconnect()
    }
}

private fun fetchModelsDirect(
    provider: String,
    providerUrl: String,
    apiKey: String,
): List<String> {
    val base = providerUrl.trim().trimEnd('/').let {
        if (provider == "ollama") it.removeSuffix("/v1") else it
    }
    if (base.isBlank()) return emptyList()
    if (provider == "ollama") {
        val root = Json
            .parseToJsonElement(httpGet("$base/api/tags", null))
            .jsonObject
        return root["models"]?.jsonArray?.mapNotNull {
            it.jsonObject["name"]?.jsonPrimitive?.contentOrNull
        } ?: emptyList()
    }
    if (providerNeedsKey(provider) && apiKey.isBlank()) {
        throw IllegalStateException("${providerLabel(provider)} API key is required.")
    }
    val root = Json
        .parseToJsonElement(httpGet("$base/models", apiKey.ifBlank { null }))
        .jsonObject
    return root["data"]?.jsonArray?.mapNotNull {
        it.jsonObject["id"]?.jsonPrimitive?.contentOrNull
    } ?: emptyList()
}

private fun httpGet(url: String, apiKey: String?): String {
    val connection = URI.create(url).toURL().openConnection() as HttpURLConnection
    connection.requestMethod = "GET"
    connection.connectTimeout = 5000
    connection.readTimeout = 15000
    if (!apiKey.isNullOrBlank()) {
        connection.setRequestProperty("Authorization", "Bearer $apiKey")
    }
    try {
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        if (code !in 200..299) {
            throw IllegalStateException("HTTP $code from $url")
        }
        return text
    } finally {
        connection.disconnect()
    }
}

private fun findProjectRoot(): File? {
    var directory: File? = File(System.getProperty("user.dir")).absoluteFile
    repeat(5) {
        val current = directory ?: return null
        if (File(current, "grid_agent.py").isFile) return current
        directory = current.parentFile
    }
    return null
}

private fun pythonExecutable(root: File): String {
    val windows = File(root, ".venv/Scripts/python.exe")
    if (windows.isFile) return windows.absolutePath
    val unix = File(root, ".venv/bin/python")
    if (unix.isFile) return unix.absolutePath
    return if (System.getProperty("os.name").lowercase().contains("win")) "python" else "python3"
}

private fun readToken(root: File): String {
    return try {
        val file = File(root, "run/api_token")
        if (file.isFile) file.readText().trim() else ""
    } catch (_: Exception) {
        ""
    }
}

private fun startHost(root: File) {
    val log = File(root, "run/desktop_host.log")
    log.parentFile?.mkdirs()
    val builder = ProcessBuilder(
        pythonExecutable(root),
        "grid_agent.py",
        "--api",
        "--no-input",
        "--no-banner",
    )
        .directory(root)
        .redirectErrorStream(true)
        .redirectOutput(ProcessBuilder.Redirect.appendTo(log))
    builder.environment()["PYTHONUNBUFFERED"] = "1"
    builder.start()
}

private fun readConfig(root: File): Map<String, kotlinx.serialization.json.JsonElement> {
    return try {
        val file = File(root, "config.json")
        if (!file.isFile) emptyMap()
        else Json.parseToJsonElement(file.readText()).jsonObject
    } catch (_: Exception) {
        emptyMap()
    }
}

private fun hasProviderKey(root: File, provider: String): Boolean {
    val cfg = readConfig(root)
    return when (provider) {
        "openrouter" -> !cfg["openrouter_api_key"]?.jsonPrimitive?.contentOrNull.isNullOrBlank()
        "openai" -> !cfg["openai_api_key"]?.jsonPrimitive?.contentOrNull.isNullOrBlank()
        else -> true
    }
}

private fun writeConfig(
    root: File,
    provider: String,
    providerUrl: String,
    model: String,
    apiKey: String,
) {
    val existing = readConfig(root).toMutableMap()
    existing["backend_type"] = JsonPrimitive(provider)
    existing["base_url"] = JsonPrimitive(providerUrl.trimEnd('/'))
    existing["model"] = JsonPrimitive(model)
    if (apiKey.isNotBlank()) {
        when (provider) {
            "openrouter" -> existing["openrouter_api_key"] = JsonPrimitive(apiKey)
            "openai" -> existing["openai_api_key"] = JsonPrimitive(apiKey)
        }
    }
    val file = File(root, "config.json")
    file.writeText(
        Json { prettyPrint = true }
            .encodeToString(JsonObject.serializer(), JsonObject(existing))
    )
}

private fun fetchModelInfo(baseUrl: String, token: String): ModelInfo? {
    return try {
        val connection = URI.create("$baseUrl/api/v1/model").toURL().openConnection() as HttpURLConnection
        connection.requestMethod = "GET"
        connection.setRequestProperty("Authorization", "Bearer $token")
        connection.connectTimeout = 3000
        connection.readTimeout = 5000
        try {
            if (connection.responseCode != 200) {
                null
            } else {
                val root = Json
                    .parseToJsonElement(connection.inputStream.bufferedReader().readText())
                    .jsonObject
                val current = root["model"]?.jsonPrimitive?.contentOrNull ?: ""
                val available = root["models"]?.jsonArray
                    ?.mapNotNull { it.jsonPrimitive.contentOrNull }
                    ?: emptyList()
                ModelInfo(current, available)
            }
        } finally {
            connection.disconnect()
        }
    } catch (_: Exception) {
        null
    }
}

private fun postUiAction(
    baseUrl: String,
    token: String,
    surfaceId: String,
    action: String,
    payload: String,
): String {
    val connection = URI.create("$baseUrl/api/v1/ui/action")
        .toURL().openConnection() as HttpURLConnection
    connection.requestMethod = "POST"
    connection.doOutput = true
    connection.setRequestProperty("Authorization", "Bearer $token")
    connection.setRequestProperty("Content-Type", "application/json")
    connection.connectTimeout = 5000
    connection.readTimeout = 15000
    try {
        val payloadElement = if (payload.isBlank()) {
            JsonObject(emptyMap())
        } else {
            runCatching { Json.parseToJsonElement(payload) }
                .getOrElse { JsonObject(emptyMap()) }
        }
        val body = buildJsonObject {
            put("surfaceId", surfaceId)
            put("action", action)
            put("payload", payloadElement)
        }.toString()
        connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        val root = Json.parseToJsonElement(text.ifBlank { "{}" }).jsonObject
        if (code in 200..299) {
            return root["message"]?.jsonPrimitive?.contentOrNull ?: "Action received."
        }
        throw IllegalStateException(
            root["error"]?.jsonPrimitive?.contentOrNull ?: "Action failed (HTTP $code)"
        )
    } finally {
        connection.disconnect()
    }
}

private fun postCommand(baseUrl: String, token: String, command: String): String {
    val connection = URI.create("$baseUrl/api/v1/command").toURL().openConnection() as HttpURLConnection
    connection.requestMethod = "POST"
    connection.doOutput = true
    connection.setRequestProperty("Authorization", "Bearer $token")
    connection.setRequestProperty("Content-Type", "application/json")
    connection.connectTimeout = 5000
    connection.readTimeout = 600000
    try {
        val payload = buildJsonObject { put("command", command) }.toString()
        connection.outputStream.use { it.write(payload.toByteArray(Charsets.UTF_8)) }
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        val root = Json.parseToJsonElement(text.ifBlank { "{}" }).jsonObject
        if (code in 200..299) {
            return root["output"]?.jsonPrimitive?.contentOrNull ?: "(no output)"
        }
        throw IllegalStateException(
            root["error"]?.jsonPrimitive?.contentOrNull ?: "Command failed (HTTP $code)"
        )
    } finally {
        connection.disconnect()
    }
}

private fun postShutdown(baseUrl: String, token: String): String {
    val connection = URI.create("$baseUrl/api/v1/shutdown").toURL().openConnection() as HttpURLConnection
    connection.requestMethod = "POST"
    connection.doOutput = true
    connection.setRequestProperty("Authorization", "Bearer $token")
    connection.setRequestProperty("Content-Type", "application/json")
    connection.connectTimeout = 5000
    connection.readTimeout = 15000
    try {
        connection.outputStream.use { it.write(ByteArray(0)) }
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        val root = Json.parseToJsonElement(text.ifBlank { "{}" }).jsonObject
        if (code in 200..299) {
            return root["message"]?.jsonPrimitive?.contentOrNull ?: "GRID host stopped."
        }
        throw IllegalStateException(
            root["error"]?.jsonPrimitive?.contentOrNull ?: "Shutdown failed (HTTP $code)"
        )
    } finally {
        connection.disconnect()
    }
}

private fun postModel(baseUrl: String, token: String, model: String): Boolean {
    return try {
        val connection = URI.create("$baseUrl/api/v1/model").toURL().openConnection() as HttpURLConnection
        connection.requestMethod = "POST"
        connection.doOutput = true
        connection.setRequestProperty("Authorization", "Bearer $token")
        connection.setRequestProperty("Content-Type", "application/json")
        connection.connectTimeout = 3000
        connection.readTimeout = 5000
        try {
            val escaped = model.replace("\\", "\\\\").replace("\"", "\\\"")
            connection.outputStream.use {
                it.write("{\"model\":\"$escaped\"}".toByteArray())
            }
            connection.responseCode in 200..299
        } finally {
            connection.disconnect()
        }
    } catch (_: Exception) {
        false
    }
}

private fun formatDuration(ms: Long): String =
    if (ms <= 0) "0.0s" else "%.1fs".format(ms / 1000.0)

private fun formatTokens(tokens: Int): String =
    if (tokens >= 1000) "%.1fk".format(tokens / 1000.0) else tokens.toString()

private fun apiHealthy(baseUrl: String, token: String): Boolean {
    return try {
        val client = HttpClient.newBuilder()
            .connectTimeout(java.time.Duration.ofSeconds(2))
            .build()
        val request = HttpRequest.newBuilder()
            .uri(URI.create("$baseUrl/api/v1/health"))
            .header("Authorization", "Bearer $token")
            .timeout(java.time.Duration.ofSeconds(3))
            .GET()
            .build()
        client.send(request, HttpResponse.BodyHandlers.ofString()).statusCode() == 200
    } catch (_: Exception) {
        false
    }
}

private fun connectionAwareMessage(error: Throwable, baseUrl: String): String {
    var current: Throwable? = error
    while (current != null) {
        val text = current.message.orEmpty()
        if (
            current is java.net.ConnectException ||
            text.contains("Connection refused", ignoreCase = true) ||
            text.contains("Failed to connect", ignoreCase = true)
        ) {
            return "GRID API is offline at $baseUrl.\n" +
                "Start it with: python grid_agent.py --api --no-input"
        }
        current = current.cause
    }
    return error.message ?: error.toString()
}

private fun postApproval(
    baseUrl: String,
    token: String,
    approvalId: String,
    decision: String,
): Boolean {
    return try {
        val client = HttpClient.newHttpClient()
        val request = HttpRequest.newBuilder()
            .uri(URI.create("$baseUrl/api/v1/approvals/$approvalId"))
            .header("Authorization", "Bearer $token")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString("{\"decision\":\"$decision\"}"))
            .build()
        val response = client.send(request, HttpResponse.BodyHandlers.ofString())
        response.statusCode() in 200..299
    } catch (_: Exception) {
        false
    }
}

private fun openPath(path: String) {
    try {
        val file = File(path)
        if (Desktop.isDesktopSupported()) {
            Desktop.getDesktop().open(file)
        }
    } catch (_: Exception) {
        try {
            if (System.getProperty("os.name").lowercase().contains("win")) {
                ProcessBuilder("notepad.exe", path).start()
            }
        } catch (_: Exception) {
            // The report stays on disk even when no handler is registered.
        }
    }
}

private fun argument(args: Array<String>, name: String): String? {
    val index = args.indexOf(name)
    return if (index >= 0 && args.size > index + 1) args[index + 1] else null
}

private fun loadToken(args: Array<String>): String {
    System.getenv("GRID_API_TOKEN")?.trim()?.takeIf { it.isNotEmpty() }?.let { return it }
    val candidates = buildList {
        argument(args, "--token-file")?.let { add(Path.of(it)) }
        add(Path.of("run", "api_token"))
        add(Path.of("..", "run", "api_token"))
        add(Path.of("..", "..", "run", "api_token"))
    }
    for (path in candidates) {
        try {
            if (Files.exists(path)) return Files.readString(path).trim()
        } catch (_: Exception) {
            // Try the next location.
        }
    }
    return ""
}
