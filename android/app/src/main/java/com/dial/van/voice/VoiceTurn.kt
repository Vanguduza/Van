package com.dial.van.voice

/**
 * Rev 1.5 §§21.11, 21.12, 21.23, 21.26 — a voice turn, from the wake word to the answer.
 *
 * Three separate things live here because they are the three places a voice assistant lies
 * to its owner if it is careless:
 *
 *  * **turn identity** (§21.12). A failover keeps the same `turnId` and `commandId`. Minting
 *    new ones on reconnect is how one spoken instruction becomes two executions, and the
 *    owner never sees the second one coming;
 *  * **offline classification** (§21.11). Before VAN knows whether Hermes is reachable, it
 *    decides what *kind* of request this is. The classifier is deterministic routing and
 *    not an agent — it never answers, it only says who should;
 *  * **the success contract** (§21.26). `RESPONSE_RECEIVED` is not proof the owner heard
 *    the response. Input and output states are kept separate so nothing can collapse
 *    "Hermes replied" into "VAN answered you".
 */

/** §21.23 — the state machine. Transport state is orthogonal and deliberately absent. */
enum class VoiceState {
    IDLE,
    WAKE_DETECTED,
    ACK_PLAYING,
    LISTENING,
    FINALIZING_ASR,
    ROUTING,
    LOCAL_EXECUTING,
    REMOTE_SUBMITTING,
    QUEUED_OFFLINE,
    WAITING_FOR_RESPONSE,
    RESPONSE_STREAMING,
    SPEAKING,
    BARGED_IN;

    /**
     * §21.23 — `SPEAKING` may continue through a failover.
     *
     * Stated as a property because the tempting implementation is to stop speech when the
     * transport wobbles, and that is precisely wrong: the segments are already local, and
     * cutting the owner off mid-sentence to report a network event is worse than the event.
     */
    val survivesTransportFailover: Boolean
        get() = this == SPEAKING || this == LOCAL_EXECUTING || this == IDLE
}

/** §21.26 — what happened on the way in. Distinct states, never collapsed. */
enum class VoiceInputOutcome {
    WAKE_DETECTED,
    ACK_PLAYED,
    ASR_LISTENING,
    ASR_FINAL,
    COMMAND_QUEUED,
    COMMAND_SUBMITTED,
    COMMAND_ACCEPTED,
}

/** §21.26 — and on the way out. `RESPONSE_RECEIVED` is not `TTS_COMPLETED`. */
enum class VoiceOutputOutcome {
    RESPONSE_RECEIVED,
    SPEECH_SEGMENT_RECEIVED,
    TTS_SYNTHESIZED,
    TTS_STARTED,
    TTS_COMPLETED,
    OWNER_INTERRUPTED,
    TTS_FAILED;

    /**
     * The only outcome that means the owner actually heard it.
     *
     * `OWNER_INTERRUPTED` is deliberately not here: the owner heard *some* of it, and
     * counting a barge-in as a delivered answer is how a system reports success for a
     * sentence nobody finished listening to.
     */
    val ownerHeardTheWholeAnswer: Boolean
        get() = this == TTS_COMPLETED
}

/**
 * §21.12 — the identity a turn keeps for its whole life, across every transport it uses.
 */
data class VoiceTurn(
    val turnId: String,
    val wakeSessionId: String,
    val transcriptRevision: Int = 0,
    val commandId: String? = null,
    val originChannel: String = ORIGIN_VOICE,
) {
    /**
     * A resubmission after a failover. The identity is preserved and only the transcript
     * revision may move, because a second-pass ASR result is a better reading of the same
     * utterance rather than a new one.
     */
    fun withRevisedTranscript(): VoiceTurn = copy(transcriptRevision = transcriptRevision + 1)

    fun submittedAs(commandId: String): VoiceTurn = copy(commandId = commandId)

    companion object {
        const val ORIGIN_VOICE = "VOICE"
    }
}

/** §21.11 — where a request has to go, decided before VAN knows whether it can get there. */
enum class CommandRouting {
    /** VAN can do this on the phone with no network at all. */
    LOCAL_EXECUTABLE,

    /** Needs Hermes. Queuing is allowed only where freshness policy permits. */
    REMOTE_REQUIRED,

    /** Better remotely, answerable locally when there is no path. */
    REMOTE_OPTIONAL,

    /** Irreversible or authority-bearing. Never silently deferred. */
    OWNER_APPROVAL_REQUIRED,
}

/**
 * §21.11 — deterministic routing, not an agent.
 *
 * The classifier never answers a question and never decides whether something is *safe*.
 * It decides who is capable of answering, and the one rule it must not get wrong is the
 * last one: an irreversible request must not be classified as ordinary work and queued,
 * because a queue that flushes an hour later would then perform it.
 */
object OfflineCommandClassifier {

    /** Things VAN does on the phone. Deliberately a short, closed list. */
    private val LOCAL_VERBS = listOf(
        "repeat", "say that again", "read that back",
        "open van browser", "open the browser", "open browser",
        "stop", "cancel that", "never mind",
        "what did you say", "louder", "quieter",
        "what time", "battery",
    )

    /** Things that cannot be answered without reaching the world. */
    private val REMOTE_VERBS = listOf(
        "search", "look up", "google", "browse", "find out",
        "what is the latest", "news", "weather", "price of",
        "email", "calendar", "schedule", "remind me",
    )

    /**
     * Things that change something outside VAN. Matched before anything else.
     *
     * A false positive here costs the owner a confirmation prompt. A false negative queues
     * an irreversible action and performs it later without them, which is the failure
     * §20.14 and this list both exist to prevent — so the list is deliberately broad and
     * the tie is broken towards asking.
     */
    private val APPROVAL_VERBS = listOf(
        "send", "delete", "remove", "pay", "transfer", "buy", "sell",
        "execute", "deploy", "publish", "post", "reply", "confirm",
        "approve", "cancel the order", "close the position", "withdraw",
    )

    fun classify(transcript: String, actionClass: String? = null): CommandRouting {
        val text = transcript.lowercase().trim()

        // The action class is authoritative when the Gateway has already assigned one: it
        // knows what the command actually does, and a phrase match is a guess about that.
        if (actionClass == "A4" || actionClass == "A5") return CommandRouting.OWNER_APPROVAL_REQUIRED

        if (APPROVAL_VERBS.any { text.startsWith(it) || text.contains(" $it ") }) {
            return CommandRouting.OWNER_APPROVAL_REQUIRED
        }
        if (LOCAL_VERBS.any { text.startsWith(it) || text == it }) {
            return CommandRouting.LOCAL_EXECUTABLE
        }
        if (REMOTE_VERBS.any { text.contains(it) }) return CommandRouting.REMOTE_REQUIRED

        // The honest default. An unrecognised request is not local work: VAN does not know
        // what it is, and guessing "I can do that here" produces a confident wrong answer
        // with no network to correct it.
        return CommandRouting.REMOTE_OPTIONAL
    }

    /**
     * §21.24 — what VAN says when it cannot reach Hermes, per routing.
     *
     * VAN must not fabricate a remote answer. Each of these is a true sentence about VAN's
     * own state rather than an attempt to be helpful about the question.
     */
    fun offlineSentence(routing: CommandRouting): String = when (routing) {
        CommandRouting.LOCAL_EXECUTABLE -> ""
        CommandRouting.REMOTE_REQUIRED ->
            "I can't reach Hermes right now, so I can't answer that yet."
        CommandRouting.REMOTE_OPTIONAL ->
            "I can't reach Hermes right now. I'll answer when I can."
        CommandRouting.OWNER_APPROVAL_REQUIRED ->
            "That needs your approval and I can't reach Hermes to set it up."
    }

    /**
     * Whether a request may be held for later at all (§20.14 in voice's terms).
     *
     * Approval-bearing work is never queued. The queue flushing an hour later would
     * perform it, and the owner would not be there.
     */
    fun mayQueueOffline(routing: CommandRouting): Boolean =
        routing == CommandRouting.REMOTE_REQUIRED || routing == CommandRouting.REMOTE_OPTIONAL
}
