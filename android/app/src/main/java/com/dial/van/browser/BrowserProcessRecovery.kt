package com.dial.van.browser

/**
 * Rev 1.5 §29.10, §29.11 and ADR-RB-022 — what survives the phone's process being killed,
 * and what must not be believed afterwards.
 *
 * §29.10's last step is the whole of it: **never trust cached completion state over
 * Gateway truth.** An Android process that was killed while a browser task was running
 * comes back holding a snapshot that says the task was running. The snapshot is what the
 * phone last saw, not what happened — the work may have finished, failed, or been taken
 * over by the owner on another device — and a VAN that told its owner "still working" from
 * that snapshot would be reporting a state it has no evidence for.
 *
 * So restoration produces a *claim*, never a conclusion, and every field that says
 * anything about an outcome is dropped rather than restored. The session id, the cursors
 * and the viewport are restored because they are references and positions, not verdicts.
 *
 * ADR-RB-022 is the same idea one level up: a window resize is not a process death and
 * neither is an Activity recreation. The long-lived objects live outside the Activity, so
 * the only thing that rebuilds is the renderer attachment.
 *
 * Pure. The Keystore read, the SharedPreferences and the Gateway call belong to the app;
 * what may be believed belongs here.
 */

/** §29.10 step 1 — what VAN writes down before it can be killed. */
data class PersistedBrowserSession(
    val sessionId: String,
    val profileAlias: String,
    val lastViewportRevision: Int,
    val lastEventCursor: Long,
    val lastSpokenSegment: Int,
    val persistedAtMs: Long,
    /**
     * What the phone last saw. Deliberately named as a belief rather than as a state:
     * whoever reads it has to decide what it is worth, and a field called `state` invites
     * them not to.
     */
    val lastObservedState: String,
    val lastObservedControlGeneration: Int,
)

/** What a restored session may be used for before the Gateway has spoken. */
enum class RestoreDisposition {
    /** Nothing was persisted, or it is too old to be about the same session. */
    NOTHING_TO_RESTORE,

    /**
     * Restored as a claim. The session id and cursors may be used to *ask*; nothing in it
     * may be shown to the owner as the current state.
     */
    RESUMABLE_PENDING_GATEWAY,

    /** The Gateway said this session is gone. The record is dropped. */
    GATEWAY_SAYS_GONE,

    /** The Gateway confirmed it, and only now is any of it true. */
    CONFIRMED_BY_GATEWAY,
}

data class RestoredBrowserSession(
    val disposition: RestoreDisposition,
    val sessionId: String? = null,
    val profileAlias: String? = null,
    val resumeEventCursor: Long = 0,
    val resumeSpeechSegment: Int = 0,
    /**
     * Always null before [RestoreDisposition.CONFIRMED_BY_GATEWAY]. The type allows it
     * only so the confirmed case has somewhere to put the Gateway's answer.
     */
    val ownerVisibleState: String? = null,
)

object BrowserProcessRecovery {

    /**
     * Past this, a persisted session is not about the session the owner remembers.
     *
     * Interactive sessions expire server-side; a record older than that describes
     * something that no longer exists, and asking about it produces a refusal that reads
     * to the owner as an error rather than as time passing.
     */
    const val MAX_AGE_MS = 6 * 60 * 60 * 1000L

    /**
     * §29.10 steps 1-3. Restores references, never verdicts.
     *
     * The returned value has no owner-visible state on purpose: there is no argument that
     * would let a caller ask for one, so the "still working" a stale snapshot would have
     * produced is not reachable from here.
     */
    fun restore(persisted: PersistedBrowserSession?, nowMs: Long): RestoredBrowserSession {
        if (persisted == null) {
            return RestoredBrowserSession(RestoreDisposition.NOTHING_TO_RESTORE)
        }
        if (nowMs - persisted.persistedAtMs >= MAX_AGE_MS) {
            return RestoredBrowserSession(RestoreDisposition.NOTHING_TO_RESTORE)
        }
        // A clock that moved backwards across the restart. The record is not necessarily
        // wrong, but its age cannot be reasoned about, so it is treated as a reference
        // rather than discarded: asking the Gateway costs one call and is always correct.
        return RestoredBrowserSession(
            disposition = RestoreDisposition.RESUMABLE_PENDING_GATEWAY,
            sessionId = persisted.sessionId,
            profileAlias = persisted.profileAlias,
            // §21.16's rule, carried across a process death: resume from what was
            // *spoken*, not from what arrived, or the answer develops a hole nobody sees.
            resumeEventCursor = persisted.lastEventCursor,
            resumeSpeechSegment = persisted.lastSpokenSegment,
            ownerVisibleState = null,
        )
    }

    /**
     * §29.10 step 6 — the Gateway answered, and its answer is the only one that counts.
     *
     * Note what this does not take: the persisted record. A reconciliation that could see
     * the cached state could prefer it, and the one case where it would matter is the one
     * where the cache is wrong.
     */
    fun reconcile(
        restored: RestoredBrowserSession,
        gatewaySaysResumable: Boolean,
        gatewayState: String?,
    ): RestoredBrowserSession {
        if (restored.disposition != RestoreDisposition.RESUMABLE_PENDING_GATEWAY) {
            return restored
        }
        if (!gatewaySaysResumable) {
            return RestoredBrowserSession(RestoreDisposition.GATEWAY_SAYS_GONE)
        }
        return restored.copy(
            disposition = RestoreDisposition.CONFIRMED_BY_GATEWAY,
            ownerVisibleState = gatewayState,
        )
    }

    /**
     * §29.11 / §29.8 — the media plane reconnects separately, and only after the session
     * is confirmed.
     *
     * Reconnecting first would mean negotiating WebRTC against a grant for a session the
     * Gateway has already ended, which fails in a way that looks like a network problem
     * and is not.
     */
    fun mayReconnectMedia(restored: RestoredBrowserSession): Boolean =
        restored.disposition == RestoreDisposition.CONFIRMED_BY_GATEWAY

    /**
     * ADR-RB-022 — what an Activity being recreated is allowed to rebuild.
     *
     * A resize, a split-screen transition, a pop-up conversion and a rotation all destroy
     * and recreate the Activity. None of them is a reason to rebuild a remote Chromium
     * session, and a browser that restarted navigation on rotation would lose the page the
     * owner was reading because they turned the phone.
     */
    val ACTIVITY_OWNS = setOf(
        "renderer attachment",
        "window metrics",
        "local chrome",
    )

    /** ADR-RB-022's other list: these outlive the Activity and are never rebuilt by it. */
    val OUTLIVES_THE_ACTIVITY = setOf(
        "BrowserSessionRepository",
        "BrowserMediaSessionManager",
        "VanPeerConnectionClient",
        "control/session cursors",
    )

    fun rebuiltOnActivityRecreation(component: String): Boolean = component in ACTIVITY_OWNS
}
