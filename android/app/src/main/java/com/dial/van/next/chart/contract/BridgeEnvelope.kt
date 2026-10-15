package com.dial.van.next.chart.contract

/**
 * The message envelope for any chart renderer running outside the app's trust boundary,
 * such as a web engine in a WebView (§7.8.3, REA-VAN-004). The native engine in this
 * package does not need it; it exists so that adopting a web renderer later cannot weaken
 * the rules.
 *
 * Deny by default: unknown schema, wrong origin or session, replayed or out-of-order
 * sequence, expired message, oversized payload, unknown or forbidden capability, or any
 * claimed authority effect other than NONE — each is rejected with a named reason.
 */
data class BridgeEnvelope(
    val schema: String,
    val sessionId: String,
    val messageId: String,
    val seq: Long,
    val createdAtMs: Long,
    val expiresAtMs: Long,
    val origin: String,
    val capability: String,
    val payloadBytes: Int,
    val authorityEffect: String,
)

sealed interface BridgeVerdict {
    data class Accepted(val capability: Capability) : BridgeVerdict
    data class Rejected(val reason: String) : BridgeVerdict
}

class BridgeGate(
    private val sessionId: String,
    private val allowedOrigin: String,
    private val allowed: Set<Capability>,
    private val maxPayloadBytes: Int = 64 * 1024,
    private val maxLifetimeMs: Long = 10_000,
) {
    private var lastSeq = -1L
    private val seen = LinkedHashSet<String>()

    fun check(e: BridgeEnvelope, nowMs: Long): BridgeVerdict {
        fun no(r: String) = BridgeVerdict.Rejected(r)
        if (e.schema != SCHEMA) return no("unknown schema ${e.schema}")
        if (e.origin != allowedOrigin) return no("origin not allowed")
        if (e.sessionId != sessionId) return no("wrong session")
        if (e.authorityEffect != "NONE") return no("authority effect must be NONE")
        if (e.capability in Capability.FORBIDDEN) return no("forbidden capability ${e.capability}")
        val cap = Capability.of(e.capability) ?: return no("unknown capability ${e.capability}")
        if (cap !in allowed) return no("capability not granted ${e.capability}")
        if (e.payloadBytes < 0 || e.payloadBytes > maxPayloadBytes) return no("payload too large")
        if (e.expiresAtMs <= e.createdAtMs || e.expiresAtMs - e.createdAtMs > maxLifetimeMs) return no("bad lifetime")
        if (nowMs >= e.expiresAtMs) return no("expired")
        if (e.messageId in seen) return no("replayed message")
        if (e.seq <= lastSeq) return no("sequence not increasing")
        lastSeq = e.seq
        seen += e.messageId
        if (seen.size > 4096) seen.remove(seen.first())
        return BridgeVerdict.Accepted(cap)
    }

    companion object { const val SCHEMA = "van.chart.bridge.v1" }
}
