package ai.grid.android

import ai.grid.shared.GridAgentClient
import ai.grid.shared.GridEvent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
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
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.PasswordVisualTransformation
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
    var baseUrl by remember { mutableStateOf(store.loadUrl()) }
    var token by remember { mutableStateOf(store.loadToken()) }
    var editing by remember { mutableStateOf(token.isBlank()) }

    if (editing) {
        SetupScreen(
            initialUrl = baseUrl,
            initialToken = token,
            onConnect = { url, newToken ->
                baseUrl = url.trimEnd('/')
                token = newToken
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
    initialUrl: String,
    initialToken: String,
    onConnect: (String, String) -> Unit,
) {
    var url by remember { mutableStateOf(initialUrl) }
    var token by remember { mutableStateOf(initialToken) }

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

        Text("HOST URL", color = Muted, fontSize = 11.sp)
        OutlinedTextField(
            value = url,
            onValueChange = { url = it },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            placeholder = { Text(TokenStore.DEFAULT_URL) },
        )
        Text(
            "Emulator: http://10.0.2.2:8771\n" +
                "Physical device: http://<computer-LAN-IP>:8771 (set api.host to 0.0.0.0)",
            color = Muted,
            fontSize = 11.sp,
        )

        Text("API TOKEN", color = Muted, fontSize = 11.sp)
        OutlinedTextField(
            value = token,
            onValueChange = { token = it },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            placeholder = { Text("paste run/api_token") },
        )
        Text(
            "The token is stored encrypted with the Android Keystore.",
            color = Muted,
            fontSize = 11.sp,
        )

        Spacer(Modifier.height(8.dp))
        Button(
            onClick = { onConnect(url, token.trim()) },
            enabled = url.isNotBlank() && token.isNotBlank(),
            colors = ButtonDefaults.buttonColors(containerColor = GridGreen, contentColor = Color.Black),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Connect to GRID")
        }
        Text(
            "Start the host first:\npython grid_agent.py --api --no-input",
            color = GridGreenDim,
            fontSize = 12.sp,
            fontFamily = FontFamily.Monospace,
        )
    }
}

@Composable
private fun ChatScreen(baseUrl: String, token: String, onSettings: () -> Unit) {
    val scope = rememberCoroutineScope()
    val items = remember { mutableStateListOf<Item>() }
    val listState = rememberLazyListState()
    var input by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("Connecting") }
    var threadId by remember { mutableStateOf(GridAgentClient.newThreadId()) }
    var toolCommands by remember { mutableStateOf<List<SlashCommand>>(emptyList()) }
    val client = remember(baseUrl, token) { GridAgentClient(baseUrl, token) }
    val focusRequester = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current

    LaunchedEffect(baseUrl, token) {
        status = "Connecting"
        val online = withContext(Dispatchers.IO) { apiHealthy(baseUrl, token) }
        status = if (online) "Ready" else "API offline"
        if (!online) {
            items.add(
                Item.System(
                    "GRID API is offline at $baseUrl.\n" +
                        "Start it with: python grid_agent.py --api --no-input"
                )
            )
        } else {
            toolCommands = withContext(Dispatchers.IO) { fetchToolCommands(baseUrl, token) }
        }
    }

    LaunchedEffect(items.size) {
        if (items.isNotEmpty()) listState.animateScrollToItem(items.lastIndex)
    }

    fun handle(event: GridEvent) {
        when (event) {
            is GridEvent.RunStarted -> {
                threadId = event.threadId
                status = "Running ${event.runId.take(8)}"
            }
            is GridEvent.StepStarted -> status = event.name
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
            is GridEvent.ToolStarted -> items.add(Item.Tool(event.callId, event.name, "", null))
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
            is GridEvent.Artifact -> items.add(Item.Artifact(event.path))
            is GridEvent.ApprovalRequired -> items.add(
                Item.Approval(
                    id = event.approvalId,
                    tool = event.tool,
                    input = event.input,
                    risk = event.risk,
                )
            )
            is GridEvent.Stats -> Unit
            is GridEvent.Ui -> Unit
            is GridEvent.Custom -> Unit
            is GridEvent.RunFinished -> status = "Ready"
            is GridEvent.Error -> {
                items.add(Item.Error(event.message))
                status = "Error"
            }
            is GridEvent.Other -> Unit
        }
    }

    fun runPrompt(prompt: String) {
        items.add(Item.User(prompt))
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
        val prompt = input.trim()
        if (prompt.isEmpty() || busy) return
        input = ""
        if (prompt.startsWith("/") && handleSlash(prompt)) return
        runPrompt(prompt)
    }

    val allCommands = remember(toolCommands) {
        mergeSlashCommands(APP_COMMANDS, toolCommands)
    }
    val palette = remember(input, allCommands) {
        buildSlashPalette(input, allCommands)
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
                Text(status, color = if (status == "API offline") Danger else GridGreenDim, fontSize = 11.sp)
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(threadId, color = Muted, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                Spacer(Modifier.weight(1f))
                TextButton(onClick = {
                    threadId = GridAgentClient.newThreadId()
                    items.clear()
                    status = "Ready"
                }) { Text("New") }
                TextButton(onClick = onSettings) { Text("Settings") }
            }
            HorizontalDivider(color = PanelRaised)
        }

        LazyColumn(
            state = listState,
            modifier = Modifier.weight(1f).fillMaxWidth().padding(horizontal = 12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            itemsIndexed(items) { index, item ->
                when (item) {
                    is Item.User -> UserBubble(item.text)
                    is Item.Assistant -> AssistantBubble(item.text)
                    is Item.Tool -> ToolCard(item)
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
                                            input = suggestion.applyText
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
                    enabled = !busy && input.isNotBlank(),
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

private sealed interface Item {
    data class User(val text: String) : Item
    data class Assistant(val id: String, val text: String) : Item
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

@Composable
private fun UserBubble(text: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
        Surface(
            color = Color(0xFF123326),
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier.fillMaxWidth(0.86f),
        ) {
            Text(text, color = Color.White, modifier = Modifier.padding(11.dp), fontSize = 14.sp)
        }
    }
}

@Composable
private fun AssistantBubble(text: String) {
    Surface(
        color = PanelRaised,
        shape = RoundedCornerShape(12.dp),
        modifier = Modifier.fillMaxWidth(0.94f),
    ) {
        Text(
            text.ifBlank { "…" },
            color = Color.White,
            modifier = Modifier.padding(12.dp),
            fontSize = 14.sp,
            lineHeight = 20.sp,
        )
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
                if (item.result == null) {
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
        Text(
            message,
            color = color,
            modifier = Modifier.padding(12.dp),
            fontSize = 12.sp,
        )
    }
}

private fun apiHealthy(baseUrl: String, token: String): Boolean {
    return try {
        val connection = URL("$baseUrl/api/v1/health").openConnection() as HttpURLConnection
        connection.requestMethod = "GET"
        connection.setRequestProperty("Authorization", "Bearer $token")
        connection.connectTimeout = 2500
        connection.readTimeout = 2500
        try {
            connection.responseCode == 200
        } finally {
            connection.disconnect()
        }
    } catch (_: Exception) {
        false
    }
}

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
