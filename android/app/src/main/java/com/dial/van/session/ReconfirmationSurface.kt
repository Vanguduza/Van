package com.dial.van.session

import org.json.JSONObject

/**
 * Rev 1.5 §20.15 — the owner-facing projection of work that VAN is deliberately
 * refusing to replay until the owner says yes again.
 *
 * This is a projection, not a second queue. The authoritative entry remains [OutboxEntry]
 * and the signed command remains inside the encrypted session outbox. The screen gets only
 * the fields required to make an informed choice: what the command says, when it was
 * queued, when it expires, and the stable identities needed to act on exactly that item.
 */
data class OwnerReconfirmationRequest(
    val messageId: String,
    val commandId: String,
    val commandText: String,
    val actionClass: String,
    val queuedAtMs: Long,
    val expiresAtMs: Long,
    val ownerReadableState: String,
)

object OwnerReconfirmationSurface {
    private const val MAX_OWNER_PREVIEW = 280

    /**
     * Project one queued envelope only when [DurableOutbox] says it is waiting for the
     * owner. A safe-to-retry item is not shown as a question, and an expired item is not
     * offered for resurrection.
     */
    fun project(
        entry: OutboxEntry,
        envelope: JSONObject,
        nowMs: Long,
    ): OwnerReconfirmationRequest? {
        if (DurableOutbox.flush(entry, nowMs) !is FlushVerdict.NeedsReconfirmation) {
            return null
        }
        val text = envelope.optJSONObject("payload")
            ?.optString("text")
            .orEmpty()
            .trim()
            .take(MAX_OWNER_PREVIEW)
            .ifBlank { "Queued command ${entry.commandId.takeLast(8)}" }
        return OwnerReconfirmationRequest(
            messageId = entry.messageId,
            commandId = entry.commandId,
            commandText = text,
            actionClass = entry.actionClass,
            queuedAtMs = entry.createdAtMs,
            expiresAtMs = entry.expiresAtMs,
            ownerReadableState = DurableOutbox.ownerReadableState(entry, nowMs),
        )
    }

    /**
     * Reconfirmation is valid only for an item that currently needs it.
     *
     * This prevents an arbitrary UI caller from stamping an ordinary queued command as
     * owner-reconfirmed, and it also prevents an expired item being revived by a late tap.
     */
    fun reconfirm(entry: OutboxEntry, nowMs: Long): OutboxEntry? =
        if (DurableOutbox.flush(entry, nowMs) is FlushVerdict.NeedsReconfirmation) {
            DurableOutbox.reconfirm(entry, nowMs)
        } else {
            null
        }
}
