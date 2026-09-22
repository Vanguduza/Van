package com.dial.van.visual

/**
 * GAP-F-012 — the real runtime event that produces each durable state and finite action.
 *
 * This is a registry, not a dispatcher: it names, in one place, why every value on
 * [VanDurableState] and [VanFiniteAction] is reachable from something that actually happens
 * on the device, so the property the original audit found broken — an aura family, a
 * frame-budget signal, a whole animation clock with no caller anywhere — cannot recur
 * silently. `VanEvidenceMatrix`'s completeness test in `android/visual-preview` asserts both
 * maps below are total over their enums; a state or action added without an entry here fails
 * that test rather than shipping unreachable.
 *
 * Not every listed producer lives in [VanEmbodimentReducer]. Several predate it — a gateway
 * health poll, an ASR callback, a trade classification — and are named here as documentation
 * of where to look, not as a claim that this file calls them. Pure and dependency-free (only
 * [VanDurableState]/[VanFiniteAction] from `RiveContract.kt`) so it compiles into the app,
 * `android/verification` and `android/visual-preview` alike.
 */
object VanEmbodimentProducers {

    val STATES: Map<VanDurableState, String> = mapOf(
        VanDurableState.OFFLINE to
            "gateway/hermes uplink unreachable (VanApplication.refreshGatewayHealth, " +
            "DeviceSignals -> DegradedModeStore -> VanPresence.cue)",
        VanDurableState.CONNECTING to
            "session handshake starting (VanEmbodimentReducer.forSessionHandshake, " +
            "VanHermesSessionManager.start)",
        VanDurableState.IDLE to
            "owner turn settled with nothing outstanding (VanLiveVisualState.settleToIdle)",
        VanDurableState.ATTENTIVE to
            "overlay tap / command bar focus, or capture ending with nothing said " +
            "(VanPresenceReducer.listeningEnded, VanOverlayInteraction)",
        VanDurableState.LISTENING to
            "microphone capture started (VoiceInputManager.onListeningChanged -> " +
            "VanLiveVisualState.listeningStarted)",
        VanDurableState.THINKING to
            "final transcript received with text (VanLiveVisualState.finalTranscript)",
        VanDurableState.SEARCHING to
            "mission activity.started for a research/browser activity " +
            "(VanEmbodimentReducer.forMissionEvent)",
        VanDurableState.WORKING to
            "gateway command accepted, or mission running with no Hermes run id " +
            "(VanLiveVisualState.dispatchAccepted, VanEmbodimentReducer.forMissionEvent)",
        VanDurableState.DELEGATING to
            "gateway command dispatch started, or mission running with a Hermes run id " +
            "(VanLiveVisualState.dispatchStarted, VanEmbodimentReducer.forMissionEvent)",
        VanDurableState.SPEAKING to
            "text-to-speech started (TtsOutputManager.onStart -> VanLiveVisualState.speakingStarted)",
        VanDurableState.WAITING to
            "mission.waiting_external — VanEmbodimentReducer.forMissionEvent(stateHint) " +
            "(backend mission gap: WAITING_EXTERNAL is not yet in mission/models.py's " +
            "EVENT_FOR_STATE, so this producer is wired ahead of the event existing — see report)",
        VanDurableState.WAITING_FOR_OWNER to
            "command approval_required, mission.waiting_owner, or a halted trade " +
            "(VanLiveVisualState.waitingForOwner, VanEmbodimentReducer.forMissionEvent, " +
            "VanTradeSemantics.durableStateFor)",
        VanDurableState.DEGRADED to
            "a broken subsystem, or an unreadable/stale trading ledger " +
            "(VanPresence.cue via DegradedModeStore, VanTradeSemantics.durableStateFor)",
        VanDurableState.WARNING to
            "command degraded/UNVERIFIABLE/PARTIAL_SUCCESS response, or trade RISK/STOP " +
            "(VanLiveVisualState.warning, VanTradeSemantics.durableStateFor)",
        VanDurableState.ERROR to
            "command denied/failed response, or local ASR error " +
            "(VanLiveVisualState.warning path from VanGatewayClient, VoiceInputManager.onError)",
        VanDurableState.SUCCESS to
            "command VERIFIED_SUCCESS response, or mission.completed " +
            "(VanLiveVisualState.transition(SUCCESS), VanEmbodimentReducer.forMissionEvent)",
        VanDurableState.URGENT to
            "attention.upserted with severity URGENT " +
            "(VanEmbodimentReducer.forAttentionEvent -> VanLiveVisualState.urgent)",
        VanDurableState.SLEEPING to
            "quiet hours in force with no open attention item " +
            "(VanEmbodimentReducer.forQuietHours, NotificationPolicyStore.isQuietNow)",
    )

    val ACTIONS: Map<VanFiniteAction, String> = mapOf(
        VanFiniteAction.HELLO_WAVE to
            "first session opened today (VanEmbodimentReducer.forFirstSessionOfDay, " +
            "persisted day marker)",
        VanFiniteAction.ACK_NOD to
            "gateway command accepted (VanLiveVisualState.dispatchAccepted)",
        VanFiniteAction.POINT_LEFT to
            "expanded overlay highlights a card to the left (VanEmbodimentReducer.forCardHighlight)",
        VanFiniteAction.POINT_RIGHT to
            "expanded overlay highlights a card to the right (VanEmbodimentReducer.forCardHighlight)",
        VanFiniteAction.POINT_UP to
            "expanded overlay highlights a card above (VanEmbodimentReducer.forCardHighlight)",
        VanFiniteAction.POINT_DOWN to
            "expanded overlay highlights a card below (VanEmbodimentReducer.forCardHighlight)",
        VanFiniteAction.POINT_TARGET to
            "expanded overlay highlights the focal card (VanEmbodimentReducer.forCardHighlight)",
        VanFiniteAction.CELEBRATE to
            "trading.trade.closed with quadrant GOOD_DECISION_GOOD_OUTCOME " +
            "(VanEmbodimentReducer.forTradingEvent, guarded on the field's presence — " +
            "no producer emits this event type yet; see report)",
        VanFiniteAction.CAUTION to
            "mission.waiting_owner, command approval_required, or attention URGENT " +
            "(VanEmbodimentReducer.forMissionEvent/forAttentionEvent, VanLiveVisualState.waitingForOwner)",
        VanFiniteAction.CONFIRM to
            "gateway command VERIFIED_SUCCESS response (VanLiveVisualState.transition(SUCCESS))",
        VanFiniteAction.SHRUG to
            "command degraded/UNVERIFIABLE/PARTIAL_SUCCESS response, or a mission completing " +
            "unverifiable (VanLiveVisualState.warning, VanEmbodimentReducer.forMissionEvent)",
        VanFiniteAction.PRESENT_CARD to
            "mission.completed — a result summary is ready (VanEmbodimentReducer.forMissionEvent)",
        VanFiniteAction.OPEN_PANEL to
            "overlay expanded (VanEmbodimentReducer.forOverlayTransition)",
        VanFiniteAction.CLOSE_PANEL to
            "overlay collapsed (VanEmbodimentReducer.forOverlayTransition)",
    )

    /** True when every [VanDurableState] and [VanFiniteAction] has a registered producer. */
    fun isComplete(): Boolean =
        VanDurableState.entries.all { it in STATES } && VanFiniteAction.entries.all { it in ACTIONS }

    /** States/actions with no entry — empty when [isComplete]. Used to make a failure legible. */
    fun missing(): Pair<List<VanDurableState>, List<VanFiniteAction>> = Pair(
        VanDurableState.entries.filterNot { it in STATES },
        VanFiniteAction.entries.filterNot { it in ACTIONS },
    )
}
