// Compose UI functions use PascalCase by convention.
@file:Suppress("FunctionName")

package ai.grid.desktop

import ai.grid.shared.GridAgentClient
import ai.grid.shared.GridEvent
import androidx.compose.foundation.VerticalScrollbar
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.isShiftPressed
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import java.awt.Desktop
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
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
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

private data class SlashCommand(
    val name: String,
    val description: String,
    val template: String? = null,
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
    SlashCommand("/tokens", "Show session token and timing stats"),
    SlashCommand(
        "/rea",
        "Authorized passive teardown: /rea authorized <url>",
        template = "/rea authorized ",
    ),
    SlashCommand("/tools", "List every GRID tool"),
    SlashCommand("/tool", "Run a tool: /tool <name> <input>", template = "/tool "),
    SlashCommand("/memory", "Recall, add facts, show profile"),
    SlashCommand("/life", "Status, goals, commitments, tick"),
    SlashCommand("/plan", "Toggle planner mode"),
    SlashCommand("/ref", "Read an offloaded tool output", template = "/ref "),
    SlashCommand("/jobs", "List/show/toggle dynamic skills"),
    SlashCommand("/persona", "View or set GRID persona"),
    SlashCommand("/social", "Moltbook social platform"),
    SlashCommand("/pb", "PocketBase status/start/stop/sync"),
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
    ) : Item
    data class Artifact(val path: String) : Item
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
                App(baseUrl.trimEnd('/'), token, onExit = ::exitApplication)
            }
        }
    }
}

@Composable
private fun App(baseUrl: String, token: String, onExit: () -> Unit) {
    val scope = rememberCoroutineScope()
    val items = remember { mutableStateListOf<Item>() }
    val listState = rememberLazyListState()
    val inputFocus = remember { FocusRequester() }
    var input by remember { mutableStateOf(TextFieldValue("")) }
    var busy by remember { mutableStateOf(false) }
    var commandBusy by remember { mutableStateOf(false) }
    var confirmShutdown by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("Ready") }
    var threadId by remember { mutableStateOf(GridAgentClient.newThreadId()) }
    var model by remember { mutableStateOf("") }
    var models by remember { mutableStateOf(emptyList<String>()) }
    var tools by remember { mutableStateOf(emptyList<ToolInfo>()) }
    var totalTokens by remember { mutableStateOf(0) }
    var lastLatency by remember { mutableStateOf(0L) }
    var lastTokens by remember { mutableStateOf(0) }
    var runCount by remember { mutableStateOf(0) }
    val client = remember { GridAgentClient(baseUrl, token) }

    LaunchedEffect(baseUrl, token) {
        if (token.isBlank()) {
            status = "Token missing"
            return@LaunchedEffect
        }
        val online = withContext(Dispatchers.IO) { apiHealthy(baseUrl, token) }
        if (!online) {
            status = "API offline"
            if (items.none { it is Item.Error && it.message.startsWith("GRID API is offline") }) {
                items.add(
                    Item.Error(
                        "GRID API is offline at $baseUrl.\n" +
                            "Start it with: python grid_agent.py --api --no-input"
                    )
                )
            }
        } else {
            val info = withContext(Dispatchers.IO) { fetchModelInfo(baseUrl, token) }
            if (info != null) {
                model = info.model
                models = info.models
            }
            val toolList = withContext(Dispatchers.IO) { fetchTools(baseUrl, token) }
            if (toolList != null) tools = toolList
        }
    }

    LaunchedEffect(Unit) {
        inputFocus.requestFocus()
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
            }
            is GridEvent.StepStarted -> status = "Step: ${event.name}"
            is GridEvent.StepFinished -> status = "Working"
            is GridEvent.MessageStarted -> {
                if (items.none { it is Item.Assistant && it.id == event.messageId }) {
                    items.add(Item.Assistant(event.messageId, ""))
                }
            }
            is GridEvent.TextDelta -> {
                val index = items.indexOfLast { it is Item.Assistant && it.id == event.messageId }
                if (index >= 0) {
                    val old = items[index] as Item.Assistant
                    items[index] = old.copy(text = old.text + event.delta)
                } else {
                    items.add(Item.Assistant(event.messageId, event.delta))
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
            is GridEvent.Artifact -> addDuringRun(Item.Artifact(event.path))
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
                val index = items.indexOfLast { it is Item.Assistant }
                if (index >= 0) {
                    val old = items[index] as Item.Assistant
                    items[index] = old.copy(
                        durationMs = event.durationMs,
                        tokens = event.totalTokens,
                        estimated = event.estimated,
                    )
                }
            }
            is GridEvent.Custom -> Unit
            is GridEvent.RunFinished -> {
                finishActivity()
                busy = false
                status = "Ready"
            }
            is GridEvent.Error -> {
                finishActivity()
                items.add(Item.Error(event.message))
                busy = false
                status = "Error"
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
        scope.launch {
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
                if (args.isBlank()) {
                    items.add(Item.Note("Usage: /rea authorized <url>"))
                } else {
                    val target = if (args.startsWith("authorized ")) {
                        args
                    } else {
                        "authorized $args"
                    }
                    send("rea $target")
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

    fun changeModel(requested: String) {
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

    Row(Modifier.fillMaxSize().background(Background)) {
        Sidebar(
            status = status,
            threadId = threadId,
            baseUrl = baseUrl,
            tokenReady = token.isNotBlank(),
            model = model,
            models = models,
            totalTokens = totalTokens,
            lastLatency = lastLatency,
            lastTokens = lastTokens,
            runCount = runCount,
            onModelChange = { changeModel(it) },
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
                            is Item.Tool -> ToolCard(item)
                            is Item.Artifact -> ArtifactCard(item.path)
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
                enabled = token.isNotBlank(),
                focusRequester = inputFocus,
                tools = tools,
                onInput = { input = it },
                onCommand = { handleSlashCommand(it) },
                onSend = { send() },
            )
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
}

@Composable
private fun Sidebar(
    status: String,
    threadId: String,
    baseUrl: String,
    tokenReady: Boolean,
    model: String,
    models: List<String>,
    totalTokens: Int,
    lastLatency: Long,
    lastTokens: Int,
    runCount: Int,
    onModelChange: (String) -> Unit,
    onNewThread: () -> Unit,
    onQuickPrompt: (String) -> Unit,
) {
    var modelMenu by remember { mutableStateOf(false) }
    Column(
        Modifier
            .width(250.dp)
            .fillMaxHeight()
            .background(Panel)
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
        Spacer(Modifier.height(18.dp))
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
            Text("Command center", color = Color.White, fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
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
            Text(text, color = Color.White, modifier = Modifier.padding(13.dp), fontSize = 14.sp)
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
            SelectionContainer {
                Text(
                    item.text.ifBlank { "…" },
                    color = Color.White,
                    fontSize = 14.sp,
                    lineHeight = 21.sp,
                )
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
private fun ToolCard(item: Item.Tool) {
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
                }
            }
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
        SelectionContainer {
            Text(
                message,
                color = GridGreenDim,
                modifier = Modifier.padding(13.dp),
                fontSize = 12.sp,
                fontFamily = FontFamily.Monospace,
            )
        }
    }
}

@Composable
private fun Composer(
    input: TextFieldValue,
    busy: Boolean,
    enabled: Boolean,
    focusRequester: FocusRequester,
    tools: List<ToolInfo>,
    onInput: (TextFieldValue) -> Unit,
    onCommand: (String) -> Boolean,
    onSend: () -> Unit,
) {
    val text = input.text
    val allCommands = (
        SLASH_COMMANDS +
            tools.map {
                SlashCommand(
                    "/${it.name}",
                    it.description,
                    template = "/${it.name} ",
                )
            }
        ).distinctBy { it.name }
    val query = text.removePrefix("/").substringBefore(" ").trim()
    var dismissed by remember { mutableStateOf(false) }
    var selected by remember { mutableStateOf(0) }
    val suggestionState = rememberLazyListState()
    val filtered = allCommands.filter {
        it.name.removePrefix("/").startsWith(query, ignoreCase = true)
    }
    val showSuggestions = text.startsWith("/") &&
        !text.contains(" ") &&
        !dismissed &&
        filtered.isNotEmpty()

    LaunchedEffect(query) {
        selected = 0
        dismissed = false
        if (showSuggestions) suggestionState.scrollToItem(0)
    }

    LaunchedEffect(selected, showSuggestions) {
        if (showSuggestions && filtered.isNotEmpty()) {
            suggestionState.animateScrollToItem(selected.coerceIn(0, filtered.lastIndex))
        }
    }

    fun apply(command: SlashCommand) {
        val next = command.template ?: "${command.name} "
        onInput(TextFieldValue(next, TextRange(next.length)))
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
                            "COMMANDS · ${filtered.size}/${allCommands.size}",
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
                        itemsIndexed(filtered) { index, command ->
                            Row(
                                Modifier
                                    .fillMaxWidth()
                                    .background(
                                        if (index == selected) Color(0xFF173B27) else Color.Transparent,
                                        RoundedCornerShape(6.dp),
                                    )
                                    .clickable { apply(command) }
                                    .padding(horizontal = 8.dp, vertical = 7.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Text(
                                    command.name,
                                    color = GridGreen,
                                    fontSize = 12.sp,
                                    fontFamily = FontFamily.Monospace,
                                    modifier = Modifier.width(140.dp),
                                )
                                Text("= ${command.description}", color = Muted, fontSize = 11.sp)
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
                                selected = (selected + 1) % filtered.size
                                true
                            }
                            Key.DirectionUp, Key.NumPadDirectionUp -> {
                                selected = (selected - 1 + filtered.size) % filtered.size
                                true
                            }
                            Key.Tab -> {
                                apply(filtered[selected])
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
                                    val command = filtered[selected]
                                    if (
                                        text.trim().equals(command.name, ignoreCase = true) &&
                                        command.template == null
                                    ) {
                                        onCommand(command.name)
                                        onInput(TextFieldValue(""))
                                    } else {
                                        apply(command)
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

private data class ModelInfo(val model: String, val models: List<String>)

private data class ToolInfo(val name: String, val description: String)

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
                        ToolInfo(name, description)
                    }
            }
        } finally {
            connection.disconnect()
        }
    } catch (_: Exception) {
        null
    }
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
