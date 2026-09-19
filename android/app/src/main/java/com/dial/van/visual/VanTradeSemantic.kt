package com.dial.van.visual

/**
 * Trading state, classified, and turned into something VAN's field can show.
 *
 * P1-AURA-003. Eight trade aura families existed — watching, setup, entry, in-trade, profit,
 * risk, stop, halt — and their only caller was the PNG board generator. They were reachable
 * through `VanAuraSpecs.tradePreview(kind: String)`, a stringly-typed switch used to draw a
 * capability poster. The live trading screen, meanwhile, derived VAN's presence from the
 * *degraded-code set*: whether VAN looked calm or alarmed while the owner's money was at risk
 * depended on whether a subsystem was reporting a fault, and not at all on the trade.
 *
 * So the families are now an enum, classified from live signals, and published to the same
 * presence runtime that voice and the command envelope write to. Three things follow from
 * that and are deliberate:
 *
 * **Classification is ordered by what the owner needs to see first.** An owner halt outranks
 * a profit; an unknown ledger outranks a calm flat state. The order is the whole content of
 * `classify`, so it is written as a sequence of guards rather than as a score.
 *
 * **An unavailable or stale ledger is UNKNOWN, not FLAT.** Showing a quiet field because VAN
 * cannot read the ledger is the exact failure the audit found elsewhere: absence of evidence
 * rendered as evidence of calm. UNKNOWN has its own appearance.
 *
 * **Nothing here can place, size, modify or cancel a trade.** This is a read of state and a
 * choice of colour and topology. The authority boundary is unchanged.
 *
 * Pure Kotlin, no Android imports: the classification is the part worth testing and it is
 * tested on the JVM.
 */
enum class VanTradeSemantic(
    /** The capability board's panel name, or empty when this family has no panel. */
    val boardKey: String,
) {
    /**
     * Nothing open, nothing pending, and VAN can see that clearly.
     *
     * No board key: a flat book is plain identity cyan, which is the idle field the board
     * already shows on its own page. Sharing WATCHING's key would have made the board's
     * "watching" panel resolve to this and render nothing.
     */
    FLAT(""),

    /** Instruments are being followed; no setup has formed. */
    WATCHING("watching"),

    /** A setup has formed and is waiting on its conditions. */
    SETUP("setup"),

    /** An order is being worked, or a ticket is waiting on the owner. */
    ENTRY("entry"),

    /** Live exposure with the position inside its risk envelope. */
    IN_TRADE("in_trade"),

    /** Live exposure, in profit. */
    PROFIT("profit"),

    /** Live exposure with risk pressure — margin, drawdown, or refusals accumulating. */
    RISK("risk"),

    /** A protective stop has fired, or the risk authority is refusing new work. */
    STOP("stop"),

    /** The owner has halted trading. Outranks everything below it. */
    HALTED("halt"),

    /**
     * VAN cannot read the ledger, or what it read is too old to answer from.
     *
     * P0-TRADE-004's lesson, carried into the visuals: a stale ledger that opens cleanly is
     * not a ledger to show a calm field from.
     */
    UNKNOWN("halt"),
    ;

    val isLive: Boolean
        get() = this == IN_TRADE || this == PROFIT || this == RISK || this == ENTRY

    val needsOwner: Boolean
        get() = this == RISK || this == STOP || this == HALTED || this == UNKNOWN
}

/**
 * What the classifier reads. Every field comes from the gateway's trading read models, which
 * read the VATI ledger — VAN never derives these from its own memory of what it did.
 */
data class VanTradeSignals(
    val ledgerAvailable: Boolean = false,
    val ledgerStale: Boolean = true,
    val ownerHaltActive: Boolean = false,
    val killSwitchTriggers: List<String> = emptyList(),
    val openPositions: Int = 0,
    val openTickets: Int = 0,
    val workingOrders: Int = 0,
    val watchedInstruments: Int = 0,
    val pendingSetups: Int = 0,
    val unrealizedPnl: Double? = null,
    val marginLevelPct: Double? = null,
    val riskRefusalsRecent: Int = 0,
)

object VanTradeSemantics {

    /**
     * Below this margin level the position is under real pressure. It matches
     * `MARGIN_FLOOR_LEVEL_PCT` in the trading risk authority, so the field turns amber at the
     * same point the authority starts refusing — the owner should not learn about the floor
     * from a refusal they did not see coming.
     */
    const val MARGIN_PRESSURE_PCT = 200.0

    fun classify(signals: VanTradeSignals): VanTradeSemantic {
        // Owner authority first. A halt the owner asked for is the most important fact on
        // the screen, whatever the position is doing.
        if (signals.ownerHaltActive) return VanTradeSemantic.HALTED
        // Then what VAN can actually see. An unreadable or stale ledger cannot support any
        // claim below this line.
        if (!signals.ledgerAvailable || signals.ledgerStale) return VanTradeSemantic.UNKNOWN
        if (signals.killSwitchTriggers.isNotEmpty()) return VanTradeSemantic.STOP

        val exposed = signals.openPositions > 0
        val margin = signals.marginLevelPct
        val underPressure = (margin != null && margin < MARGIN_PRESSURE_PCT) ||
            signals.riskRefusalsRecent > 0

        return when {
            exposed && underPressure -> VanTradeSemantic.RISK
            exposed && (signals.unrealizedPnl ?: 0.0) > 0.0 -> VanTradeSemantic.PROFIT
            exposed -> VanTradeSemantic.IN_TRADE
            signals.workingOrders > 0 || signals.openTickets > 0 -> VanTradeSemantic.ENTRY
            signals.pendingSetups > 0 -> VanTradeSemantic.SETUP
            signals.watchedInstruments > 0 -> VanTradeSemantic.WATCHING
            else -> VanTradeSemantic.FLAT
        }
    }

    /**
     * The outer semantic field for a trade state.
     *
     * Zone C only, per Rev 2.2: semantic colour never lands on VAN's body, so a trade in
     * profit does not turn VAN green. The topologies are the ones the capability board
     * already drew; what changed is that they are now reachable from live state.
     */
    fun auraFor(
        semantic: VanTradeSemantic,
        budget: VanEffectBudget = VanEffectBudget.FULL,
    ): VanAuraSpec {
        val idle = VanAuraSpecs.forState(VanDurableState.IDLE, budget)
        return when (semantic) {
            VanTradeSemantic.FLAT -> idle
            VanTradeSemantic.WATCHING -> idle.copy(
                envelopeRadiusScale = 1.46f, envelopeAlpha = 0.14f,
                semanticColor = VanGlassTokens.ACCENT_TEAL,
                envelopeSegments = listOf(VanAuraEnvelopeSegment(200f, 58f)),
            )
            VanTradeSemantic.SETUP -> idle.copy(
                envelopeRadiusScale = 1.50f, envelopeAlpha = 0.14f,
                semanticColor = VanGlassTokens.ACCENT_VIOLET,
                envelopeSegments = listOf(VanAuraEnvelopeSegment(300f, 50f, node = true)),
            )
            VanTradeSemantic.ENTRY -> idle.copy(
                envelopeRadiusScale = 1.48f, envelopeAlpha = 0.16f,
                semanticColor = VanGlassTokens.ACCENT_GOLD,
                envelopeSegments = listOf(VanAuraEnvelopeSegment(-25f, 44f, node = true)),
            )
            VanTradeSemantic.IN_TRADE -> idle.copy(
                envelopeRadiusScale = 1.58f, envelopeAlpha = 0.16f,
                semanticColor = VanGlassTokens.ACCENT_CYAN,
                envelopeSegments = listOf(
                    VanAuraEnvelopeSegment(15f, 46f),
                    VanAuraEnvelopeSegment(200f, 36f),
                ),
            )
            VanTradeSemantic.PROFIT -> idle.copy(
                envelopeRadiusScale = 1.48f, envelopeAlpha = 0.16f,
                semanticColor = VanGlassTokens.ACCENT_GREEN,
                envelopeSegments = listOf(VanAuraEnvelopeSegment(220f, 64f)),
            )
            VanTradeSemantic.RISK -> idle.copy(
                envelopeRadiusScale = 1.52f, envelopeAlpha = 0.16f,
                semanticColor = VanGlassTokens.ACCENT_AMBER,
                envelopeSegments = listOf(
                    VanAuraEnvelopeSegment(-40f, 34f),
                    VanAuraEnvelopeSegment(150f, 30f),
                ),
            )
            VanTradeSemantic.STOP -> idle.copy(
                envelopeRadiusScale = 1.50f, envelopeAlpha = 0.17f,
                semanticColor = VanGlassTokens.ACCENT_RED,
                envelopeSegments = listOf(
                    VanAuraEnvelopeSegment(10f, 36f),
                    VanAuraEnvelopeSegment(200f, 24f),
                ),
            )
            VanTradeSemantic.HALTED, VanTradeSemantic.UNKNOWN -> idle.copy(
                envelopeRadiusScale = 1.45f, envelopeAlpha = 0.16f,
                semanticColor = VanGlassTokens.ACCENT_RED,
                envelopeSegments = listOf(
                    VanAuraEnvelopeSegment(-50f, 30f, node = true),
                    VanAuraEnvelopeSegment(40f, 30f, node = true),
                ),
            )
        }
    }

    /**
     * How the trade state shows on VAN's body.
     *
     * Deliberately conservative: only the states the owner has to act on move the pose. A
     * position quietly in profit is Zone C news, not a reason for VAN to change posture at
     * the owner all day.
     */
    fun durableStateFor(semantic: VanTradeSemantic): VanDurableState? = when (semantic) {
        VanTradeSemantic.HALTED -> VanDurableState.WAITING_FOR_OWNER
        VanTradeSemantic.STOP -> VanDurableState.WARNING
        VanTradeSemantic.RISK -> VanDurableState.WARNING
        VanTradeSemantic.UNKNOWN -> VanDurableState.DEGRADED
        else -> null
    }

    /** One sentence the owner reads, in the same voice as the rest of VAN's status lines. */
    fun headlineFor(semantic: VanTradeSemantic): String = when (semantic) {
        VanTradeSemantic.FLAT -> "Nothing open."
        VanTradeSemantic.WATCHING -> "Watching your instruments."
        VanTradeSemantic.SETUP -> "A setup is forming."
        VanTradeSemantic.ENTRY -> "Working an entry."
        VanTradeSemantic.IN_TRADE -> "You are in a trade."
        VanTradeSemantic.PROFIT -> "You are in a trade, in profit."
        VanTradeSemantic.RISK -> "Risk pressure on an open position."
        VanTradeSemantic.STOP -> "A protective stop has fired."
        VanTradeSemantic.HALTED -> "Trading is halted, because you halted it."
        VanTradeSemantic.UNKNOWN -> "I cannot read the trading ledger, so I am not telling you it is fine."
    }
}
