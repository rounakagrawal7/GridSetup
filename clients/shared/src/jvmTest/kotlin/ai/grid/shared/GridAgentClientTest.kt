package ai.grid.shared

import com.sun.net.httpserver.HttpServer
import java.net.InetSocketAddress
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.flow.toList

class GridAgentClientTest {
    @Test
    fun parsesTheSameSseFramesAsThePythonApi() {
        val frames = listOf(
            """{"type":"RUN_STARTED","threadId":"thr-1","runId":"run-1","protocolVersion":"1.0"}""",
            """{"type":"STEP_STARTED","stepName":"agent"}""",
            """{"type":"TOOL_CALL_START","toolCallId":"call-1","toolCallName":"ping"}""",
            """{"type":"TOOL_CALL_ARGS","toolCallId":"call-1","delta":"{\"input\":\"127.0.0.1\"}"}""",
            """{"type":"TOOL_CALL_END","toolCallId":"call-1"}""",
            """{"type":"TOOL_CALL_RESULT","messageId":"msg-tool","toolCallId":"call-1","content":"Pinging 127.0.0.1"}""",
            """{"type":"TEXT_MESSAGE_START","messageId":"msg-1","role":"assistant"}""",
            """{"type":"TEXT_MESSAGE_CONTENT","messageId":"msg-1","delta":"hello"}""",
            """{"type":"TEXT_MESSAGE_END","messageId":"msg-1"}""",
            """{"type":"CUSTOM","name":"grid.artifact","value":{"path":"refs/rea/x/report.md","kind":"rea_report"}}""",
            """{"type":"CUSTOM","name":"grid.stats","value":{"durationMs":1234,"inputTokens":100,"outputTokens":50,"totalTokens":150,"model":"test-model","toolCalls":1,"estimated":false}}""",
            """{"type":"STEP_FINISHED","stepName":"agent"}""",
            """{"type":"RUN_FINISHED","threadId":"thr-1","runId":"run-1","outcome":{"type":"success"}}""",
        )
        val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        server.createContext("/api/v1/agent") { exchange ->
            exchange.requestBody.readBytes()
            exchange.responseHeaders.add("Content-Type", "text/event-stream")
            exchange.sendResponseHeaders(200, 0)
            exchange.responseBody.bufferedWriter().use { writer ->
                frames.forEach { frame ->
                    writer.write("data: $frame\n\n")
                    writer.flush()
                }
            }
        }
        server.start()
        try {
            val client = GridAgentClient("http://127.0.0.1:${server.address.port}", "test-token")
            val events = runBlocking {
                client.run("ping 127.0.0.1", "thr-1", "run-1").toList()
            }
            assertTrue(events.first() is GridEvent.RunStarted)
            assertTrue(events.any { it is GridEvent.ToolStarted && it.name == "ping" })
            val toolResult = events.filterIsInstance<GridEvent.ToolResult>().single()
            assertEquals("Pinging 127.0.0.1", toolResult.content)
            val delta = events.filterIsInstance<GridEvent.TextDelta>().single()
            assertEquals("hello", delta.delta)
            val artifact = events.filterIsInstance<GridEvent.Artifact>().single()
            assertEquals("refs/rea/x/report.md", artifact.path)
            val stats = events.filterIsInstance<GridEvent.Stats>().single()
            assertEquals(150, stats.totalTokens)
            assertEquals(1234L, stats.durationMs)
            assertEquals("test-model", stats.model)
            assertTrue(events.last() is GridEvent.RunFinished)
        } finally {
            server.stop(0)
        }
    }
}
