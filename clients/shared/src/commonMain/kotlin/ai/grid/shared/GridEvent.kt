package ai.grid.shared

/**
 * GRID's stable client-facing view of an AG-UI run.
 *
 * The UI never depends on the AG-UI SDK directly; the wrapper keeps a small
 * surface so a protocol/SDK change does not reach every screen.
 */
sealed interface GridEvent {
    data class RunStarted(val threadId: String, val runId: String) : GridEvent
    data class StepStarted(val name: String) : GridEvent
    data class StepFinished(val name: String) : GridEvent
    data class MessageStarted(val messageId: String) : GridEvent
    data class TextDelta(val messageId: String, val delta: String) : GridEvent
    data class MessageFinished(val messageId: String) : GridEvent
    data class ToolStarted(val callId: String, val name: String) : GridEvent
    data class ToolArgs(val callId: String, val delta: String) : GridEvent
    data class ToolEnded(val callId: String) : GridEvent
    data class ToolResult(val callId: String, val content: String) : GridEvent
    data class Activity(
        val messageId: String,
        val activityType: String,
        val content: String,
    ) : GridEvent
    data class Artifact(val path: String, val kind: String) : GridEvent
    data class ApprovalRequired(
        val approvalId: String,
        val tool: String,
        val input: String,
        val risk: String,
    ) : GridEvent
    data class Stats(
        val durationMs: Long,
        val inputTokens: Int,
        val outputTokens: Int,
        val totalTokens: Int,
        val model: String,
        val toolCalls: Int,
        val estimated: Boolean,
    ) : GridEvent
    data class Ui(
        val surfaceId: String,
        val toolCallId: String,
        val artifactPath: String,
        val artifactKind: String,
        val fallback: String,
        val root: String,
    ) : GridEvent
    data class Custom(val name: String, val value: String) : GridEvent
    data class RunFinished(val threadId: String, val runId: String) : GridEvent
    data class Error(val message: String) : GridEvent
    data class Other(val type: String) : GridEvent
}
