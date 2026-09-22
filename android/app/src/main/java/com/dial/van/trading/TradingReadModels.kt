package com.dial.van.trading

import com.dial.van.design.StatusSemantics
import com.dial.van.design.ThesisState
import kotlinx.serialization.json.JsonObject

/**
 * GAP-F-003 typed models for the five trading intelligence read models
 * (`trading/vati/readmodels/active.py`): `positions()`, `events()`, `potential()`,
 * `history()` and `assessment()`. Every one of these is, on the wire, a read model of the
 * VATI hash-chained ledger and nothing else (see that module's own docstring) — these
 * parsers add no interpretation the ledger did not already record, only shape.
 *
 * Pure Kotlin, no Android imports, so the parsing and the domain-state mappings below are
 * executed in `android/verification` rather than only inspected on a screenshot — same
 * reasoning as `TradingModels.kt` and `TradeBook.kt` beside this file.
 *
 * @DataSource("GET /v1/trading/positions")
 * @DataSource("GET /v1/trading/events")
 * @DataSource("GET /v1/trading/potential")
 * @DataSource("GET /v1/trading/history")
 * @DataSource("GET /v1/trading/assessment")
 */

// --------------------------------------------------------------------------- shared pieces

data class LinkedEventBrief(
    val headlineId: String?,
    val headlineTitle: String? = null,
    val materiality: Double?,
    val uncertainty: Double? = null,
    val concern: String?,
    val relevanceBasis: String? = null,
    val atMs: Long?,
) {
    companion object {
        fun from(o: JsonObject) = LinkedEventBrief(
            o.str("headline_id"), o.str("headline_title"), o.num("materiality"), o.num("uncertainty"),
            o.str("concern"), o.str("relevance_basis"), o.long("at_ms"),
        )
    }
}

// -------------------------------------------------------------------------------- positions

data class PositionThesis(
    val seal: String?,
    val statement: String?,
    val expectedPath: String?,
    val invalidation: String?,
    val confirmation: String?,
    val adverseSignals: List<String>,
    val eventSensitivity: String?,
    val originalApprovedRiskPct: Double?,
    val createdMs: Long?,
) {
    companion object {
        fun from(o: JsonObject) = PositionThesis(
            o.str("seal"), o.str("statement"), o.str("expected_path"), o.str("invalidation"), o.str("confirmation"),
            o.strList("adverse_signals"), o.str("event_sensitivity"), o.num("original_approved_risk_pct"), o.long("created_ms"),
        )
    }
}

data class PositionAssessment(
    val state: String?,
    val previousState: String?,
    val reasons: List<String>,
    val reasonDetail: String?,
    val evidence: List<String>,
    val eventMateriality: Double?,
    val arguesForLess: Boolean?,
    val assessedMs: Long?,
) {
    companion object {
        fun from(o: JsonObject) = PositionAssessment(
            o.str("state"), o.str("previous_state"), o.strList("reasons"), o.str("reason_detail"), o.strList("evidence"),
            o.num("event_materiality"), o.bool("argues_for_less"), o.long("assessed_ms"),
        )
    }
}

data class PositionHealth(
    val state: String?,
    val reasons: List<String>,
    val blocksScaling: Boolean?,
    val requiresPreservation: Boolean?,
    val assessedMs: Long?,
) {
    companion object {
        fun from(o: JsonObject) = PositionHealth(
            o.str("state"), o.strList("reasons"), o.bool("blocks_scaling"), o.bool("requires_preservation"), o.long("assessed_ms"),
        )
    }
}

data class PositionProposal(
    val action: String?,
    val rationale: String?,
    val reasons: List<String>,
    val requiresAuthority: Boolean?,
    val proposedMs: Long?,
) {
    companion object {
        fun from(o: JsonObject) = PositionProposal(
            o.str("action"), o.str("rationale"), o.strList("reasons"), o.bool("requires_authority"), o.long("proposed_ms"),
        )
    }
}

data class OpenPosition(
    val tradeIntentId: String,
    val symbol: String,
    val venue: String?,
    val accountAlias: String?,
    val direction: String?,
    val strategyId: String?,
    val openedMs: Long,
    val entry: Double?,
    val quantity: Double?,
    val approvedSize: String?,
    val approvedRiskPct: Double?,
    val portfolioHeatAfter: Double?,
    val stop: Double?,
    val protectionConfirmed: Boolean,
    val atOrBeyondBreakEven: Boolean?,
    val unrealisedR: Double?,
    val thesis: PositionThesis?,
    val thesisStateRaw: String?,
    val latestAssessment: PositionAssessment?,
    val health: PositionHealth?,
    val latestProposal: PositionProposal?,
    val linkedEvents: List<LinkedEventBrief>,
) {
    /** DNA §2: thesis state, never the sign of the R, decides this position's colour role. */
    val thesisState: ThesisState get() = TradingReadModels.thesisStateFor(thesisStateRaw)

    companion object {
        fun from(o: JsonObject): OpenPosition? {
            val id = o.str("trade_intent_id") ?: return null
            val symbol = o.str("symbol") ?: return null
            val exposure = o.obj("exposure") ?: JsonObject(emptyMap())
            val protection = o.obj("protection") ?: JsonObject(emptyMap())
            val assessment = o.obj("latest_assessment")
            return OpenPosition(
                tradeIntentId = id,
                symbol = symbol,
                venue = o.str("venue"),
                accountAlias = o.str("account_alias"),
                direction = o.str("direction"),
                strategyId = o.str("strategy_id"),
                openedMs = o.long("opened_ms") ?: 0L,
                entry = exposure.num("entry"),
                quantity = exposure.num("quantity"),
                approvedSize = exposure.str("approved_size"),
                approvedRiskPct = exposure.num("approved_risk_pct"),
                portfolioHeatAfter = exposure.num("portfolio_heat_after"),
                stop = protection.num("stop"),
                protectionConfirmed = protection.bool("confirmed") ?: false,
                atOrBeyondBreakEven = protection.bool("at_or_beyond_break_even"),
                unrealisedR = o.num("unrealised_r"),
                thesis = o.obj("thesis")?.let(PositionThesis::from),
                thesisStateRaw = o.str("thesis_state") ?: assessment?.str("state"),
                latestAssessment = assessment?.let(PositionAssessment::from),
                health = o.obj("health")?.let(PositionHealth::from),
                latestProposal = o.obj("latest_proposal")?.let(PositionProposal::from),
                linkedEvents = o.arr("linked_events").map(LinkedEventBrief::from),
            )
        }
    }
}

data class PositionsReadModel(val ledgerAvailable: Boolean, val count: Int, val positions: List<OpenPosition>) {
    companion object {
        fun parse(body: String): PositionsReadModel? {
            val o = parseObject(body) ?: return null
            return PositionsReadModel(
                o.bool("ledger_available") ?: false,
                o.long("count")?.toInt() ?: 0,
                o.arr("positions").mapNotNull(OpenPosition::from),
            )
        }
    }
}

// ----------------------------------------------------------------------------------- events

data class LedgerEventRow(
    val kind: String,
    val headlineId: String?,
    val eventKey: String?,
    val sourceId: String?,
    val trust: String?,
    val title: String?,
    val name: String?,
    val currencies: List<String>,
    val symbols: List<String>,
    val concern: String?,
    val severity: String?,
    val tier: String?,
    val status: String?,
    val usable: Boolean?,
    val publishedMs: Long,
    val authority: String?,
) {
    /** Newsroom-style headline vs. calendar release. */
    val isHeadline: Boolean get() = kind == "HEADLINE"

    companion object {
        fun from(o: JsonObject) = LedgerEventRow(
            o.str("kind") ?: "?", o.str("headline_id"), o.str("event_key"), o.str("source_id"), o.str("trust"),
            o.str("title"), o.str("name"), o.strList("currencies"), o.strList("symbols"), o.str("concern"),
            o.str("severity"), o.str("tier"), o.str("status"), o.bool("usable"), o.long("published_ms") ?: 0L, o.str("authority"),
        )
    }
}

data class EventImpactRow(
    val headlineId: String?,
    val subjectKind: String?,
    val subjectId: String?,
    val symbol: String?,
    val materiality: Double?,
    val uncertainty: Double?,
    val concern: String?,
    val actionable: Boolean?,
    val atMs: Long,
) {
    companion object {
        fun from(o: JsonObject) = EventImpactRow(
            o.str("headline_id"), o.str("subject_kind"), o.str("subject_id"), o.str("symbol"), o.num("materiality"),
            o.num("uncertainty"), o.str("concern"), o.bool("actionable"), o.long("at_ms") ?: 0L,
        )
    }
}

data class EventsReadModel(val ledgerAvailable: Boolean, val count: Int, val events: List<LedgerEventRow>, val impacts: List<EventImpactRow>) {
    companion object {
        fun parse(body: String): EventsReadModel? {
            val o = parseObject(body) ?: return null
            return EventsReadModel(
                o.bool("ledger_available") ?: false,
                o.long("count")?.toInt() ?: 0,
                o.arr("events").map(LedgerEventRow::from),
                o.arr("impacts").map(EventImpactRow::from),
            )
        }
    }
}

// -------------------------------------------------------------------------------- potential

data class PotentialRiskRequirement(val capsuleRiskCeiling: Double?, val stop: Double?, val entry: Double?, val validUntilMs: Long?) {
    companion object {
        fun from(o: JsonObject) = PotentialRiskRequirement(o.num("capsule_risk_ceiling"), o.num("stop"), o.num("entry"), o.long("valid_until_ms"))
    }
}

data class PotentialInvalidation(val stop: Double?, val expiresMs: Long?) {
    companion object { fun from(o: JsonObject) = PotentialInvalidation(o.num("stop"), o.long("expires_ms")) }
}

data class PotentialCandidate(
    val symbol: String,
    val direction: String?,
    val strategyId: String?,
    val kind: String?,
    val label: String?,
    val entry: Double?,
    val stop: Double?,
    val costMultiple: Double?,
    val confidence: TradeConfidence,
    val reasons: List<String>,
    val assessedMs: Long?,
    val linkedEvents: List<LinkedEventBrief>,
    val evidenceRefs: List<String>,
    val riskRequirement: PotentialRiskRequirement?,
    val invalidation: PotentialInvalidation?,
) {
    companion object {
        fun from(o: JsonObject): PotentialCandidate? {
            val symbol = o.str("symbol") ?: return null
            val confObj = o.obj("confidence")
            val score = confObj?.num("score")
            val band = confObj?.str("band")?.let(ConfidenceBand::parse) ?: score?.let(ConfidenceBand::forScore) ?: ConfidenceBand.UNKNOWN
            return PotentialCandidate(
                symbol = symbol,
                direction = o.str("direction"),
                strategyId = o.str("strategy_id"),
                kind = o.str("kind"),
                label = o.str("label") ?: o.str("decision"),
                entry = o.num("entry"),
                stop = o.num("stop"),
                costMultiple = o.num("cost_multiple"),
                confidence = TradeConfidence(score, band),
                reasons = o.strList("reasons"),
                assessedMs = o.long("assessed_ms") ?: o.long("decided_ms"),
                linkedEvents = o.arr("linked_events").map(LinkedEventBrief::from),
                evidenceRefs = o.strList("evidence_refs"),
                riskRequirement = o.obj("risk_requirement")?.let(PotentialRiskRequirement::from),
                invalidation = o.obj("invalidation")?.let(PotentialInvalidation::from),
            )
        }
    }
}

data class PotentialReadModel(val ledgerAvailable: Boolean, val count: Int, val trades: List<PotentialCandidate>) {
    companion object {
        fun parse(body: String): PotentialReadModel? {
            val o = parseObject(body) ?: return null
            return PotentialReadModel(
                o.bool("ledger_available") ?: false,
                o.long("count")?.toInt() ?: 0,
                o.arr("potential_trades").mapNotNull(PotentialCandidate::from),
            )
        }
    }
}

// ---------------------------------------------------------------------------------- history

data class TradeQuadrant(
    val quadrant: String?,
    val decisionQuality: String?,
    val outcomeQuality: String?,
    val faults: List<String>,
    val faultDetail: String?,
    val isLucky: Boolean?,
    val isUnlucky: Boolean?,
) {
    companion object {
        fun from(o: JsonObject) = TradeQuadrant(
            o.str("quadrant"), o.str("decision_quality"), o.str("outcome_quality"), o.strList("faults"),
            o.str("fault_detail"), o.bool("is_lucky"), o.bool("is_unlucky"),
        )
    }
}

data class TradeAttribution(val realised: Double?, val dominantBucket: String?, val counterfactual: Double?, val buckets: Map<String, Double>) {
    companion object {
        fun from(o: JsonObject) = TradeAttribution(
            o.num("realised"), o.str("dominant_bucket"), o.num("counterfactual"),
            o.obj("buckets")?.entries?.mapNotNull { (k, v) -> (v as? kotlinx.serialization.json.JsonPrimitive)?.content?.toDoubleOrNull()?.let { k to it } }?.toMap() ?: emptyMap(),
        )
    }
}

data class TradeLesson(val lessonId: String?, val quadrant: String?, val keep: String?, val avoid: String?, val confidence: Double?) {
    companion object {
        fun from(o: JsonObject) = TradeLesson(o.str("lesson_id"), o.str("quadrant"), o.str("keep"), o.str("avoid"), o.num("confidence"))
    }
}

data class ClosedTrade(
    val tradeIntentId: String,
    val strategyId: String?,
    val outcome: String?,
    val polarity: String?,
    val rMultiple: Double?,
    val pnl: Double?,
    val exitReason: String?,
    val closedMs: Long,
    val quadrant: TradeQuadrant?,
    val attribution: TradeAttribution?,
    val lessons: List<TradeLesson>,
) {
    companion object {
        fun from(o: JsonObject): ClosedTrade? {
            val id = o.str("trade_intent_id") ?: return null
            return ClosedTrade(
                id, o.str("strategy_id"), o.str("outcome"), o.str("polarity"), o.num("r_multiple"), o.num("pnl"),
                o.str("exit_reason"), o.long("closed_ms") ?: 0L, o.obj("quadrant")?.let(TradeQuadrant::from),
                o.obj("attribution")?.let(TradeAttribution::from), o.arr("lessons").map(TradeLesson::from),
            )
        }
    }
}

data class HistoryReadModel(val ledgerAvailable: Boolean, val count: Int, val byQuadrant: Map<String, Int>, val trades: List<ClosedTrade>) {
    companion object {
        fun parse(body: String): HistoryReadModel? {
            val o = parseObject(body) ?: return null
            val byQuadrant = o.obj("by_quadrant")?.entries?.mapNotNull { (k, v) -> (v as? kotlinx.serialization.json.JsonPrimitive)?.content?.toIntOrNull()?.let { k to it } }?.toMap() ?: emptyMap()
            return HistoryReadModel(
                o.bool("ledger_available") ?: false, o.long("count")?.toInt() ?: 0, byQuadrant,
                o.arr("history").mapNotNull(ClosedTrade::from),
            )
        }
    }
}

// ------------------------------------------------------------------------------- assessment

data class UrgentRisk(val tradeIntentId: String?, val symbol: String?, val strategyId: String?, val reasons: List<String>, val latestProposal: String?) {
    companion object {
        fun from(o: JsonObject) = UrgentRisk(o.str("trade_intent_id"), o.str("symbol"), o.str("strategy_id"), o.strList("reasons"), o.str("latest_proposal"))
    }
}

/** DNA-honest invoker read: `state` is shown verbatim, e.g. "Cognition: not configured" for MODEL_INVOKER_UNCONFIGURED. */
data class CognitionInvokerState(val invoker: String, val state: String) {
    companion object {
        fun from(o: JsonObject) = CognitionInvokerState(o.str("cognition_invoker") ?: "none", o.str("state") ?: "MODEL_INVOKER_UNCONFIGURED")
    }
}

data class AssessmentReadModel(
    val ledgerAvailable: Boolean,
    val urgentRisks: List<UrgentRisk>,
    val portfolioHeat: Double?,
    val maxOpenStopRisk: Double?,
    val availableRisk: Double?,
    val availableRiskNote: String?,
    val openPositions: Int,
    val activeTheses: Map<String, Int>,
    val killSwitchActive: List<String>,
    val cognition: CognitionInvokerState,
) {
    /** DNA §3 HeatBar's `fraction`: heat against the mandate ceiling; null when either side is unknown. */
    val heatFraction: Float? get() {
        val heat = portfolioHeat ?: return null
        val cap = maxOpenStopRisk?.takeIf { it > 0 } ?: return null
        return (heat / cap).toFloat()
    }

    companion object {
        fun parse(body: String): AssessmentReadModel? {
            val o = parseObject(body) ?: return null
            val theses = o.obj("active_theses")?.entries?.mapNotNull { (k, v) -> (v as? kotlinx.serialization.json.JsonPrimitive)?.content?.toIntOrNull()?.let { k to it } }?.toMap() ?: emptyMap()
            return AssessmentReadModel(
                o.bool("ledger_available") ?: false,
                o.arr("urgent_risks").map(UrgentRisk::from),
                o.num("portfolio_heat"),
                o.num("max_open_stop_risk"),
                o.num("available_risk"),
                o.str("available_risk_note"),
                o.long("open_positions")?.toInt() ?: 0,
                theses,
                o.strList("kill_switch_active"),
                o.obj("cognition")?.let(CognitionInvokerState::from) ?: CognitionInvokerState("none", "MODEL_INVOKER_UNCONFIGURED"),
            )
        }
    }
}

// ------------------------------------------------------------------------------- mappings

/**
 * The mechanical mappings this read-model layer owns: ledger thesis-state strings →
 * [ThesisState] (which `StatusSemantics.forThesisState` then colours), a materiality filter
 * for "significant" events (DNA §5's Overview panel), and a quadrant tally for the History
 * screen's distribution visual.
 */
object TradingReadModels {

    /** DNA §5 Overview: "significant events (from /events, materiality ≥ threshold)." */
    const val DEFAULT_MATERIALITY_THRESHOLD = 0.5

    /** Mirrors `backend/van_gateway/trading/service.py`'s `LEDGER_STALENESS_MS`: how old the
     * newest thing VAN has read off the ledger may be before Overview's `LiveBadge` stops
     * reading LIVE. There is no dedicated `/v1/trading/status` client method in this
     * worker's scope, so Overview derives its own "newest timestamp" from whatever read
     * models it already fetched rather than calling that route (see this worker's report). */
    const val LEDGER_STALENESS_MS = 15 * 60 * 1000L

    /** vati.lifecycle.thesis / THESIS_ASSESSMENT event states, mapped onto the design system's
     * closed [ThesisState] set. Unknown/absent reads as [ThesisState.HYPOTHESIS] — a claim
     * that has not yet earned a confirmed or weakening read, never silently "confirmed". */
    fun thesisStateFor(raw: String?): ThesisState = when (raw?.trim()?.uppercase()) {
        "CONFIRMED" -> ThesisState.CONFIRMED
        "UNCHANGED", "MONITORING" -> ThesisState.MONITORING
        "WEAKER", "WEAKENING", "RISKIER", "OVEREXTENDED" -> ThesisState.WEAKENING
        "INVALIDATED" -> ThesisState.INVALIDATED
        else -> ThesisState.HYPOTHESIS
    }

    /** `health.state` ("IMPAIRED"/"FAILING") layered onto a thesis-derived role: health never
     * reads *more* favourable than the thesis itself, only ever as bad or worse. */
    fun roleForHealth(thesisState: ThesisState, healthState: String?): String {
        val thesisRole = StatusSemantics.forThesisState(thesisState)
        return when (healthState?.trim()?.uppercase()) {
            "FAILING" -> StatusSemantics.ROLE_CRITICAL
            "IMPAIRED" -> if (thesisRole == StatusSemantics.ROLE_CRITICAL) thesisRole else StatusSemantics.ROLE_DETERIORATING
            else -> thesisRole
        }
    }

    /** DNA §5: "significant events (... materiality ≥ threshold)." */
    fun significantImpacts(impacts: List<EventImpactRow>, threshold: Double = DEFAULT_MATERIALITY_THRESHOLD): List<EventImpactRow> =
        impacts.filter { (it.materiality ?: -1.0) >= threshold }

    /** Trust tier → status role, for `EvidenceRow`'s `trustRole` on the events list. */
    fun roleForTrust(trust: String?): String = when (trust?.trim()?.uppercase()) {
        "HIGH", "VERIFIED", "PRIMARY" -> StatusSemantics.ROLE_FAVOURABLE
        "LOW", "UNVERIFIED", "RUMOUR" -> StatusSemantics.ROLE_EVENT_RISK
        else -> StatusSemantics.ROLE_MONITOR
    }

    /** History's quadrant-distribution visual: a tally over whatever page of trades is shown,
     * independent of the server's own `by_quadrant` (that one covers the whole ledger; this
     * one covers exactly the rows on screen, so the two can legitimately differ). */
    fun quadrantTally(trades: List<ClosedTrade>): Map<String, Int> =
        trades.mapNotNull { it.quadrant?.quadrant }.groupingBy { it }.eachCount()

    /** GOOD_DECISION_GOOD_OUTCOME → `favourable`, etc. — decision quality is the axis that
     * should change what VAN does next (DNA §6: celebrate only in this quadrant, never on
     * P&L alone), never P&L sign. */
    fun roleForQuadrant(quadrant: String?): String = when (quadrant) {
        "GOOD_DECISION_GOOD_OUTCOME" -> StatusSemantics.ROLE_FAVOURABLE
        "GOOD_DECISION_BAD_OUTCOME" -> StatusSemantics.ROLE_MONITOR
        "BAD_DECISION_GOOD_OUTCOME" -> StatusSemantics.ROLE_EVENT_RISK
        "BAD_DECISION_BAD_OUTCOME" -> StatusSemantics.ROLE_CRITICAL
        else -> StatusSemantics.ROLE_DISABLED
    }

    /** "GOOD_DECISION_GOOD_OUTCOME" -> "Good decision, good outcome". */
    fun quadrantLabel(quadrant: String?): String {
        if (quadrant.isNullOrBlank()) return "Unclassified"
        return quadrant.lowercase().replace('_', ' ').replaceFirstChar { it.uppercase() }
    }
}
