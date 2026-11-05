package com.dial.van.visual

/**
 * Presentation-only arbitration for existing finite Rive action codes.
 *
 * Source revisions and event IDs are an anti-replay boundary, not approval authority.
 * The real mission, trade, approval and OS owners still decide what actually happened.
 * No gesture creates a command, authorizes an effect or claims a provider receipt.
 */
enum class VanCueEvidence {
    /** A local UI event actually observed by VAN. */
    LOCAL_UI,
    /** An upstream domain reducer verified the stated result against its original source. */
    VERIFIED_SOURCE,
    /** Unknown, optimistic or externally supplied facts must not produce a success gesture. */
    UNVERIFIED,
}

enum class VanCueOutcome {
    PLAY,
    CLEAR,
    DUPLICATE,
    STALE_REVISION,
    EXPIRED,
    INVALID_SOURCE,
    INVALID_TARGET,
    UNVERIFIED_RESULT,
    CRITICAL_STATE,
    ANTICIPATION_HELD,
    LOWER_PRIORITY_HELD,
}

/**
 * Geometry is deliberately scoped to a known VAN-owned viewport.
 * This cannot authorize inspecting an unrelated Android application.
 */
data class VanCueTarget(
    val leftPx: Float,
    val topPx: Float,
    val rightPx: Float,
    val bottomPx: Float,
    val viewportWidthPx: Float,
    val viewportHeightPx: Float,
    val viewportRevision: Long,
    val expectedRevision: Long,
    val ownedAndVisible: Boolean,
) {
    fun normalizedCenter(): Pair<Float, Float>? {
        if (!ownedAndVisible || viewportRevision != expectedRevision) return null
        val numbers = listOf(leftPx, topPx, rightPx, bottomPx, viewportWidthPx, viewportHeightPx)
        if (numbers.any { !it.isFinite() }) return null
        if (viewportWidthPx <= 0f || viewportHeightPx <= 0f) return null
        if (leftPx < 0f || topPx < 0f || rightPx > viewportWidthPx || bottomPx > viewportHeightPx) return null
        if (rightPx <= leftPx || bottomPx <= topPx) return null
        val x = ((leftPx + rightPx) / viewportWidthPx - 1f).coerceIn(-1f, 1f)
        val y = ((topPx + bottomPx) / viewportHeightPx - 1f).coerceIn(-1f, 1f)
        return x to y
    }
}

data class VanGestureCue(
    val source: String,
    val eventId: String,
    val emittedAtMs: Long,
    val action: VanFiniteAction?,
    val revision: Long? = null,
    val expiresAtMs: Long? = null,
    val evidence: VanCueEvidence = VanCueEvidence.UNVERIFIED,
    val target: VanCueTarget? = null,
)

data class VanGestureDecision(
    val outcome: VanCueOutcome,
    val action: VanFiniteAction? = null,
    val attention: Pair<Float, Float>? = null,
) {
    val accepted: Boolean get() = outcome == VanCueOutcome.PLAY || outcome == VanCueOutcome.CLEAR
}

/**
 * Deterministic, bounded local director. The caller supplies monotonic local time.
 * An old cue is never queued for later replay merely because a higher-priority action won.
 */
class VanGestureDirector(private val recentLimit: Int = 256) {
    private data class Active(
        val action: VanFiniteAction,
        val startedAtMs: Long,
        val endsAtMs: Long,
        val priority: Int,
    )

    private var active: Active? = null
    private val recent = LinkedHashSet<String>()
    private val sourceRevisions = LinkedHashMap<String, Long>()

    fun submit(cue: VanGestureCue, pose: VanDurableState, nowMs: Long): VanGestureDecision {
        if (cue.source.isBlank() || cue.eventId.isBlank()) return VanGestureDecision(VanCueOutcome.INVALID_SOURCE)
        if (cue.expiresAtMs != null && cue.expiresAtMs < cue.emittedAtMs) {
            return VanGestureDecision(VanCueOutcome.EXPIRED)
        }
        if (nowMs < cue.emittedAtMs || (cue.expiresAtMs != null && nowMs > cue.expiresAtMs)) {
            return VanGestureDecision(VanCueOutcome.EXPIRED)
        }

        val key = cue.source + "\u0000" + cue.eventId
        if (key in recent) return VanGestureDecision(VanCueOutcome.DUPLICATE)
        val previousRevision = sourceRevisions[cue.source]
        if (cue.revision != null && previousRevision != null && cue.revision < previousRevision) {
            return VanGestureDecision(VanCueOutcome.STALE_REVISION)
        }
        remember(key)
        if (cue.revision != null) {
            if (previousRevision == null || cue.revision > previousRevision) sourceRevisions[cue.source] = cue.revision
            while (sourceRevisions.size > recentLimit.coerceAtLeast(1)) {
                sourceRevisions.remove(sourceRevisions.keys.first())
            }
        }

        val proposed = cue.action ?: run {
            active = null
            return VanGestureDecision(VanCueOutcome.CLEAR)
        }

        if (proposed in POSITIVE_RESULTS && cue.evidence != VanCueEvidence.VERIFIED_SOURCE) {
            return VanGestureDecision(VanCueOutcome.UNVERIFIED_RESULT)
        }

        if (pose in VanStatePriority.AUTHORITY_HELD) {
            val permissible = when (pose) {
                VanDurableState.URGENT, VanDurableState.ERROR, VanDurableState.WAITING_FOR_OWNER ->
                    proposed == VanFiniteAction.CAUTION
                VanDurableState.WARNING -> proposed == VanFiniteAction.CAUTION || proposed == VanFiniteAction.SHRUG
                else -> false
            }
            if (!permissible) return VanGestureDecision(VanCueOutcome.CRITICAL_STATE)
        }

        val mapped = if (proposed in POINTING) cue.target?.normalizedCenter() else null
        if (proposed in POINTING && mapped == null) return VanGestureDecision(VanCueOutcome.INVALID_TARGET)

        val current = active?.takeIf { nowMs < it.endsAtMs }
        val nextPriority = priority(proposed)
        if (current != null && current.action != proposed) {
            val anticipationEnd = current.startedAtMs + ((current.endsAtMs - current.startedAtMs) * 15 / 100)
            // Critical caution must interrupt immediately; other gestures respect anticipation.
            if (proposed != VanFiniteAction.CAUTION && nowMs < anticipationEnd) {
                return VanGestureDecision(VanCueOutcome.ANTICIPATION_HELD)
            }
            if (nextPriority < current.priority && proposed != VanFiniteAction.CAUTION) {
                return VanGestureDecision(VanCueOutcome.LOWER_PRIORITY_HELD)
            }
        } else if (current?.action == proposed) {
            // Repeating a gesture while it is already playing is not visible expressiveness.
            return VanGestureDecision(VanCueOutcome.DUPLICATE)
        }

        active = Active(
            action = proposed,
            startedAtMs = nowMs,
            endsAtMs = nowMs + VanMotionMap.actionDurationMs(proposed),
            priority = nextPriority,
        )
        return VanGestureDecision(VanCueOutcome.PLAY, proposed, mapped)
    }

    fun activeAt(nowMs: Long): VanFiniteAction? = active?.takeIf { nowMs < it.endsAtMs }?.action

    fun reset() {
        active = null
        recent.clear()
        sourceRevisions.clear()
    }

    private fun remember(key: String) {
        recent.add(key)
        while (recent.size > recentLimit.coerceAtLeast(1)) recent.remove(recent.first())
    }

    private fun priority(action: VanFiniteAction): Int = when (action) {
        VanFiniteAction.CAUTION -> 100
        VanFiniteAction.CONFIRM, VanFiniteAction.PRESENT_CARD -> 80
        VanFiniteAction.SHRUG -> 75
        VanFiniteAction.POINT_LEFT, VanFiniteAction.POINT_RIGHT, VanFiniteAction.POINT_UP,
        VanFiniteAction.POINT_DOWN, VanFiniteAction.POINT_TARGET -> 65
        VanFiniteAction.OPEN_PANEL, VanFiniteAction.CLOSE_PANEL -> 60
        VanFiniteAction.ACK_NOD -> 50
        VanFiniteAction.CELEBRATE -> 45
        VanFiniteAction.HELLO_WAVE -> 25
    }

    private companion object {
        val POINTING = setOf(
            VanFiniteAction.POINT_LEFT, VanFiniteAction.POINT_RIGHT,
            VanFiniteAction.POINT_UP, VanFiniteAction.POINT_DOWN, VanFiniteAction.POINT_TARGET,
        )
        val POSITIVE_RESULTS = setOf(
            VanFiniteAction.CONFIRM, VanFiniteAction.PRESENT_CARD, VanFiniteAction.CELEBRATE,
        )
    }
}


/** Local, VAN-owned pointer coordinates only; never external-screen inspection. */
object VanPointerGaze {
    fun fromLocal(
        xPx: Float, yPx: Float, widthPx: Float, heightPx: Float,
    ): Pair<Float, Float>? {
        if (!xPx.isFinite() || !yPx.isFinite() || !widthPx.isFinite() || !heightPx.isFinite()) return null
        if (widthPx <= 0f || heightPx <= 0f) return null
        if (xPx < 0f || yPx < 0f || xPx > widthPx || yPx > heightPx) return null
        return (xPx * 2f / widthPx - 1f).coerceIn(-1f, 1f) to
            (yPx * 2f / heightPx - 1f).coerceIn(-1f, 1f)
    }
}
