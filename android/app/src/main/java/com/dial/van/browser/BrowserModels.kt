package com.dial.van.browser

import org.json.JSONObject

/**
 * Rev 1.5 §§5.1, 5.2, 27 — the browser read models, and what the owner is allowed to
 * conclude from them.
 *
 * The rule carried over from `P0-EXEC-003` and restated by §5.2: **a session state is not a
 * work outcome.** `INTERACTIVE` means pixels are flowing, not that anything the owner asked
 * for has happened, and no screen may infer completion from it. The gateway says so
 * explicitly in `is_work_outcome`, and [BrowserSessionSnapshot.isWorkOutcome] keeps that
 * answer rather than deriving a cheerier one.
 *
 * Unknown states read as unknown. A build that meets a state it does not recognise says so
 * instead of falling back to something that looks like working — the same defect the
 * mission surface had.
 */
enum class BrowserSessionState {
    REQUESTED,
    AUTHORIZED,
    ALLOCATING,
    SIGNALING,
    CONNECTING,
    INTERACTIVE,
    AGENT_CONTROLLED,
    RECONNECTING,
    SUSPENDED,
    TERMINATING,
    TERMINATED,
    FAILED,
    UNKNOWN;

    val isTerminal: Boolean
        get() = this == TERMINATED || this == FAILED

    /** Whether the owner's touches can reach the page at all right now. */
    val acceptsInput: Boolean
        get() = this == INTERACTIVE || this == AGENT_CONTROLLED

    companion object {
        fun from(raw: String?): BrowserSessionState =
            entries.firstOrNull { it.name == raw } ?: UNKNOWN
    }
}

enum class BrowserControlHolder {
    OWNER,
    HERMES_DETERMINISTIC,
    HERMES_STAGEHAND,
    SYSTEM_RECOVERY,
    NONE,
    UNKNOWN;

    val isAgent: Boolean
        get() = this == HERMES_DETERMINISTIC || this == HERMES_STAGEHAND

    companion object {
        fun from(raw: String?): BrowserControlHolder =
            entries.firstOrNull { it.name == raw } ?: UNKNOWN
    }
}

data class BrowserViewport(
    val width: Int,
    val height: Int,
    val deviceScaleFactor: Float,
    val revision: Int,
)

data class BrowserSessionSnapshot(
    val sessionId: String,
    val state: BrowserSessionState,
    val profileAlias: String,
    val viewport: BrowserViewport,
    val ackedViewportRevision: Int?,
    val controlHolder: BrowserControlHolder,
    val controlLeaseId: String?,
    val controlGeneration: Int,
    val activeTargetId: String?,
    val missionId: String?,
    val isWorkOutcome: Boolean,
    val ownerReadableStateFromGateway: String?,
) {
    /**
     * §8.1 — the client withholds actuation until the layout it is showing is acknowledged.
     *
     * Kept here rather than in the input encoder because it is a fact about the session, and
     * a rule enforced in the place that sends bytes is a rule that moves when the sending
     * code is refactored.
     */
    val mayActuate: Boolean
        get() = state.acceptsInput &&
            controlHolder == BrowserControlHolder.OWNER &&
            ackedViewportRevision == viewport.revision

    /**
     * The half of [mayActuate] the surface has to be able to name separately.
     *
     * "VAN is driving" and "the layout is mid-resize" both stop input, and telling the
     * owner the wrong one of those is how a two-second resize looks like a broken session.
     */
    val viewportUnacknowledged: Boolean
        get() = ackedViewportRevision != viewport.revision

    /** What the owner sees. Never an enum, and never a guess dressed as a status. */
    val ownerReadableState: String
        get() = ownerReadableStateFromGateway ?: when (state) {
            BrowserSessionState.INTERACTIVE -> "Ready"
            BrowserSessionState.AGENT_CONTROLLED -> "Van is driving"
            BrowserSessionState.RECONNECTING -> "Reconnecting"
            BrowserSessionState.SUSPENDED -> "Paused"
            BrowserSessionState.TERMINATED -> "Closed"
            BrowserSessionState.FAILED -> "Stopped"
            BrowserSessionState.UNKNOWN -> "Van cannot tell what this session is doing"
            else -> "Connecting"
        }
}

object BrowserParsing {

    fun session(json: JSONObject): BrowserSessionSnapshot {
        val viewport = json.optJSONObject("viewport")
        return BrowserSessionSnapshot(
            sessionId = json.getString("session_id"),
            state = BrowserSessionState.from(json.optString("state", null)),
            profileAlias = json.optString("profile_alias", ""),
            viewport = BrowserViewport(
                width = viewport?.optInt("width", 0) ?: 0,
                height = viewport?.optInt("height", 0) ?: 0,
                deviceScaleFactor = (viewport?.optDouble("device_scale_factor", 1.0) ?: 1.0).toFloat(),
                revision = viewport?.optInt("revision", 1) ?: 1,
            ),
            ackedViewportRevision =
                if (json.isNull("acked_viewport_revision")) null
                else json.optInt("acked_viewport_revision"),
            controlHolder = BrowserControlHolder.from(json.optString("control_holder", null)),
            controlLeaseId = json.optStringOrNullBrowser("control_lease_id"),
            controlGeneration = json.optInt("control_generation", 0),
            activeTargetId = json.optStringOrNullBrowser("active_target_id"),
            missionId = json.optStringOrNullBrowser("mission_id"),
            // §5.2 — the gateway states this; the device does not infer it. An older
            // gateway that omits it is treated as "not an outcome", which is the safe
            // direction: the alternative is a screen calling a live session finished.
            isWorkOutcome = json.optBoolean("is_work_outcome", false),
            ownerReadableStateFromGateway = json.optStringOrNullBrowser("owner_readable_state"),
        )
    }

    fun streamGrant(json: JSONObject): BrowserStreamGrant = BrowserStreamGrant(
        sessionId = json.getString("session_id"),
        token = json.getString("stream_grant"),
        signalUrl = json.getString("signal_url"),
        expiresAtMs = json.optLong("expires_at_ms", 0L),
        iceServers = (0 until (json.optJSONArray("ice_servers")?.length() ?: 0)).map { index ->
            val entry = json.getJSONArray("ice_servers").getJSONObject(index)
            BrowserIceServer(
                urls = (0 until (entry.optJSONArray("urls")?.length() ?: 0)).map {
                    entry.getJSONArray("urls").getString(it)
                },
                username = entry.optStringOrNullBrowser("username"),
                credential = entry.optStringOrNullBrowser("credential"),
            )
        },
    )
}

data class BrowserIceServer(
    val urls: List<String>,
    val username: String?,
    val credential: String?,
)

data class BrowserStreamGrant(
    val sessionId: String,
    val token: String,
    val signalUrl: String,
    val expiresAtMs: Long,
    val iceServers: List<BrowserIceServer>,
) {
    fun usableAt(nowMs: Long): Boolean = nowMs < expiresAtMs
}

/**
 * §0D.1 / §27.2 — the three window classes the browser chrome responds to.
 *
 * Samsung pop-up view can be narrower than any phone in portrait, so "compact" is not the
 * same question as "is this a phone". The width is what decides, because that is what the
 * owner is actually looking at.
 */
enum class BrowserWindowClass {
    COMPACT,
    MEDIUM,
    EXPANDED;

    companion object {
        fun forWidthDp(widthDp: Int): BrowserWindowClass = when {
            widthDp < 600 -> COMPACT
            widthDp < 840 -> MEDIUM
            else -> EXPANDED
        }
    }
}

internal fun JSONObject.optStringOrNullBrowser(key: String): String? =
    if (isNull(key)) null else optString(key, "").ifEmpty { null }
