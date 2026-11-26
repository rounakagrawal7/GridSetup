package ai.grid.shared

import com.agui.client.AgUiAgent
import com.agui.core.types.ActivitySnapshotEvent
import com.agui.core.types.BaseEvent
import com.agui.core.types.CustomEvent
import com.agui.core.types.RunErrorEvent
import com.agui.core.types.RunFinishedEvent
import com.agui.core.types.RunStartedEvent
import com.agui.core.types.StepFinishedEvent
import com.agui.core.types.StepStartedEvent
import com.agui.core.types.TextMessageContentEvent
import com.agui.core.types.TextMessageEndEvent
import com.agui.core.types.TextMessageStartEvent
import com.agui.core.types.ToolCallArgsEvent
import com.agui.core.types.ToolCallEndEvent
import com.agui.core.types.ToolCallResultEvent
import com.agui.core.types.ToolCallStartEvent
import com.agui.core.types.UserMessage
import com.agui.core.types.RunAgentInput
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import kotlin.random.Random

/**
 * Thin adapter over the community AG-UI Kotlin client.
 *
 * The SDK is still 0.x; everything the UI consumes goes through [GridEvent] so
 * we can replace the transport without touching the screens.
 */
class GridAgentClient(
    baseUrl: String,
    private val token: String,
) {
    private val endpoint = baseUrl.trimEnd('/') + "/api/v1/agent"
    private val agent = AgUiAgent(endpoint) {
        bearerToken = token
        requestTimeout = 600_000L
        connectTimeout = 10_000L
    }

    fun run(
        prompt: String,
        threadId: String,
        runId: String = newId("run"),
    ): Flow<GridEvent> {
        val input = RunAgentInput(
            threadId = threadId,
            runId = runId,
            messages = listOf(UserMessage(id = newId("msg"), content = prompt)),
        )
        return agent.run(input).map { event -> event.toGridEvent() }
    }

    companion object {
        fun newThreadId(): String = newId("thr")

        fun newId(prefix: String): String {
            val random = Random.nextLong().toULong().toString(16)
            return "$prefix-$random"
        }
    }
}

private fun JsonElement.string(key: String): String =
    (this as? JsonObject)?.get(key)?.jsonPrimitive?.contentOrNull ?: ""

private fun JsonElement.int(key: String): Int =
    (this as? JsonObject)?.get(key)?.jsonPrimitive?.intOrNull ?: 0

private fun JsonElement.long(key: String): Long =
    (this as? JsonObject)?.get(key)?.jsonPrimitive?.longOrNull ?: 0L

private fun JsonElement.boolean(key: String): Boolean =
    (this as? JsonObject)?.get(key)?.jsonPrimitive?.booleanOrNull ?: false

private fun BaseEvent.toGridEvent(): GridEvent = when (this) {
    is RunStartedEvent -> GridEvent.RunStarted(threadId, runId)
    is StepStartedEvent -> GridEvent.StepStarted(stepName)
    is StepFinishedEvent -> GridEvent.StepFinished(stepName)
    is TextMessageStartEvent -> GridEvent.MessageStarted(messageId)
    is TextMessageContentEvent -> GridEvent.TextDelta(messageId, delta)
    is TextMessageEndEvent -> GridEvent.MessageFinished(messageId)
    is ToolCallStartEvent -> GridEvent.ToolStarted(toolCallId, toolCallName)
    is ToolCallArgsEvent -> GridEvent.ToolArgs(toolCallId, delta)
    is ToolCallEndEvent -> GridEvent.ToolEnded(toolCallId)
    is ToolCallResultEvent -> GridEvent.ToolResult(toolCallId, content)
    is ActivitySnapshotEvent -> GridEvent.Activity(
        messageId = messageId,
        activityType = activityType,
        content = content.toString(),
    )
    is CustomEvent -> when (name) {
        "grid.artifact" -> GridEvent.Artifact(
            path = value.string("path"),
            kind = value.string("kind"),
        )
        "grid.approval_required" -> GridEvent.ApprovalRequired(
            approvalId = value.string("approvalId"),
            tool = value.string("tool"),
            input = value.string("input"),
            risk = value.string("risk"),
        )
        "grid.stats" -> GridEvent.Stats(
            durationMs = value.long("durationMs"),
            inputTokens = value.int("inputTokens"),
            outputTokens = value.int("outputTokens"),
            totalTokens = value.int("totalTokens"),
            model = value.string("model"),
            toolCalls = value.int("toolCalls"),
            estimated = value.boolean("estimated"),
        )
        "grid.ui" -> GridEvent.Ui(
            surfaceId = value.string("surfaceId"),
            toolCallId = value.string("toolCallId"),
            artifactPath = value.string("artifactPath"),
            artifactKind = value.string("artifactKind"),
            fallback = value.string("fallback"),
            root = (value as? JsonObject)?.get("root")?.toString() ?: "",
        )
        else -> GridEvent.Custom(name, value.toString())
    }
    is RunFinishedEvent -> GridEvent.RunFinished(threadId, runId)
    is RunErrorEvent -> GridEvent.Error(message)
    else -> GridEvent.Other(eventType.name)
}
