package com.dial.van.visual

/**
 * Kotlin bindings for [visual-authority/rive_contract.json].
 * Values MUST stay in sync — see [RiveContractTest].
 */
enum class VanDurableState(val code: Int) {
    OFFLINE(0),
    CONNECTING(1),
    IDLE(2),
    ATTENTIVE(3),
    LISTENING(4),
    THINKING(5),
    SEARCHING(6),
    WORKING(7),
    DELEGATING(8),
    SPEAKING(9),
    WAITING(10),
    WAITING_FOR_OWNER(11),
    DEGRADED(12),
    WARNING(13),
    ERROR(14),
    SUCCESS(15),
    URGENT(16),
    SLEEPING(17);

    companion object {
        fun fromCode(code: Int): VanDurableState =
            entries.firstOrNull { it.code == code } ?: IDLE
    }
}

enum class VanFiniteAction(val code: Int) {
    HELLO_WAVE(1),
    ACK_NOD(2),
    POINT_LEFT(3),
    POINT_RIGHT(4),
    POINT_UP(5),
    POINT_DOWN(6),
    POINT_TARGET(7),
    CELEBRATE(8),
    CAUTION(9),
    CONFIRM(10),
    SHRUG(11),
    PRESENT_CARD(12),
    OPEN_PANEL(13),
    CLOSE_PANEL(14);

    companion object {
        fun fromCode(code: Int): VanFiniteAction? =
            entries.firstOrNull { it.code == code }
    }
}

enum class VanTrigger(val wireName: String) {
    POINT("point"),
    ACK("ack"),
    CELEBRATE("celebrate"),
    WARNING("warning"),
    WAVE("wave"),
    SHRUG("shrug"),
    PRESENT("present"),
    PANEL("panel");

    companion object {
        fun fromWireName(name: String): VanTrigger? =
            entries.firstOrNull { it.wireName == name }
    }
}

enum class VanInput(val wireName: String) {
    STATE("state"),
    SPEAKING("speaking"),
    LISTENING("listening"),
    ATTENTION_X("attention_x"),
    ATTENTION_Y("attention_y"),
    MOUTH_OPEN("mouth_open"),
    URGENCY("urgency"),
    VISEME("viseme"),
    ACTION_CODE("action_code");

    companion object {
        fun fromWireName(name: String): VanInput? =
            entries.firstOrNull { it.wireName == name }
    }
}

/** Rive artboard + state machine identifiers from contract. */
object RiveBindingContract {
    const val ARTBOARD = "Van"
    const val STATE_MACHINE = "VanRuntime"
    const val ASSET_FILE = "van.riv"
}

data class VanVisualState(
    val durableState: VanDurableState = VanDurableState.IDLE,
    val speaking: Boolean = false,
    val listening: Boolean = false,
    val attentionX: Float = 0f,
    val attentionY: Float = 0f,
    val mouthOpen: Float = 0f,
    val urgency: Float = 0f,
    val viseme: Int = 0,
    val actionCode: Int = 0,
) {
    fun toRiveInputs(): Map<VanInput, Any> = mapOf(
        VanInput.STATE to durableState.code,
        VanInput.SPEAKING to speaking,
        VanInput.LISTENING to listening,
        VanInput.ATTENTION_X to attentionX.coerceIn(-1f, 1f),
        VanInput.ATTENTION_Y to attentionY.coerceIn(-1f, 1f),
        VanInput.MOUTH_OPEN to mouthOpen.coerceIn(0f, 1f),
        VanInput.URGENCY to urgency.coerceIn(0f, 1f),
        VanInput.VISEME to viseme,
        VanInput.ACTION_CODE to actionCode,
    )
}
