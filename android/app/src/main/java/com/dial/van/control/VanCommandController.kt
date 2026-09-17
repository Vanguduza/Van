package com.dial.van.control

import com.dial.van.gateway.VanGatewayClient
import com.dial.van.visual.VanLiveVisualState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.UUID

/** Every owner input surface converges here before crossing the signed gateway boundary. */
enum class VanCommandSource {
    CHAT,
    VOICE,
    QUICK_ACTION,
    DECISION,
    TASK,
    PROJECT,
    SYSTEM,
}

enum class VanMessageRole { OWNER, VAN, SYSTEM }

enum class VanCommandStatus {
    LOCAL_DRAFT,
    SUBMITTING,
    APPROVAL_REQUIRED,
    ACCEPTED,
    IN_FLIGHT,
    SUCCEEDED,
    FAILED,
    CANCELLED,
    EXPIRED,
}

data class VanConversationMessage(
    val id: String = UUID.randomUUID().toString(),
    val role: VanMessageRole,
    val text: String,
    val projectId: String? = null,
    val commandId: String? = null,
    val status: VanCommandStatus? = null,
    val createdAtEpochMs: Long = System.currentTimeMillis(),
)

data class VanConversationState(
    val messages: List<VanConversationMessage> = emptyList(),
    val submitting: Boolean = false,
    val selectedProjectId: String? = null,
    val lastError: String? = null,
)

data class VanOwnerCommand(
    val text: String,
    val source: VanCommandSource,
    val projectId: String? = null,
    val actionClass: String = "A1",
    val approvalToken: String? = null,
    val idempotencyKey: String = UUID.randomUUID().toString(),
    val turnId: String? = null,
    val speechEvidenceRef: String? = null,
    val expiresAtUnix: Long? = null,
    val noStaleReplay: Boolean = false,
)

class VanCommandController(
    private val gateway: VanGatewayClient,
    private val scope: CoroutineScope,
) {
    private val _state = MutableStateFlow(VanConversationState())
    val state: StateFlow<VanConversationState> = _state.asStateFlow()

    fun selectProject(projectId: String?) {
        _state.update { it.copy(selectedProjectId = projectId) }
    }

    fun submitText(
        text: String,
        source: VanCommandSource,
        projectId: String? = _state.value.selectedProjectId,
        actionClass: String = "A1",
        approvalToken: String? = null,
        turnId: String? = null,
        speechEvidenceRef: String? = null,
        expiresAtUnix: Long? = null,
        noStaleReplay: Boolean = false,
    ) {
        val normalized = text.trim()
        if (normalized.isEmpty()) return
        val idempotencyKey = if (source == VanCommandSource.VOICE && !turnId.isNullOrBlank()) {
            "voice:$turnId"
        } else {
            UUID.randomUUID().toString()
        }
        submit(
            VanOwnerCommand(
                text = normalized,
                source = source,
                projectId = projectId,
                actionClass = actionClass,
                approvalToken = approvalToken,
                idempotencyKey = idempotencyKey,
                turnId = turnId,
                speechEvidenceRef = speechEvidenceRef,
                expiresAtUnix = expiresAtUnix,
                noStaleReplay = noStaleReplay,
            ),
        )
    }

    fun submit(command: VanOwnerCommand) {
        val normalized = command.text.trim()
        if (normalized.isEmpty()) return

        val ownerMessage = VanConversationMessage(
            role = VanMessageRole.OWNER,
            text = normalized,
            projectId = command.projectId,
            status = VanCommandStatus.LOCAL_DRAFT,
        )
        _state.update {
            it.copy(
                messages = it.messages + ownerMessage,
                submitting = true,
                lastError = null,
            )
        }

        // Fail closed locally. The Android UI cannot manufacture a privileged approval token.
        if (command.actionClass.equals("A4", ignoreCase = true) && command.approvalToken.isNullOrBlank()) {
            VanLiveVisualState.waitingForOwner()
            _state.update {
                it.copy(
                    messages = it.messages + VanConversationMessage(
                        role = VanMessageRole.SYSTEM,
                        text = "A4 owner approval is required before this command can be dispatched.",
                        projectId = command.projectId,
                        status = VanCommandStatus.APPROVAL_REQUIRED,
                    ),
                    submitting = false,
                )
            }
            return
        }

        scope.launch {
            try {
                val response = gateway.dispatchCommand(
                    text = normalized,
                    actionClass = command.actionClass,
                    projectId = command.projectId,
                    idempotencyKey = command.idempotencyKey,
                    approvalToken = command.approvalToken,
                    turnId = command.turnId,
                    originChannel = originChannel(command.source),
                    expiresAtUnix = command.expiresAtUnix,
                    noStaleReplay = command.noStaleReplay,
                    speechEvidenceRef = command.speechEvidenceRef,
                )
                val wireStatus = response.optString("status").lowercase()
                val status = when (wireStatus) {
                    "approval_required" -> VanCommandStatus.APPROVAL_REQUIRED
                    "accepted", "submitted", "executing", "verifying" -> VanCommandStatus.ACCEPTED
                    "in_flight" -> VanCommandStatus.IN_FLIGHT
                    "verified_success", "succeeded", "success", "completed" -> VanCommandStatus.SUCCEEDED
                    "cancelled" -> VanCommandStatus.CANCELLED
                    "expired" -> VanCommandStatus.EXPIRED
                    "denied", "rejected", "rejected_untrusted", "conflict", "failed", "error",
                    "unverifiable", "verification_failed", "partial_success" -> VanCommandStatus.FAILED
                    else -> VanCommandStatus.ACCEPTED
                }

                val responseText = when {
                    response.optString("message").isNotBlank() -> response.optString("message")
                    response.optString("detail").isNotBlank() -> response.optString("detail")
                    status == VanCommandStatus.ACCEPTED || status == VanCommandStatus.IN_FLIGHT ->
                        "Hermes accepted the command. Completion has not been confirmed yet."
                    status == VanCommandStatus.APPROVAL_REQUIRED ->
                        "Owner approval is required before execution can continue."
                    status == VanCommandStatus.SUCCEEDED ->
                        "The requested postcondition has been verified."
                    status == VanCommandStatus.FAILED ->
                        "The command was rejected, failed, or could not be verified."
                    else -> "Command status: ${wireStatus.ifBlank { "accepted" }}"
                }

                _state.update {
                    it.copy(
                        messages = it.messages + VanConversationMessage(
                            role = VanMessageRole.VAN,
                            text = responseText,
                            projectId = command.projectId,
                            commandId = response.optString("command_id").ifBlank { null },
                            status = status,
                        ),
                        submitting = false,
                    )
                }
            } catch (t: Throwable) {
                val safeMessage = t.message?.take(240) ?: t::class.java.simpleName
                _state.update {
                    it.copy(
                        messages = it.messages + VanConversationMessage(
                            role = VanMessageRole.SYSTEM,
                            text = "Command dispatch failed: $safeMessage",
                            projectId = command.projectId,
                            status = VanCommandStatus.FAILED,
                        ),
                        submitting = false,
                        lastError = safeMessage,
                    )
                }
            }
        }
    }

    private fun originChannel(source: VanCommandSource): String = when (source) {
        VanCommandSource.VOICE -> "VOICE"
        VanCommandSource.CHAT -> "TEXT"
        VanCommandSource.SYSTEM -> "SYSTEM_EVENT"
        else -> "UI"
    }
}
