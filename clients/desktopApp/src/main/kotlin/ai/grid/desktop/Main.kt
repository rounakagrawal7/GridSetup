// Compose UI functions use PascalCase by convention.
@file:Suppress("FunctionName")

package ai.grid.desktop

import ai.grid.shared.GridAgentClient
import ai.grid.shared.GridEvent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
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
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import java.awt.Desktop
import java.io.File
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
import kotlin.time.Duration.Companion.milliseconds

private val Background = Color(0xFF0B0F0C)
private val Panel = Color(0xFF111813)
private val PanelRaised = Color(0xFF162119)
private val GridGreen = Color(0xFF00FF88)
private val GridGreenDim = Color(0xFF7CF7B0)
private val Muted = Color(0xFF8A9B8F)
private val Danger = Color(0xFFFF6B6B)
private val Warning = Color(0xFFFFD166)

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
                App(baseUrl.trimEnd('/'), token)
            }
        }
    }
}

@Composable
private fun App(baseUrl: String, token: String) {
    val scope = rememberCoroutineScope()
    val items = remember { mutableStateListOf<Item>() }
    val listState = rememberLazyListState()
    val inputFocus = remember { FocusRequester() }
    var input by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("Ready") }
    var threadId by remember { mutableStateOf(GridAgentClient.newThreadId()) }
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
        }
    }

    LaunchedEffect(Unit) {
        inputFocus.requestFocus()
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
            is GridEvent.Custom -> Unit
            is GridEvent.RunFinished -> {
                busy = false
                status = "Ready"
            }
            is GridEvent.Error -> {
                items.add(Item.Error(event.message))
                busy = false
                status = "Error"
            }
            is GridEvent.Other -> Unit
        }
    }

    fun send() {
        val prompt = input.trim()
        if (prompt.isEmpty() || busy) return
        input = ""
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

    Row(Modifier.fillMaxSize().background(Background)) {
        Sidebar(
            status = status,
            threadId = threadId,
            baseUrl = baseUrl,
            tokenReady = token.isNotBlank(),
            onNewThread = {
                threadId = GridAgentClient.newThreadId()
                items.clear()
                status = "Ready"
            },
            onQuickPrompt = {
                input = it
                send()
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
            LazyColumn(
                state = listState,
                modifier = Modifier.weight(1f).fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(10.dp),
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
                        is Item.Error -> ErrorCard(item.message)
                    }
                }
            }
            Spacer(Modifier.height(12.dp))
            Composer(
                input = input,
                busy = busy,
                enabled = token.isNotBlank(),
                focusRequester = inputFocus,
                onInput = { input = it },
                onSend = { send() },
            )
        }
    }
}

@Composable
private fun Sidebar(
    status: String,
    threadId: String,
    baseUrl: String,
    tokenReady: Boolean,
    onNewThread: () -> Unit,
    onQuickPrompt: (String) -> Unit,
) {
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
        Spacer(Modifier.height(18.dp))
        Button(
            onClick = onNewThread,
            colors = ButtonDefaults.buttonColors(containerColor = PanelRaised, contentColor = GridGreen),
            modifier = Modifier.fillMaxWidth(),
        ) { Text("New thread") }
        Spacer(Modifier.height(22.dp))
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
private fun AssistantBubble(text: String) {
    Surface(
        color = PanelRaised,
        shape = RoundedCornerShape(14.dp),
        modifier = Modifier.fillMaxWidth(0.9f),
    ) {
        SelectionContainer {
            Text(
                text.ifBlank { "…" },
                color = Color.White,
                modifier = Modifier.padding(14.dp),
                fontSize = 14.sp,
                lineHeight = 21.sp,
            )
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
private fun ErrorCard(message: String) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color(0xFF2A1414)),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(message, color = Danger, modifier = Modifier.padding(13.dp), fontSize = 12.sp)
    }
}

@Composable
private fun Composer(
    input: String,
    busy: Boolean,
    enabled: Boolean,
    focusRequester: FocusRequester,
    onInput: (String) -> Unit,
    onSend: () -> Unit,
) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom) {
        OutlinedTextField(
            value = input,
            onValueChange = onInput,
            modifier = Modifier.weight(1f).focusRequester(focusRequester).onPreviewKeyEvent { event ->
                if (
                    enabled && !busy &&
                    event.type == KeyEventType.KeyDown &&
                    event.key == Key.Enter &&
                    !event.isShiftPressed
                ) {
                    onSend()
                    true
                } else {
                    false
                }
            },
            placeholder = { Text("Ask GRID, run a tool, or request a teardown…", color = Muted) },
            maxLines = 4,
            enabled = enabled,
        )
        Spacer(Modifier.width(10.dp))
        Button(
            onClick = onSend,
            enabled = enabled && !busy && input.isNotBlank(),
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
