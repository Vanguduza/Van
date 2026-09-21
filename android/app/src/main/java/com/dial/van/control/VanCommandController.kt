package com.dial.van.control

import androidx.fragment.app.FragmentActivity
import com.dial.van.gateway.GatewayHttpException
import com.dial.van.gateway.VanGatewayClient
import com.dial.van.security.BiometricGate
import com.dial.van.session.OfflineSubmission
import com.dial.van.status.OwnerStatusProjection
import com.dial.van.status.OwnerWorkStatus
import com.dial.van.status.VanCommandStatus
import com.dial.van.status.commandStatusFor
import com.dial.van.visual.VanLiveVisualState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.UUID
import kotlin.math.roundToInt

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


data class VanConversationMessage(
    val id: String = UUID.randomUUID().toString(),
    val role: VanMessageRole,
    val text: String,
    val projectId: String? = null,
    val commandId: String? = null,
    val status: VanCommandStatus? = null,
    val createdAtEpochMs: Long = System.currentTimeMillis(),
)

data class VanOwnerCommand(
    val text: String,
    val source: VanCommandSource,
    val projectId: String? = null,
    val actionClass: String = "A1",
    /** Deprecated compatibility field; it never grants A4 authority. */
    val approvalToken: String? = null,
    val idempotencyKey: String = UUID.randomUUID().toString(),
    val turnId: String? = null,
    val speechEvidenceRef: String? = null,
    /** Signed fixed-point speaker similarity provenance, never authentication. */
    val speakerEvidenceMilli: Int? = null,
    val expiresAtUnix: Long? = null,
    val noStaleReplay: Boolean = false,
)

data class PendingA4Approval(
    val command: VanOwnerCommand,
    val challengeId: String,
    val challenge: String,
    val expiresAtUnix: Long,
    val resolvedActionId: String,
    val noStaleReplay: Boolean,
    val maxAgeSeconds: Int?,
)

data class VanConversationState(
    val messages: List<VanConversationMessage> = emptyList(),
    val submitting: Boolean = false,
    val selectedProjectId: String? = null,
    val lastError: String? = null,
    val pendingA4Approval: PendingA4Approval? = null,
)

class VanCommandController(
    private val gateway: VanGatewayClient,
    private val scope: CoroutineScope,
    /**
     * P1-VOICE-001 — how VAN says an outcome out loud.
     *
     * `TtsOutputManager.speak` had zero call sites: VAN could speak and never did. Spoken
     * only for a command the owner *spoke*, and only when the outcome is worth interrupting
     * for — reading every status change aloud is how an assistant gets muted.
     */
    private val speak: (String) -> Unit = {},
) {
    private val _state = MutableStateFlow(VanConversationState())
    val state: StateFlow<VanConversationState> = _state.asStateFlow()

    /**
     * §20.14 — where a command goes when it could not be sent.
     *
     * A property assigned after construction rather than a constructor parameter, because
     * `VanApplication` builds this controller before it builds the session and the
     * session needs the same gateway client. A lambda rather than the session type, so
     * this class keeps knowing nothing about transports.
     *
     * Null means there is no outbox, and [recordFailure] says so rather than pretending:
     * a build with nothing behind this must not tell the owner their work was saved.
     * It returns whether the command was actually stored.
     */
    var storeForLater: ((body: org.json.JSONObject, needsReconfirm: Boolean) -> Boolean)? = null

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
        /**
         * P2-SEC-010 — how sure VAN is that the owner spoke.
         *
         * Null for anything that did not come through a microphone. For voice it is the
         * speaker similarity score, and [SpeakerVerificationPolicy] decides what authority
         * a spoken command carries on it: any voice reaching the microphone used to produce
         * a transcript that was signed as an owner command, so a visitor, a television or a
         * recording had the owner's authority for as long as they were in the room.
         */
        speakerScore: Float? = null,
    ) {
        val normalized = text.trim()
        if (normalized.isEmpty()) return

        // Android does not decide the authority of spoken text. The deterministic gateway
        // resolver may classify an A1-looking transcript as A3/A4, so deciding here would
        // enforce the wrong class. The device only measures and signs fixed-point provenance;
        // the gateway applies SpeakerVerificationPolicy-equivalent thresholds after resolution.
        val speakerEvidenceMilli = if (source == VanCommandSource.VOICE) {
            speakerScore
                ?.takeIf { it.isFinite() }
                ?.coerceIn(0f, 1f)
                ?.times(1000f)
                ?.roundToInt()
        } else {
            null
        }
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
                speakerEvidenceMilli = speakerEvidenceMilli,
                expiresAtUnix = expiresAtUnix,
                noStaleReplay = noStaleReplay,
            ),
        )
    }

    /**
     * P2-SEC-010 — a spoken command VAN will not act on, and the owner is told why.
     *
     * Both turns are recorded: what was heard, and that nothing was done about it. A refusal
     * that leaves no trace is indistinguishable from a command that was never heard, and the
     * owner needs to be able to tell those apart — particularly when it was in fact them.
     */
    private fun refuseSpokenCommand(text: String, reason: String) {
        _state.update {
            it.copy(
                submitting = false,
                messages = it.messages +
                    VanConversationMessage(
                        role = VanMessageRole.OWNER,
                        text = text,
                        projectId = it.selectedProjectId,
                        status = VanCommandStatus.REFUSED,
                    ) +
                    VanConversationMessage(
                        role = VanMessageRole.VAN,
                        text = reason,
                        projectId = it.selectedProjectId,
                        status = VanCommandStatus.REFUSED,
                    ),
            )
        }
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

        // A4 requests are allowed to reach the gateway only to obtain a one-time
        // cryptographic challenge. They cannot execute until approvePendingA4()
        // supplies a biometric-bound signature over that challenge.
        // `Dispatchers.IO` because the failure branch writes to the encrypted outbox with
        // a synchronous `commit()`, and the scope's default pool is sized for CPU work.
        scope.launch(Dispatchers.IO) {
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
                    speakerEvidenceMilli = command.speakerEvidenceMilli,
                )
                recordResponse(command, response)
            } catch (t: Throwable) {
                recordFailure(command, t)
            }
        }
    }

    fun approvePendingA4(activity: FragmentActivity) {
        val pending = _state.value.pendingA4Approval ?: return
        val now = System.currentTimeMillis() / 1000L
        if (now >= pending.expiresAtUnix) {
            _state.update {
                it.copy(
                    pendingA4Approval = null,
                    submitting = false,
                    lastError = "A4 approval challenge expired",
                    messages = it.messages + VanConversationMessage(
                        role = VanMessageRole.SYSTEM,
                        text = "A4 approval challenge expired. Issue the command again.",
                        projectId = pending.command.projectId,
                        status = VanCommandStatus.EXPIRED,
                    ),
                )
            }
            return
        }

        val gate = BiometricGate(activity)
        val signingSignature = try {
            gateway.newA4ApprovalSignature()
        } catch (t: Throwable) {
            _state.update { it.copy(lastError = t.message ?: "A4 approval key unavailable") }
            return
        }

        gate.requestA4CommandApproval(
            signature = signingSignature,
            challenge = pending.challenge,
            onApproved = { signatureBase64 ->
                _state.update { it.copy(submitting = true, lastError = null) }
                scope.launch {
                    try {
                        val approvedAt = System.currentTimeMillis() / 1000L
                        val replayWindow = (pending.maxAgeSeconds ?: 60).coerceIn(1, 60)
                        val expiresAt = if (pending.noStaleReplay) approvedAt + replayWindow else null
                        val response = gateway.dispatchCommand(
                            text = pending.command.text,
                            actionClass = pending.command.actionClass,
                            projectId = pending.command.projectId,
                            idempotencyKey = "a4:${pending.challengeId}:${UUID.randomUUID()}",
                            approvalChallengeId = pending.challengeId,
                            approvalSignatureBase64 = signatureBase64,
                            issuedAtUnix = approvedAt,
                            turnId = pending.command.turnId,
                            originChannel = originChannel(pending.command.source),
                            expiresAtUnix = expiresAt,
                            noStaleReplay = pending.noStaleReplay,
                            speechEvidenceRef = pending.command.speechEvidenceRef,
                            speakerEvidenceMilli = pending.command.speakerEvidenceMilli,
                        )
                        recordResponse(pending.command, response)
                    } catch (t: Throwable) {
                        recordFailure(pending.command, t)
                    }
                }
            },
            onDenied = { reason ->
                _state.update {
                    it.copy(
                        submitting = false,
                        lastError = reason,
                        messages = it.messages + VanConversationMessage(
                            role = VanMessageRole.SYSTEM,
                            text = "A4 approval was not granted: $reason",
                            projectId = pending.command.projectId,
                            status = VanCommandStatus.APPROVAL_REQUIRED,
                        ),
                    )
                }
            },
        )
    }

    private fun recordResponse(command: VanOwnerCommand, response: org.json.JSONObject) {
        val wireStatus = response.optString("status").lowercase()
        // P0-EXEC-003. The status is no longer decided here. It goes through the one
        // projection the gateway also uses, so the device cannot drift into its own
        // vocabulary, and an unrecognised status becomes UNKNOWN rather than ACCEPTED.
        val ownerStatus = OwnerStatusProjection.fromCommandResult(wireStatus)
        val status = commandStatusFor(ownerStatus)

        val pending = if (status == VanCommandStatus.APPROVAL_REQUIRED) {
            val challengeId = response.optString("approval_challenge_id")
            val challenge = response.optString("approval_challenge")
            val expiresAt = response.optLong("approval_expires_at_unix", 0L)
            val actionId = response.optString("resolved_action_id")
            if (challengeId.isNotBlank() && challenge.isNotBlank() && expiresAt > 0L && actionId.isNotBlank()) {
                PendingA4Approval(
                    command = command,
                    challengeId = challengeId,
                    challenge = challenge,
                    expiresAtUnix = expiresAt,
                    resolvedActionId = actionId,
                    noStaleReplay = response.optBoolean("no_stale_replay", false),
                    maxAgeSeconds = response.optInt("max_age_seconds", 0).takeIf { it > 0 },
                )
            } else {
                null
            }
        } else {
            null
        }

        val responseText = when {
            response.optString("message").isNotBlank() -> response.optString("message")
            response.optString("detail").isNotBlank() -> response.optString("detail")
            // One sentence per owner status, shared with the gateway. The old fallback
            // read "Command status: accepted" for a blank status, which invented an
            // acceptance the gateway never sent.
            else -> OwnerStatusProjection.sentenceFor(ownerStatus)
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
                pendingA4Approval = pending,
                lastError = if (status == VanCommandStatus.FAILED) responseText else null,
            )
        }
        if (shouldSpeak(command, ownerStatus)) speak(responseText)
    }

    /**
     * Whether this outcome is worth saying out loud.
     *
     * Spoken only for a command the owner spoke — answering a typed command aloud is
     * startling — and only when the outcome is one they have to know about: something
     * finished, something needs them, or something was refused. "Working on it" said aloud
     * after every command is how an assistant gets muted, and a muted assistant cannot tell
     * the owner the things that matter.
     */
    private fun shouldSpeak(command: VanOwnerCommand, ownerStatus: OwnerWorkStatus): Boolean {
        if (command.source != VanCommandSource.VOICE) return false
        return OwnerStatusProjection.isFinished(ownerStatus) ||
            OwnerStatusProjection.needsOwner(ownerStatus)
    }

    /**
     * §20.14 — the command did not go out, so it is held or the owner is told it did not.
     *
     * This used to append "Command dispatch failed" and stop. Nothing stored the command
     * and nothing retried it, so an instruction given in a tunnel was gone — the exact
     * failure §20.14 exists to prevent, reached by the one path nobody had connected to
     * the outbox (P0-SESS-011).
     *
     * The decision is [OfflineSubmission]'s, not this method's. Whether a refusal may be
     * replayed later and whether an A4 may be stored at all are the two rules worth
     * getting right, and they belong somewhere a test can execute them.
     */
    private fun recordFailure(command: VanOwnerCommand, throwable: Throwable) {
        val safeMessage = throwable.message?.take(240) ?: throwable::class.java.simpleName
        // An HTTP status came back, so the command arrived and was answered. A timeout or
        // a dropped connection did not, and only that may be held.
        val gatewayAnswered = throwable is GatewayHttpException
        val verdict = OfflineSubmission.decide(
            actionClass = command.actionClass,
            // No separate signal for this at this call site yet: nothing upstream marks a
            // command as only meaningful with the owner present. Stated rather than
            // guessed, because passing `noStaleReplay` here — which was the first version
            // — conflates a sixty-second Gateway contract with a storage policy, and the
            // two want opposite answers.
            requiresLiveOwnerContext = false,
            gatewayAnswered = gatewayAnswered,
            failureSummary = safeMessage,
            noStaleReplay = command.noStaleReplay,
        )
        val stored = when (verdict) {
            is OfflineSubmission.Verdict.Store -> storeSignedBody(command, verdict.needsReconfirm)
            is OfflineSubmission.Verdict.Drop -> false
        }
        // Said rather than assumed. A build with no outbox behind `storeForLater`, or a
        // store that refused, must not leave the owner told their work was saved.
        val text = if (stored) verdict.ownerMessage else when (verdict) {
            is OfflineSubmission.Verdict.Drop -> verdict.ownerMessage
            is OfflineSubmission.Verdict.Store -> "Not sent, and not saved: $safeMessage"
        }
        _state.update {
            it.copy(
                messages = it.messages + VanConversationMessage(
                    role = VanMessageRole.SYSTEM,
                    text = text,
                    projectId = command.projectId,
                    status = if (stored) VanCommandStatus.QUEUED else VanCommandStatus.FAILED,
                ),
                submitting = false,
                lastError = if (stored) null else safeMessage,
            )
        }
    }

    /**
     * Build the body the Gateway would have received, and hand *that* to the outbox.
     *
     * The first version stored `{text, action_class, idempotency_key}`, which is not a
     * command: `CommandRequest` requires `command_id`, `issued_at_unix` and `signature`,
     * so the delegate refuses it as `command_payload_invalid` when the outbox flushes.
     * The owner would have been told their work was saved and it would have been rejected
     * on their behalf hours later — nothing looking wrong until it was too late to redo.
     *
     * Signed here rather than at flush time so that `issued_at_unix` is the moment the
     * owner issued it. Re-signing later would make a day-old instruction look fresh and
     * defeat the Gateway's own stale-intent refusal.
     */
    private fun storeSignedBody(command: VanOwnerCommand, needsReconfirm: Boolean): Boolean {
        val store = storeForLater ?: return false
        val body = runCatching {
            gateway.buildCommandBody(
                text = command.text.trim(),
                actionClass = command.actionClass,
                projectId = command.projectId,
                idempotencyKey = command.idempotencyKey,
                approvalToken = command.approvalToken,
                turnId = command.turnId,
                originChannel = originChannel(command.source),
                expiresAtUnix = command.expiresAtUnix,
                noStaleReplay = command.noStaleReplay,
                speechEvidenceRef = command.speechEvidenceRef,
                speakerEvidenceMilli = command.speakerEvidenceMilli,
            )
        }.getOrNull() ?: return false
        return store(body, needsReconfirm)
    }

    /**
     * §20.15 — work the outbox will not send, surfaced where the owner is already looking.
     *
     * Called by the session when a stored command expires or the session it belonged to
     * is replaced. Without a caller for this, "the owner is told" is an intention.
     */
    fun reportUndelivered(reasons: List<Pair<String, String>>) {
        if (reasons.isEmpty()) return
        _state.update { current ->
            current.copy(
                messages = current.messages + reasons.map { (_, line) ->
                    VanConversationMessage(
                        role = VanMessageRole.SYSTEM,
                        text = line,
                        status = VanCommandStatus.FAILED,
                    )
                },
            )
        }
    }

    private fun originChannel(source: VanCommandSource): String = when (source) {
        VanCommandSource.VOICE -> "VOICE"
        VanCommandSource.CHAT -> "TEXT"
        VanCommandSource.SYSTEM -> "SYSTEM_EVENT"
        else -> "UI"
    }
}
