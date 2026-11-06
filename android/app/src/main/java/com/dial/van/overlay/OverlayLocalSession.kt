package com.dial.van.overlay

import com.dial.van.visual.VanDoubleTapAction
import com.dial.van.visual.VanExpressionLevel
import com.dial.van.visual.VanPresentationPreferences
import org.json.JSONObject

/** No captured audio, task results, approvals, tokens or automatic actions are persisted here. */
data class OverlayLocalSession(
    val scope: String,
    val revision: Long = 0,
    val draft: String = "",
    val savedAtMs: Long = 0,
    val mode: String = "CONTEXT",
    val preferences: VanPresentationPreferences = VanPresentationPreferences(),
)

enum class OverlayRecoveryStatus { EMPTY, AVAILABLE, EXPIRED, WRONG_OWNER, INVALID, FUTURE_VERSION }
data class OverlayRecoveredSession(val session: OverlayLocalSession, val status: OverlayRecoveryStatus)

object OverlayLocalSessionCodec {
    const val MAX_DRAFT_CHARS = 16_384
    const val MAX_RECORD_CHARS = 100_000
    const val DRAFT_RETENTION_MS = 7L * 24 * 60 * 60 * 1_000
    private const val FUTURE_TOLERANCE_MS = 5L * 60 * 1_000
    private val SCOPE = Regex("[a-f0-9]{64}")
    private val MODES = setOf("CONTEXT", "CHAT", "VOICE", "TRADES", "SETTINGS")
    fun validScope(scope: String) = scope.matches(SCOPE)

    fun encode(state: OverlayLocalSession): String {
        require(validScope(state.scope))
        require(state.revision in 0..1_000_000_000_000L && state.savedAtMs >= 0)
        require(state.draft.length <= MAX_DRAFT_CHARS)
        require(state.mode in MODES)
        val p = state.preferences.normalized()
        return JSONObject().put("schema", 1).put("scope", state.scope).put("revision", state.revision)
            .put("draft", if (p.rememberDraft) state.draft else "").put("saved_at_ms", state.savedAtMs)
            .put("mode", state.mode).put("preferences", JSONObject().put("expression", p.expression.name)
                .put("reduced_motion", p.reducedMotion).put("idle_opacity", p.idleOpacityPercent)
                .put("remember_draft", p.rememberDraft).put("double_tap", p.doubleTap.name)).toString()
            .also { require(it.length <= MAX_RECORD_CHARS) }
    }

    fun decode(raw: String?, scope: String, nowMs: Long): OverlayRecoveredSession {
        val empty = OverlayLocalSession(scope)
        fun rejected(status: OverlayRecoveryStatus) = OverlayRecoveredSession(empty, status)
        if (!validScope(scope) || nowMs < 0) return rejected(OverlayRecoveryStatus.INVALID)
        if (raw == null) return rejected(OverlayRecoveryStatus.EMPTY)
        if (raw.length > MAX_RECORD_CHARS) return rejected(OverlayRecoveryStatus.INVALID)
        return try {
            val o = JSONObject(raw)
            val schema = o.get("schema")
            if (schema !is Number || schema.toInt().toDouble() != schema.toDouble()) return rejected(OverlayRecoveryStatus.INVALID)
            if (schema.toInt() != 1) return rejected(OverlayRecoveryStatus.FUTURE_VERSION)
            if (o.get("scope") !is String || o.getString("scope") != scope) return rejected(OverlayRecoveryStatus.WRONG_OWNER)
            val revision = integral(o, "revision"); val saved = integral(o, "saved_at_ms")
            if (revision !in 0..1_000_000_000_000L || saved < 0) return rejected(OverlayRecoveryStatus.INVALID)
            val draft = o.get("draft") as? String ?: return rejected(OverlayRecoveryStatus.INVALID)
            if (draft.length > MAX_DRAFT_CHARS) return rejected(OverlayRecoveryStatus.INVALID)
            val mode = (o.get("mode") as? String)?.takeIf { it in MODES } ?: return rejected(OverlayRecoveryStatus.INVALID)
            val p = o.getJSONObject("preferences")
            val preferences = VanPresentationPreferences(
                expression = VanExpressionLevel.valueOf(p.get("expression") as String),
                reducedMotion = p.get("reduced_motion") as Boolean,
                idleOpacityPercent = integral(p, "idle_opacity").takeIf { it in 55L..100L }?.toInt() ?: return rejected(OverlayRecoveryStatus.INVALID),
                rememberDraft = p.get("remember_draft") as Boolean,
                doubleTap = VanDoubleTapAction.valueOf(p.get("double_tap") as String),
            )
            val invalidAge = saved > nowMs && saved - nowMs > FUTURE_TOLERANCE_MS ||
                nowMs >= saved && nowMs - saved > DRAFT_RETENTION_MS
            val recoverable = preferences.rememberDraft && draft.isNotBlank() && !invalidAge
            OverlayRecoveredSession(OverlayLocalSession(scope, revision,
                if (recoverable) draft else "", saved,
                // Startup NEVER begins capture or opens an account/approval operation.
                if (mode == "VOICE" || mode == "SETTINGS") "CONTEXT" else mode, preferences),
                when { invalidAge && draft.isNotBlank() -> OverlayRecoveryStatus.EXPIRED
                    recoverable -> OverlayRecoveryStatus.AVAILABLE
                    else -> OverlayRecoveryStatus.EMPTY })
        } catch (_: Exception) { rejected(OverlayRecoveryStatus.INVALID) }
    }

    private fun integral(o: JSONObject, key: String): Long {
        val value = o.get(key)
        require(value is Number && value.toDouble().isFinite() && value.toLong().toDouble() == value.toDouble())
        return value.toLong()
    }
}

/** Restoring a UI snapshot never reopens the microphone or silently restores focus over another app. */
object OverlayRestartPresentation {
    fun safe(presentation: VanOverlayPresentation): VanOverlayPresentation = when (presentation) {
        VanOverlayPresentation.MINIMIZED, VanOverlayPresentation.DOCKED -> presentation
        else -> VanOverlayPresentation.FULL_FLOATING
    }
}
