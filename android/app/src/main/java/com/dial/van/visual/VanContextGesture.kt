package com.dial.van.visual

/** Optional v1 character extension; the original fourteen action codes never move. */
enum class VanContextGesture(
    val code: Int,
    val durationMs: Long,
    val legacyAction: VanFiniteAction,
    val priority: Int,
    val requiresTarget: Boolean = false,
    val requiresVerifiedResult: Boolean = false,
) {
    EXPLAIN_OPEN_PALMS(15, 1_400, VanFiniteAction.ACK_NOD, 45),
    COMPARE_OPTIONS(16, 1_800, VanFiniteAction.ACK_NOD, 50),
    THINK_CHIN(17, 1_500, VanFiniteAction.ACK_NOD, 40),
    INSPECT_TARGET(18, 1_300, VanFiniteAction.POINT_TARGET, 65, requiresTarget = true),
    LISTEN_EMPHASIS(19, 1_000, VanFiniteAction.ACK_NOD, 55),
    POLITE_REFUSAL(20, 1_100, VanFiniteAction.SHRUG, 75),
    ACKNOWLEDGE_ERROR(21, 1_200, VanFiniteAction.CAUTION, 100),
    YIELD_TO_INTERRUPTION(22, 650, VanFiniteAction.CLOSE_PANEL, 90),
    REQUEST_CLARIFICATION(23, 1_300, VanFiniteAction.CAUTION, 80),
    HANDOFF_RESULT(24, 1_500, VanFiniteAction.PRESENT_CARD, 80, requiresVerifiedResult = true),
    RECOVERY_READY(25, 1_000, VanFiniteAction.CONFIRM, 70, requiresVerifiedResult = true),
    GUIDE_NEXT_STEP(26, 1_500, VanFiniteAction.POINT_TARGET, 65, requiresTarget = true);

    fun allows(state: VanDurableState): Boolean = when (this) {
        EXPLAIN_OPEN_PALMS -> state in setOf(VanDurableState.SPEAKING, VanDurableState.WORKING, VanDurableState.ATTENTIVE)
        COMPARE_OPTIONS -> state in setOf(VanDurableState.SPEAKING, VanDurableState.THINKING, VanDurableState.ATTENTIVE, VanDurableState.WORKING)
        THINK_CHIN -> state == VanDurableState.THINKING
        INSPECT_TARGET -> state in setOf(VanDurableState.IDLE, VanDurableState.WORKING, VanDurableState.SEARCHING, VanDurableState.ATTENTIVE, VanDurableState.SPEAKING)
        LISTEN_EMPHASIS -> state == VanDurableState.LISTENING
        POLITE_REFUSAL -> state in setOf(VanDurableState.ATTENTIVE, VanDurableState.WARNING)
        ACKNOWLEDGE_ERROR -> state in setOf(VanDurableState.ERROR, VanDurableState.WARNING)
        YIELD_TO_INTERRUPTION -> state in setOf(VanDurableState.IDLE, VanDurableState.ATTENTIVE, VanDurableState.LISTENING)
        REQUEST_CLARIFICATION -> state in setOf(VanDurableState.WAITING_FOR_OWNER, VanDurableState.ATTENTIVE, VanDurableState.WAITING)
        HANDOFF_RESULT -> state == VanDurableState.SUCCESS
        RECOVERY_READY -> state in setOf(VanDurableState.IDLE, VanDurableState.ATTENTIVE, VanDurableState.WORKING, VanDurableState.SUCCESS)
        GUIDE_NEXT_STEP -> state in setOf(VanDurableState.IDLE, VanDurableState.ATTENTIVE, VanDurableState.WORKING, VanDurableState.WAITING, VanDurableState.SPEAKING)
    }

    companion object {
        fun fromCode(code: Int): VanContextGesture? = entries.firstOrNull { it.code == code }
    }
}
