package ai.grid.android

import ai.grid.shared.GridAgentClient
import ai.grid.shared.GridEvent
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.AlertDialog
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
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.time.Duration.Companion.milliseconds

private val Background = Color(0xFF0B0F0C)
private val Panel = Color(0xFF111813)
private val PanelRaised = Color(0xFF162119)
private val GridGreen = Color(0xFF00FF88)
private val GridGreenDim = Color(0xFF7CF7B0)
private val Muted = Color(0xFF8A9B8F)
private val Danger = Color(0xFFFF6B6B)
private val Warning = Color(0xFFFFD166)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val store = TokenStore(this)
        setContent {
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
                GridRoot(store)
            }
        }
    }
}

@Composable
private fun GridRoot(store: TokenStore) {
    var baseUrl by remember { mutableStateOf(normalizeBaseUrl(store.loadUrl())) }
    var token by remember { mutableStateOf(store.loadToken()) }
    var editing by remember { mutableStateOf(token.isBlank()) }

    if (editing) {
        SetupScreen(
            canCancel = token.isNotBlank(),
            onCancel = { editing = false },
            onConnect = { url, newToken ->
                baseUrl = normalizeBaseUrl(url)
                token = normalizeToken(newToken)
                store.saveUrl(baseUrl)
                store.saveToken(token)
                editing = false
            },
        )
    } else {
        ChatScreen(
            baseUrl = baseUrl,
            token = token,
            onSettings = { editing = true },
        )
    }
}

@Composable
private fun SetupScreen(
    canCancel: Boolean,
    onCancel: () -> Unit,
    onConnect: (String, String) -> Unit,
) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var discovered by remember { mutableStateOf<List<DiscoveredHost>>(emptyList()) }
    var selectedHost by remember { mutableStateOf<DiscoveredHost?>(null) }
    var scanning by remember { mutableStateOf(false) }
    var scanError by remember { mutableStateOf<String?>(null) }
    var pairCode by remember { mutableStateOf("") }
    var pairing by remember { mutableStateOf(false) }
    var pairError by remember { mutableStateOf<String?>(null) }

    fun findHosts() {
        if (scanning) return
        scanning = true
        scanError = null
        scope.launch {
            val found = withContext(Dispatchers.IO) {
                runCatching { discoverHosts(context) }.getOrDefault(emptyList())
            }
            discovered = found
            scanning = false
            selectedHost = when {
                found.size == 1 -> found.first()
                selectedHost != null && found.any { it.url == selectedHost?.url } -> selectedHost
                else -> null
            }
            if (found.isEmpty()) {
                scanError =
                    "No GRID host found. Start the desktop app and keep both devices on the same Wi-Fi."
            }
        }
    }

    fun pair() {
        val host = selectedHost ?: return
        if (pairing) return
        pairing = true
        pairError = null
        scope.launch {
            try {
                val newToken = withContext(Dispatchers.IO) {
                    pairWithCode(host.url, pairCode, Build.MODEL)
                }
                onConnect(host.url, newToken)
            } catch (error: Exception) {
                pairError = error.message ?: "Pairing failed."
            } finally {
                pairing = false
            }
        }
    }

    LaunchedEffect(Unit) { findHosts() }

    Column(
        Modifier
            .fillMaxSize()
            .background(Background)
            .statusBarsPadding()
            .navigationBarsPadding()
            .imePadding()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("GRID", color = GridGreen, fontSize = 34.sp, fontWeight = FontWeight.Bold)
        Text("ANDROID COMPANION", color = Muted, fontSize = 11.sp, letterSpacing = 2.sp)
        Spacer(Modifier.height(12.dp))

        Text("PAIR WITH YOUR DESKTOP", color = GridGreen, fontSize = 11.sp, letterSpacing = 1.2.sp)
        Text(
            "1. Open GRID on the PC and click Pair phone.",
            color = Muted,
            fontSize = 12.sp,
        )
        Text(
            "2. Keep this phone on the same Wi-Fi.",
            color = Muted,
            fontSize = 12.sp,
        )

        if (scanning) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(
                    modifier = Modifier.size(14.dp),
                    color = GridGreen,
                    strokeWidth = 2.dp,
                )
                Spacer(Modifier.width(8.dp))
                Text("Looking for GRID on your Wi-Fi…", color = GridGreenDim, fontSize = 12.sp)
            }
        } else if (discovered.isEmpty()) {
            Text(
                scanError ?: "No GRID host found.",
                color = Warning,
                fontSize = 11.sp,
            )
            OutlinedButton(
                onClick = { findHosts() },
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Search again") }
        } else {
            Text("3. Choose your host", color = Muted, fontSize = 11.sp)
            discovered.forEach { host ->
                val selected = selectedHost?.url == host.url
                Surface(
                    color = if (selected) Color(0xFF173B27) else PanelRaised,
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth().clickable { selectedHost = host },
                ) {
                    Row(
                        Modifier.padding(horizontal = 10.dp, vertical = 9.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(host.name, color = Color.White, fontSize = 13.sp, modifier = Modifier.weight(1f))
                        Text(
                            if (selected) "Selected" else "Select",
                            color = if (selected) GridGreen else Muted,
                            fontSize = 10.sp,
                        )
                    }
                }
            }
        }

        if (discovered.isNotEmpty()) {
            HorizontalDivider(color = PanelRaised, modifier = Modifier.padding(vertical = 4.dp))
            Text("4. Enter the 6-digit code", color = Muted, fontSize = 11.sp)
            Row(verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(
                    value = pairCode,
                    onValueChange = { pairCode = normalizePairingCode(it) },
                    modifier = Modifier.weight(1f),
                    singleLine = true,
                    placeholder = { Text("000000", color = Muted) },
                    keyboardOptions = KeyboardOptions(
                        keyboardType = KeyboardType.Number,
                        imeAction = ImeAction.Done,
                    ),
                    keyboardActions = KeyboardActions(onDone = { pair() }),
                )
                Spacer(Modifier.width(8.dp))
                Button(
                    onClick = { pair() },
                    enabled = !pairing && selectedHost != null && pairCode.length == 6,
                    colors = ButtonDefaults.buttonColors(containerColor = GridGreen, contentColor = Color.Black),
                    modifier = Modifier.height(56.dp),
                ) {
                    if (pairing) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(18.dp),
                            color = Color.Black,
                            strokeWidth = 2.dp,
                        )
                    } else {
                        Text("Pair")
                    }
                }
            }
            pairError?.let {
                Text(it, color = Danger, fontSize = 11.sp)
            }
        }

        Text(
            "The code is in the desktop Pair phone dialog. It expires after 15 minutes.",
            color = Muted,
            fontSize = 11.sp,
        )
        if (canCancel) {
            TextButton(
                onClick = onCancel,
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Cancel", color = Muted) }
        }
        Text(
            "Host not listed? Make sure the desktop is running and both devices are on the same network.",
            color = GridGreenDim,
            fontSize = 11.sp,
        )
    }
}

@Composable
private fun ChatScreen(baseUrl: String, token: String, onSettings: () -> Unit) {
    val scope = rememberCoroutineScope()
    val items = remember { mutableStateListOf<Item>() }
    val listState = rememberLazyListState()
    var input by remember { mutableStateOf(TextFieldValue("")) }
    var busy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("Connecting") }
    var threadId by remember { mutableStateOf(GridAgentClient.newThreadId()) }
    var toolCommands by remember { mutableStateOf<List<SlashCommand>>(emptyList()) }
    var threads by remember { mutableStateOf<List<ThreadSummary>>(emptyList()) }
    var model by remember { mutableStateOf("") }
    var provider by remember { mutableStateOf("") }
    var providerOptions by remember { mutableStateOf<List<ProviderOption>>(emptyList()) }
    var models by remember { mutableStateOf<List<String>>(emptyList()) }
    var showHistory by remember { mutableStateOf(false) }
    var showModels by remember { mutableStateOf(false) }
    var totalTokens by remember { mutableStateOf(0) }
    var lastTokens by remember { mutableStateOf(0) }
    var lastLatency by remember { mutableStateOf(0L) }
    var runCount by remember { mutableStateOf(0) }
    var currentAssistantId by remember { mutableStateOf<String?>(null) }
    var pendingStats by remember { mutableStateOf<GridEvent.Stats?>(null) }
    val client = remember(baseUrl, token) { GridAgentClient(baseUrl, token) }
    val focusRequester = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    val clipboard = LocalClipboardManager.current
    var chatCopied by remember { mutableStateOf(false) }
    LaunchedEffect(chatCopied) {
        if (chatCopied) {
            delay(1500)
            chatCopied = false
        }
    }

    LaunchedEffect(baseUrl, token) {
        status = "Connecting"
        val failure = withContext(Dispatchers.IO) { healthFailure(baseUrl, token) }
        if (failure == null) {
            status = "Ready"
            val loaded = withContext(Dispatchers.IO) {
                val info = runCatching { fetchProviderInfo(baseUrl, token) }.getOrNull()
                val currentModels = runCatching { fetchCurrentModels(baseUrl, token) }
                    .getOrDefault(emptyList())
                val list = runCatching { fetchThreads(baseUrl, token) }
                    .getOrDefault(emptyList())
                Triple(info, currentModels, list)
            }
            toolCommands = withContext(Dispatchers.IO) { fetchToolCommands(baseUrl, token) }
            loaded.first?.let { info ->
                provider = info.provider
                model = info.model
                providerOptions = info.providers
            }
            models = loaded.second
            threads = loaded.third
        } else {
            status = if (failure.startsWith("Authentication")) "Auth failed" else "API offline"
            items.add(Item.Error(failure))
        }
    }

    LaunchedEffect(items.size) {
        if (items.isNotEmpty()) listState.animateScrollToItem(items.lastIndex)
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
                status = "Running ${event.runId.take(8)}"
                currentAssistantId = null
                pendingStats = null
            }
            is GridEvent.StepStarted -> status = event.name
            is GridEvent.StepFinished -> status = "Working"
            is GridEvent.MessageStarted -> {
                currentAssistantId = event.messageId
                if (items.none { it is Item.Assistant && it.id == event.messageId }) {
                    items.add(assistantItem(event.messageId, "", pendingStats))
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
                    items.add(assistantItem(event.messageId, event.delta, pendingStats))
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
                lastTokens = event.totalTokens
                lastLatency = event.durationMs
                runCount += 1
                if (event.model.isNotBlank()) model = event.model
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
            is GridEvent.Ui -> Unit
            is GridEvent.Custom -> Unit
            is GridEvent.RunFinished -> {
                finishActivity()
                status = "Ready"
                currentAssistantId = null
                pendingStats = null
            }
            is GridEvent.Error -> {
                finishActivity()
                items.add(Item.Error(event.message))
                status = "Error"
            }
            is GridEvent.Other -> Unit
        }
    }

    fun runPrompt(prompt: String) {
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
                val message = connectionAwareMessage(error, baseUrl)
                items.add(Item.Error(message))
                status = if (message.startsWith("GRID API is offline")) "API offline" else "Error"
            } finally {
                busy = false
                finishActivity()
            }
            threads = runCatching {
                withContext(Dispatchers.IO) { fetchThreads(baseUrl, token) }
            }.getOrDefault(threads)
        }
    }

    fun refreshThreads() {
        scope.launch {
            threads = runCatching {
                withContext(Dispatchers.IO) { fetchThreads(baseUrl, token) }
            }.getOrDefault(threads)
        }
    }

    fun openThread(id: String) {
        if (busy) {
            items.add(Item.System("Wait for the current response to finish before opening a thread."))
            return
        }
        if (id == threadId) return
        scope.launch {
            status = "Loading thread..."
            try {
                val messages = withContext(Dispatchers.IO) {
                    fetchThreadMessages(baseUrl, token, id)
                }
                threadId = id
                items.clear()
                messages.forEach { message ->
                    when (message.role) {
                        "user" -> items.add(Item.User(message.content))
                        "assistant" -> if (message.content.isNotBlank()) {
                            items.add(
                                Item.Assistant(
                                    id = message.id.ifBlank { GridAgentClient.newId("msg") },
                                    text = message.content,
                                )
                            )
                        }
                        "tool" -> if (message.name.isNotBlank()) {
                            items.add(
                                Item.Tool(
                                    callId = message.id,
                                    name = message.name,
                                    args = message.args,
                                    result = message.content.ifBlank { "(no output)" },
                                )
                            )
                        }
                    }
                }
                status = "Ready"
            } catch (error: Exception) {
                items.add(Item.Error(error.message ?: "Could not load that thread."))
                status = "Error"
            }
        }
    }

    fun runServerCommand(command: String) {
        if (busy) return
        busy = true
        status = "Running command"
        scope.launch {
            try {
                val output = withContext(Dispatchers.IO) {
                    postServerCommand(baseUrl, token, command)
                }
                items.add(Item.System(output))
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                items.add(Item.Error(error.message ?: "Command failed"))
            } finally {
                busy = false
                status = "Ready"
            }
        }
    }

    fun helpText(): String = buildString {
        appendLine("Android commands:")
        APP_COMMANDS.forEach { appendLine("  ${it.name.padEnd(12)} = ${it.description}") }
        appendLine()
        appendLine("Plus ${toolCommands.size} host tools (type /tools).")
        append("Type / to autocomplete; tap a suggestion to insert it.")
    }

    fun handleSlash(raw: String): Boolean {
        val command = raw.trim()
        if (!command.startsWith("/")) return false
        val name = command.substringBefore(" ").lowercase()
        val args = command.substringAfter(" ", "").trim()
        val toolName = name.removePrefix("/")
        when {
            name == "/help" -> items.add(Item.System(helpText()))
            name == "/new" -> {
                threadId = GridAgentClient.newThreadId()
                items.clear()
                status = "Ready"
            }
            name == "/clear" -> {
                items.clear()
                status = "Ready"
            }
            name == "/settings" -> onSettings()
            name == "/tool" -> {
                if (args.isBlank()) {
                    items.add(Item.System("Usage: /tool <name> <input>"))
                } else {
                    runPrompt(args)
                }
            }
            name == "/rea" -> {
                when {
                    args.isBlank() -> items.add(
                        Item.System("Usage: /rea authorized <url> | authorize|revoke|list|status")
                    )
                    args == "list" ||
                        args == "status" ||
                        args == "help" ||
                        args.startsWith("authorize ") ||
                        args.startsWith("revoke ") -> runServerCommand("/rea $args")
                    args.startsWith("authorized ") -> runPrompt("rea $args")
                    else -> runPrompt("rea authorized $args")
                }
            }
            name in SERVER_COMMANDS -> runServerCommand(command)
            toolCommands.any { it.name.equals("/$toolName", ignoreCase = true) } ->
                runPrompt(if (args.isEmpty()) toolName else "$toolName $args")
            else -> items.add(
                Item.System("Unknown command: $name\nType /help for available commands.")
            )
        }
        return true
    }

    fun send() {
        val prompt = input.text.trim()
        if (prompt.isEmpty() || busy) return
        input = TextFieldValue("")
        if (prompt.startsWith("/") && handleSlash(prompt)) return
        runPrompt(prompt)
    }

    val allCommands = remember(toolCommands) {
        mergeSlashCommands(APP_COMMANDS, toolCommands)
    }
    val palette = remember(input.text, allCommands) {
        buildSlashPalette(input.text, allCommands)
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
                items.add(Item.Error("Approval request failed. Is the host still running?"))
            }
        }
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(Background)
            .statusBarsPadding()
            .navigationBarsPadding()
            .imePadding()
    ) {
        Column(Modifier.padding(horizontal = 14.dp, vertical = 8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("GRID", color = GridGreen, fontSize = 24.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.weight(1f))
                TextButton(
                    onClick = {
                        clipboard.setText(
                            AnnotatedString(fullChatText(threadId, model, provider, items))
                        )
                        chatCopied = true
                    },
                    contentPadding = PaddingValues(horizontal = 6.dp),
                    modifier = Modifier.semantics {
                        contentDescription = "Copy full chat"
                    },
                ) {
                    Text(
                        if (chatCopied) "✓" else "⧉",
                        color = if (chatCopied) GridGreen else Muted,
                        fontSize = 15.sp,
                    )
                }
                Spacer(Modifier.width(4.dp))
                Text(
                    status,
                    color = if (status == "API offline") Danger else GridGreenDim,
                    fontSize = 11.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    threadId,
                    color = Muted,
                    fontSize = 10.sp,
                    fontFamily = FontFamily.Monospace,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                TextButton(
                    onClick = {
                        threadId = GridAgentClient.newThreadId()
                        items.clear()
                        status = "Ready"
                    },
                    contentPadding = PaddingValues(horizontal = 6.dp),
                ) { Text("New", fontSize = 11.sp) }
                TextButton(
                    onClick = {
                        showHistory = true
                        refreshThreads()
                    },
                    contentPadding = PaddingValues(horizontal = 6.dp),
                ) { Text("History", fontSize = 11.sp) }
                TextButton(
                    onClick = onSettings,
                    contentPadding = PaddingValues(horizontal = 6.dp),
                ) { Text("⚙", fontSize = 14.sp) }
            }
            Row(
                Modifier.fillMaxWidth().padding(top = 2.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(
                    Modifier.weight(1f).clickable { showModels = true },
                ) {
                    Text(
                        model.ifBlank { "model: (unknown)" },
                        color = GridGreenDim,
                        fontSize = 11.sp,
                        fontFamily = FontFamily.Monospace,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        "${provider.ifBlank { "provider" }} · tap to change",
                        color = Muted,
                        fontSize = 9.sp,
                        maxLines = 1,
                    )
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        "${formatTokens(totalTokens)} tok · $runCount runs",
                        color = GridGreenDim,
                        fontSize = 10.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                    Text(
                        "last ${formatDuration(lastLatency)} · ${formatTokens(lastTokens)} tok",
                        color = Muted,
                        fontSize = 9.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                }
            }
            HorizontalDivider(color = PanelRaised, modifier = Modifier.padding(top = 6.dp))
        }

        LazyColumn(
            state = listState,
            modifier = Modifier.weight(1f).fillMaxWidth().padding(horizontal = 12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            itemsIndexed(items) { index, item ->
                when (item) {
                    is Item.User -> UserBubble(item.text)
                    is Item.Assistant -> AssistantBubble(
                        text = item.text,
                        durationMs = item.durationMs,
                        tokens = item.tokens,
                        estimated = item.estimated,
                    )
                    is Item.Tool -> ToolCard(item)
                    is Item.Activity -> ActivityCard(item)
                    is Item.Artifact -> ArtifactCard(item.path)
                    is Item.Approval -> ApprovalCard(
                        approval = item,
                        onApprove = { resolveApproval(index, item, "approve") },
                        onDeny = { resolveApproval(index, item, "deny") },
                    )
                    is Item.Error -> MessageCard(item.message, Danger)
                    is Item.System -> MessageCard(item.message, GridGreenDim)
                }
            }
        }

        Column(Modifier.fillMaxWidth().padding(10.dp)) {
            palette?.let { panel ->
                Surface(
                    color = PanelRaised,
                    shape = RoundedCornerShape(10.dp),
                    modifier = Modifier.fillMaxWidth().padding(bottom = 6.dp),
                ) {
                    Column(Modifier.padding(6.dp)) {
                        Row(
                            Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 3.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                panel.header,
                                color = GridGreen,
                                fontSize = 9.sp,
                                letterSpacing = 1.2.sp,
                            )
                            Spacer(Modifier.weight(1f))
                            Text("Tap to insert", color = Muted, fontSize = 9.sp)
                        }
                        LazyColumn(Modifier.fillMaxWidth().heightIn(max = 220.dp)) {
                            itemsIndexed(panel.suggestions) { _, suggestion ->
                                Row(
                                    Modifier
                                        .fillMaxWidth()
                                        .clickable {
                                            input = TextFieldValue(
                                                suggestion.applyText,
                                                TextRange(suggestion.applyText.length),
                                            )
                                            focusRequester.requestFocus()
                                            keyboard?.show()
                                        }
                                        .padding(horizontal = 8.dp, vertical = 7.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    Text(
                                        suggestion.label,
                                        color = GridGreen,
                                        fontSize = 12.sp,
                                        fontFamily = FontFamily.Monospace,
                                        modifier = Modifier.width(130.dp),
                                    )
                                    Text(
                                        "= ${suggestion.description}",
                                        color = Muted,
                                        fontSize = 11.sp,
                                        maxLines = 2,
                                    )
                                }
                            }
                        }
                    }
                }
            }
            Row(
                Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.Bottom,
            ) {
                OutlinedTextField(
                    value = input,
                    onValueChange = { input = it },
                    modifier = Modifier.weight(1f).focusRequester(focusRequester),
                    placeholder = { Text("Ask GRID…", color = Muted) },
                    maxLines = 4,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                    keyboardActions = KeyboardActions(onSend = { send() }),
                )
                Spacer(Modifier.width(8.dp))
                Button(
                    onClick = { send() },
                    enabled = !busy && input.text.isNotBlank(),
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

    if (showHistory) {
        HistoryDialog(
            threads = threads,
            activeThreadId = threadId,
            onOpen = { id ->
                showHistory = false
                openThread(id)
            },
            onRefresh = { refreshThreads() },
            onClear = {
                scope.launch {
                    try {
                        val cleared = withContext(Dispatchers.IO) {
                            clearThreads(baseUrl, token)
                        }
                        threads = withContext(Dispatchers.IO) {
                            fetchThreads(baseUrl, token)
                        }
                        items.add(
                            Item.System(
                                "Cleared $cleared saved thread(s). Memory and profile were not changed."
                            )
                        )
                    } catch (error: Exception) {
                        items.add(Item.Error(error.message ?: "Could not clear history."))
                    }
                }
            },
            onDismiss = { showHistory = false },
        )
    }

    if (showModels) {
        ModelProviderDialog(
            baseUrl = baseUrl,
            token = token,
            currentProvider = provider,
            currentModel = model,
            providers = providerOptions,
            currentModels = models,
            onApplied = { providerId, modelName, message ->
                provider = providerId
                model = modelName
                showModels = false
                items.add(Item.System(message))
                scope.launch {
                    models = runCatching {
                        withContext(Dispatchers.IO) { fetchCurrentModels(baseUrl, token) }
                    }.getOrDefault(models)
                }
            },
            onDismiss = { showModels = false },
        )
    }
}

private enum class ToolKind { Command, Edit, Read, Tool }

private fun toolKind(name: String): ToolKind = when (name.lowercase()) {
    "run_command", "run_code" -> ToolKind.Command
    "write_file", "delete_file", "create_directory", "save_skill", "delete_skill" ->
        ToolKind.Edit
    "read_file", "document_read", "file_search", "list_directory", "get_cwd",
    "ref_read", "skill_read", "skill_search", "list_skills",
    "memory_recall", "memory_status", "db_query", "db_analytics" ->
        ToolKind.Read
    else -> ToolKind.Tool
}

private sealed interface Item {
    data class User(val text: String) : Item
    data class Assistant(
        val id: String,
        val text: String,
        val durationMs: Long = 0,
        val tokens: Int = 0,
        val estimated: Boolean = false,
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
    data class Tool(
        val callId: String,
        val name: String,
        val args: String,
        val result: String?,
    ) : Item
    data class Artifact(val path: String) : Item
    data class Approval(
        val id: String,
        val tool: String,
        val input: String,
        val risk: String,
        val resolved: Boolean = false,
    ) : Item
    data class Error(val message: String) : Item
    data class System(val message: String) : Item
}

private fun assistantItem(
    id: String,
    text: String,
    stats: GridEvent.Stats?,
): Item.Assistant = Item.Assistant(
    id = id,
    text = text,
    durationMs = stats?.durationMs ?: 0,
    tokens = stats?.totalTokens ?: 0,
    estimated = stats?.estimated ?: false,
)

@Composable
private fun UserBubble(text: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
        Surface(
            color = Color(0xFF123326),
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier.fillMaxWidth(0.86f),
        ) {
            Column(Modifier.padding(start = 11.dp, end = 5.dp, top = 3.dp, bottom = 7.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    CopyButton(text)
                }
                Text(text, color = Color.White, modifier = Modifier.padding(end = 6.dp), fontSize = 14.sp)
            }
        }
    }
}

@Composable
private fun AssistantBubble(
    text: String,
    durationMs: Long = 0,
    tokens: Int = 0,
    estimated: Boolean = false,
) {
    Surface(
        color = PanelRaised,
        shape = RoundedCornerShape(12.dp),
        modifier = Modifier.fillMaxWidth(0.94f),
    ) {
        Column(Modifier.padding(start = 12.dp, end = 5.dp, top = 4.dp, bottom = 9.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text("GRID", color = GridGreen, fontSize = 9.sp, letterSpacing = 1.sp)
                Spacer(Modifier.weight(1f))
                CopyButton(text)
            }
            Text(
                text.ifBlank { "…" },
                color = Color.White,
                modifier = Modifier.padding(end = 7.dp),
                fontSize = 14.sp,
                lineHeight = 20.sp,
            )
            if (durationMs > 0 || tokens > 0) {
                Text(
                    "${formatDuration(durationMs)} · ${formatTokens(tokens)}" +
                        (if (estimated) " est." else "") + " tok",
                    color = Muted,
                    fontSize = 9.sp,
                    fontFamily = FontFamily.Monospace,
                    modifier = Modifier.padding(top = 4.dp),
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
        Column(Modifier.padding(11.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("TOOL", color = GridGreen, fontSize = 9.sp, letterSpacing = 1.sp)
                Spacer(Modifier.width(6.dp))
                Text(item.name, color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                Spacer(Modifier.weight(1f))
                if (item.result != null) {
                    CopyButton(item.result)
                } else {
                    CircularProgressIndicator(
                        modifier = Modifier.size(13.dp),
                        color = GridGreen,
                        strokeWidth = 2.dp,
                    )
                }
            }
            if (item.args.isNotBlank()) {
                Text(
                    item.args,
                    color = Muted,
                    fontSize = 10.sp,
                    fontFamily = FontFamily.Monospace,
                    modifier = Modifier.padding(top = 5.dp),
                )
            }
            item.result?.let {
                HorizontalDivider(color = PanelRaised, modifier = Modifier.padding(vertical = 7.dp))
                Text(
                    it.take(1200),
                    color = GridGreenDim,
                    fontSize = 10.sp,
                    fontFamily = FontFamily.Monospace,
                )
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
        Column(Modifier.padding(12.dp)) {
            Text("REA REPORT", color = GridGreen, fontSize = 9.sp, letterSpacing = 1.sp)
            Text(
                path,
                color = GridGreenDim,
                fontSize = 10.sp,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier.padding(top = 4.dp),
            )
            Text("Open it on the desktop host.", color = Muted, fontSize = 10.sp)
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
        Column(Modifier.padding(12.dp)) {
            Text("APPROVAL REQUIRED", color = Warning, fontSize = 9.sp, letterSpacing = 1.sp)
            Text(
                approval.tool,
                color = Color.White,
                fontSize = 15.sp,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(top = 3.dp),
            )
            Text("risk: ${approval.risk}", color = Muted, fontSize = 10.sp)
            Text(
                approval.input,
                color = GridGreenDim,
                fontSize = 10.sp,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier.padding(top = 5.dp),
            )
            if (approval.resolved) {
                Text("Answered", color = GridGreenDim, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp))
            } else {
                Row(Modifier.padding(top = 9.dp)) {
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
private fun MessageCard(message: String, color: Color) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color(0xFF17120B)),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            Modifier.padding(start = 12.dp, end = 4.dp, top = 6.dp, bottom = 10.dp),
            verticalAlignment = Alignment.Top,
        ) {
            Text(
                message,
                color = color,
                modifier = Modifier.weight(1f),
                fontSize = 12.sp,
            )
            CopyButton(message)
        }
    }
}

@Composable
private fun CopyButton(text: String) {
    val clipboard = LocalClipboardManager.current
    var copied by remember { mutableStateOf(false) }
    LaunchedEffect(copied) {
        if (copied) {
            delay(1500)
            copied = false
        }
    }
    TextButton(
        onClick = {
            clipboard.setText(AnnotatedString(text))
            copied = true
        },
        contentPadding = PaddingValues(horizontal = 4.dp, vertical = 0.dp),
    ) {
        Text(
            if (copied) "Copied" else "Copy",
            color = if (copied) GridGreen else Muted,
            fontSize = 9.sp,
        )
    }
}

@Composable
private fun HistoryDialog(
    threads: List<ThreadSummary>,
    activeThreadId: String,
    onOpen: (String) -> Unit,
    onRefresh: () -> Unit,
    onClear: () -> Unit,
    onDismiss: () -> Unit,
) {
    var confirmClear by remember { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("History") },
        text = {
            if (confirmClear) {
                Text(
                    "Delete all saved threads? Memory, profile and persona are untouched.",
                    color = Color.White,
                    fontSize = 13.sp,
                )
            } else {
                Column {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            "${threads.size} saved thread(s)",
                            color = Muted,
                            fontSize = 10.sp,
                        )
                        Spacer(Modifier.weight(1f))
                        Text("Tap to open", color = Muted, fontSize = 10.sp)
                    }
                    if (threads.isEmpty()) {
                        Text(
                            "No saved threads yet. New runs appear here automatically.",
                            color = Muted,
                            fontSize = 12.sp,
                            modifier = Modifier.padding(vertical = 12.dp),
                        )
                    }
                    LazyColumn(Modifier.fillMaxWidth().heightIn(max = 380.dp)) {
                        itemsIndexed(threads) { _, thread ->
                            Column(
                                Modifier
                                    .fillMaxWidth()
                                    .background(
                                        if (thread.id == activeThreadId) Color(0xFF173B27) else Color.Transparent,
                                        RoundedCornerShape(6.dp),
                                    )
                                    .clickable { onOpen(thread.id) }
                                    .padding(horizontal = 8.dp, vertical = 7.dp),
                            ) {
                                Text(
                                    thread.title.ifBlank { "(untitled)" },
                                    color = Color.White,
                                    fontSize = 13.sp,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                )
                                Text(
                                    "${formatWhen(thread.updatedAt)} · ${thread.messageCount} messages" +
                                        (if (thread.id == activeThreadId) " · active" else ""),
                                    color = Muted,
                                    fontSize = 9.sp,
                                    fontFamily = FontFamily.Monospace,
                                )
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {
            if (confirmClear) {
                TextButton(onClick = {
                    confirmClear = false
                    onClear()
                }) { Text("Delete", color = Danger) }
            } else {
                TextButton(onClick = onDismiss) { Text("Close") }
            }
        },
        dismissButton = {
            if (confirmClear) {
                TextButton(onClick = { confirmClear = false }) { Text("Cancel") }
            } else {
                Row {
                    TextButton(onClick = { confirmClear = true }) { Text("Clear", color = Danger) }
                    TextButton(onClick = onRefresh) { Text("Refresh") }
                }
            }
        },
    )
}

@Composable
private fun ModelProviderDialog(
    baseUrl: String,
    token: String,
    currentProvider: String,
    currentModel: String,
    providers: List<ProviderOption>,
    currentModels: List<String>,
    onApplied: (String, String, String) -> Unit,
    onDismiss: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    var selectedProvider by remember {
        mutableStateOf(providers.firstOrNull { it.id == currentProvider } ?: providers.firstOrNull())
    }
    var models by remember {
        mutableStateOf(
            if (selectedProvider?.id == currentProvider) currentModels else emptyList()
        )
    }
    var loading by remember { mutableStateOf(false) }
    var applying by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    fun loadProvider(option: ProviderOption) {
        selectedProvider = option
        error = null
        loading = true
        models = emptyList()
        scope.launch {
            try {
                models = withContext(Dispatchers.IO) {
                    fetchProviderModels(baseUrl, token, option.id, option.defaultUrl)
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (failure: Exception) {
                error = failure.message ?: "Could not load models."
            } finally {
                loading = false
            }
        }
    }

    fun apply(candidate: String) {
        if (applying) return
        applying = true
        error = null
        val option = selectedProvider
        scope.launch {
            try {
                val message = withContext(Dispatchers.IO) {
                    if (option != null && option.id != currentProvider) {
                        postProvider(
                            baseUrl,
                            token,
                            option.id,
                            option.defaultUrl,
                            candidate,
                        )
                    } else {
                        postModel(baseUrl, token, candidate)
                    }
                }
                onApplied(option?.id ?: currentProvider, candidate, message)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (failure: Exception) {
                error = failure.message ?: "Could not switch model."
            } finally {
                applying = false
            }
        }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Model & provider") },
        text = {
            Column {
                Text("PROVIDER", color = Muted, fontSize = 9.sp, letterSpacing = 1.2.sp)
                providers.forEach { option ->
                    val active = option.id == currentProvider
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .background(
                                if (selectedProvider?.id == option.id) Color(0xFF173B27) else Color.Transparent,
                                RoundedCornerShape(6.dp),
                            )
                            .clickable(enabled = option.available && !applying) {
                                loadProvider(option)
                            }
                            .padding(horizontal = 8.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            option.name,
                            color = if (option.available) Color.White else Muted,
                            fontSize = 12.sp,
                        )
                        Spacer(Modifier.weight(1f))
                        Text(
                            when {
                                !option.available -> "unavailable"
                                active -> "active"
                                option.needsKey && !option.keySet -> "key missing"
                                else -> ""
                            },
                            color = when {
                                !option.available || (option.needsKey && !option.keySet) -> Warning
                                active -> GridGreenDim
                                else -> Muted
                            },
                            fontSize = 9.sp,
                        )
                    }
                }
                HorizontalDivider(color = PanelRaised, modifier = Modifier.padding(vertical = 6.dp))
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text("MODEL", color = Muted, fontSize = 9.sp, letterSpacing = 1.2.sp)
                    Spacer(Modifier.weight(1f))
                    if (loading || applying) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(12.dp),
                            color = GridGreen,
                            strokeWidth = 2.dp,
                        )
                    }
                }
                error?.let {
                    Text(it, color = Danger, fontSize = 10.sp, modifier = Modifier.padding(top = 3.dp))
                }
                LazyColumn(Modifier.fillMaxWidth().heightIn(max = 300.dp)) {
                    itemsIndexed(models) { _, candidate ->
                        val active = candidate == currentModel &&
                            (selectedProvider?.id ?: currentProvider) == currentProvider
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .background(
                                    if (active) Color(0xFF173B27) else Color.Transparent,
                                    RoundedCornerShape(6.dp),
                                )
                                .clickable(enabled = !applying) { apply(candidate) }
                                .padding(horizontal = 8.dp, vertical = 7.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                candidate,
                                color = GridGreenDim,
                                fontSize = 11.sp,
                                fontFamily = FontFamily.Monospace,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.weight(1f),
                            )
                            if (active) {
                                Text("active", color = GridGreenDim, fontSize = 9.sp)
                            }
                        }
                    }
                    if (models.isEmpty() && !loading) {
                        item {
                            Text(
                                "No models listed for this provider.",
                                color = Muted,
                                fontSize = 11.sp,
                                modifier = Modifier.padding(vertical = 8.dp),
                            )
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) { Text("Close") }
        },
    )
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
            delay(1000)
            seconds += 1
        }
    }
    val summary = activityText(activity)
    val label = if (activity.total == 0) "Thinking" + ".".repeat(dots) else "+$summary"
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

private fun fullChatText(
    threadId: String,
    model: String,
    provider: String,
    items: List<Item>,
): String {
    val text = StringBuilder()
    text.appendLine("GRID conversation")
    text.appendLine("Thread: $threadId")
    if (model.isNotBlank() || provider.isNotBlank()) {
        text.appendLine(
            "Model: ${model.ifBlank { "(unknown)" }} · " +
                provider.ifBlank { "(unknown)" }
        )
    }
    text.appendLine()
    items.forEach { item ->
        when (item) {
            is Item.User -> {
                text.appendLine("USER:")
                text.appendLine(item.text)
                text.appendLine()
            }
            is Item.Assistant -> {
                text.appendLine("GRID:")
                text.appendLine(item.text.ifBlank { "(no text)" })
                if (item.durationMs > 0 || item.tokens > 0) {
                    text.appendLine(
                        "(${formatDuration(item.durationMs)} · " +
                            "${formatTokens(item.tokens)}" +
                            (if (item.estimated) " est." else "") + " tok)"
                    )
                }
                text.appendLine()
            }
            is Item.Tool -> {
                text.appendLine("TOOL: ${item.name}")
                if (item.args.isNotBlank()) {
                    text.appendLine("Input: ${item.args}")
                }
                text.appendLine(
                    "Output: " + (item.result?.ifBlank { "(no output)" } ?: "(pending)")
                )
                text.appendLine()
            }
            is Item.Artifact -> {
                text.appendLine("ARTIFACT: ${item.path}")
                text.appendLine()
            }
            is Item.Approval -> {
                text.appendLine("APPROVAL: ${item.tool} (risk: ${item.risk})")
                text.appendLine("Input: ${item.input}")
                text.appendLine(
                    "Status: " + if (item.resolved) "answered" else "pending"
                )
                text.appendLine()
            }
            is Item.Error -> {
                text.appendLine("ERROR:")
                text.appendLine(item.message)
                text.appendLine()
            }
            is Item.System -> {
                text.appendLine("SYSTEM:")
                text.appendLine(item.message)
                text.appendLine()
            }
            is Item.Activity -> {
                if (item.total > 0) {
                    text.appendLine("[${activityText(item)}]")
                    text.appendLine()
                }
            }
        }
    }
    return text.toString().trimEnd() + "\n"
}

private fun formatDuration(ms: Long): String =
    if (ms <= 0) "0.0s" else "%.1fs".format(ms / 1000.0)

private fun formatTokens(tokens: Int): String =
    if (tokens >= 1000) "%.1fk".format(tokens / 1000.0) else tokens.toString()

private fun formatWhen(timestamp: String): String =
    timestamp.replace("T", " ").take(16).ifBlank { "unknown" }

private fun postApproval(
    baseUrl: String,
    token: String,
    approvalId: String,
    decision: String,
): Boolean {
    return try {
        val connection = URL("$baseUrl/api/v1/approvals/$approvalId").openConnection() as HttpURLConnection
        connection.requestMethod = "POST"
        connection.doOutput = true
        connection.setRequestProperty("Authorization", "Bearer $token")
        connection.setRequestProperty("Content-Type", "application/json")
        connection.connectTimeout = 5000
        connection.readTimeout = 5000
        try {
            connection.outputStream.use {
                it.write("{\"decision\":\"$decision\"}".toByteArray())
            }
            connection.responseCode in 200..299
        } finally {
            connection.disconnect()
        }
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
