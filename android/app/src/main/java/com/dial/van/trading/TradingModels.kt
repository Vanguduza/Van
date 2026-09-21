package com.dial.van.trading

import com.dial.van.visual.VanTradeSignals
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject

/**
 * Trading Command Center read models (Rev 5 Part I). Pure Kotlin so every parser is unit-tested
 * off-device. All of it is derived from gateway JSON that is itself a read model of the VATI
 * ledger: nothing here can act, and every numeric value keeps the gateway's exact string form
 * beside its Double so display never rounds the ledger truth away.
 */
private val json = Json { ignoreUnknownKeys = true; isLenient = true }

internal fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content
internal fun JsonObject.num(k: String): Double? = str(k)?.toDoubleOrNull()
internal fun JsonObject.long(k: String): Long? = str(k)?.toDoubleOrNull()?.toLong()
internal fun JsonObject.bool(k: String): Boolean? = str(k)?.toBooleanStrictOrNull()
internal fun JsonObject.obj(k: String): JsonObject? = this[k] as? JsonObject
internal fun JsonObject.arr(k: String): List<JsonObject> = (this[k] as? JsonArray)?.mapNotNull { it as? JsonObject } ?: emptyList()
internal fun JsonObject.strList(k: String): List<String> = (this[k] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.takeIf { p -> p !is JsonNull }?.content } ?: emptyList()
internal fun parseObject(body: String): JsonObject? = runCatching { json.parseToJsonElement(body).jsonObject }.getOrNull()

/** LIVE / DEMO / PAPER / READ ONLY / UNKNOWN — always shown next to anything execution-capable (blueprint §9). */
enum class SafetyIdentity(val label: String, val argb: Long) {
    LIVE("LIVE", 0xFFFF5252L), DEMO("DEMO", 0xFFFFB300L), PAPER("PAPER", 0xFF00E5FFL), READ_ONLY("READ ONLY", 0xFF78909CL), UNKNOWN("UNKNOWN", 0xFF78909CL);
    companion object {
        fun parse(raw: String?): SafetyIdentity = when (raw?.uppercase()) { "LIVE" -> LIVE; "DEMO" -> DEMO; "PAPER" -> PAPER; "READ ONLY", "READ_ONLY" -> READ_ONLY; else -> UNKNOWN }
    }
}

/** Feed truth (blueprint §46): market and account data must never look current when it is not. */
enum class DataState(val label: String, val argb: Long) {
    LIVE("LIVE", 0xFF69F0AEL), DELAYED("DELAYED", 0xFFFFB300L), STALE("STALE", 0xFFFF9100L), OFFLINE("OFFLINE", 0xFFFF5252L), SIMULATED("SIMULATED", 0xFF5C6BC0L), NO_DATA("NO DATA", 0xFF78909CL), UNKNOWN("UNKNOWN", 0xFF78909CL);
    companion object {
        fun parse(raw: String?): DataState = entries.firstOrNull { it.name == raw?.uppercase() } ?: when (raw?.uppercase()) { "NEVER_SYNCED", "UNAVAILABLE" -> OFFLINE; else -> UNKNOWN }
    }
}

data class Money(val raw: String?, val value: Double?) {
    val signed: String get() = value?.let { (if (it >= 0) "+" else "") + String.format(java.util.Locale.ROOT, "%,.2f", it) } ?: "—"
    val plain: String get() = value?.let { String.format(java.util.Locale.ROOT, "%,.2f", it) } ?: "—"
    companion object { fun of(raw: String?) = Money(raw, raw?.toDoubleOrNull()) }
}

data class Pct(val raw: String?, val fraction: Double?) {
    val label: String get() = fraction?.let { String.format(java.util.Locale.ROOT, "%.2f%%", it * 100) } ?: "—"
    companion object { fun of(raw: String?) = Pct(raw, raw?.toDoubleOrNull()) }
}

data class AccountCard(
    val alias: String, val label: String, val broker: String, val mode: String, val currency: String, val safety: SafetyIdentity, val equity: Money, val balance: Money,
    val floatingPnl: Money, val dayPnl: Money, val drawdown: Pct, val connection: DataState, val openPositions: Int, val killSwitch: List<String>, val lastSyncMs: Long?,
) {
    companion object {
        fun from(o: JsonObject) = AccountCard(
            o.str("alias") ?: "?", o.str("label") ?: o.str("alias") ?: "?", o.str("broker") ?: "?", o.str("mode") ?: "?", o.str("currency") ?: "?", SafetyIdentity.parse(o.str("safety_identity")),
            Money.of(o.str("equity")), Money.of(o.str("balance")), Money.of(o.str("floating_pnl")), Money.of(o.str("day_pnl")), Pct.of(o.str("drawdown_pct")),
            DataState.parse(o.str("connection_state")), o.long("open_positions")?.toInt() ?: 0, o.strList("kill_switch"), o.long("last_sync_ms"),
        )
    }
}

data class StrategyPromotionCandidate(
    val strategyId: String,
    val currentState: String,
    val targetState: String,
    val capsuleHash: String,
    val validationHash: String,
    val certificateId: String,
    val certificate: JsonObject,
    val evidenceRefs: List<String>,
    val dataManifestHash: String,
    val dsrProbability: Double?,
    val pboProbability: Double?,
    val expectancyR: Double?,
    val expectancyLowerBoundR: Double?,
    val profitFactor: Double?,
    val maxDrawdown: Double?,
    val certificateEventHash: String,
    val certificateEventMs: Long?,
) {
    companion object {
        fun from(o: JsonObject): StrategyPromotionCandidate? {
            val strategyId = o.str("strategy_id") ?: return null
            val targetState = o.str("target_state") ?: return null
            val validationHash = o.str("validation_hash") ?: return null
            val certificate = o.obj("certificate") ?: return null
            return StrategyPromotionCandidate(
                strategyId = strategyId,
                currentState = o.str("current_state") ?: "UNKNOWN",
                targetState = targetState,
                capsuleHash = o.str("capsule_hash") ?: "",
                validationHash = validationHash,
                certificateId = o.str("certificate_id") ?: "",
                certificate = certificate,
                evidenceRefs = o.strList("evidence_refs"),
                dataManifestHash = o.str("data_manifest_hash") ?: "",
                dsrProbability = o.num("dsr_probability"),
                pboProbability = o.num("pbo_probability"),
                expectancyR = o.num("expectancy_R"),
                expectancyLowerBoundR = o.num("expectancy_lower_bound_R"),
                profitFactor = o.num("profit_factor"),
                maxDrawdown = o.num("max_drawdown"),
                certificateEventHash = o.str("certificate_event_hash") ?: "",
                certificateEventMs = o.long("certificate_event_ms"),
            )
        }

        fun parseAll(body: String): List<StrategyPromotionCandidate>? {
            val root = parseObject(body) ?: return null
            val raw = root.arr("candidates")
            return raw.mapNotNull(::from).takeIf { it.size == raw.size }
        }
    }
}

data class PortfolioSummary(
    val ledgerAvailable: Boolean, val reportingCurrency: String, val accounts: List<AccountCard>, val balance: Money, val equity: Money, val floatingPnl: Money, val dayPnl: Money, val weekPnl: Money,
    val otherCurrencyAccounts: List<String>, val portfolioHeat: Pct, val killSwitch: List<String>, val openTrades: Int, val exposureBySymbol: Map<String, Int>,
    val openPositions: List<TradeRow>, val potential: List<TradeRow>, val recent: List<TradeRow>, val dataStates: Map<String, DataState>,
) {
    /** Worst account/feed truth wins the headline (blueprint §46). */
    val overallDataState: DataState get() = (dataStates.values + accounts.map { it.connection }).maxByOrNull { it.ordinal } ?: DataState.UNKNOWN

    /**
     * P1-AURA-003 — the read models the trading screens already render, in the shape VAN's
     * visual runtime classifies from.
     *
     * The mapping is deliberately mechanical. Any judgement about what a trading state
     * *means* belongs in [VanTradeSemantics.classify], which is pure and tested; a mapper
     * that made decisions here would be a second, untested classifier living beside the
     * first, which is the pattern the audit found repeatedly.
     *
     * `ledgerStale` reads `overallDataState`: a STALE or UNKNOWN feed means VAN is not
     * entitled to show a calm field, which is the same rule the gateway applies to the
     * ledger itself (P0-TRADE-004).
     */
    fun toTradeSignals(ownerHaltActive: Boolean = false, riskRefusalsRecent: Int = 0): VanTradeSignals =
        VanTradeSignals(
            ledgerAvailable = ledgerAvailable,
            ledgerStale = overallDataState != DataState.LIVE,
            ownerHaltActive = ownerHaltActive || killSwitch.any { it.equals("OWNER_HALT", ignoreCase = true) },
            killSwitchTriggers = killSwitch.filterNot { it.equals("OWNER_HALT", ignoreCase = true) },
            openPositions = openPositions.size,
            openTickets = 0,
            workingOrders = potential.size,
            watchedInstruments = exposureBySymbol.size,
            pendingSetups = potential.size,
            unrealizedPnl = floatingPnl.value,
            marginLevelPct = null,
            riskRefusalsRecent = riskRefusalsRecent,
        )
    companion object {
        fun parse(body: String): PortfolioSummary? {
            val o = parseObject(body) ?: return null
            val t = o.obj("totals") ?: JsonObject(emptyMap())
            val r = o.obj("risk") ?: JsonObject(emptyMap())
            val ex = o.obj("exposure")?.obj("by_symbol")?.entries?.associate { it.key to ((it.value as? JsonPrimitive)?.content?.toDoubleOrNull()?.toInt() ?: 0) } ?: emptyMap()
            val ds = o.obj("data_state")?.entries?.associate { it.key to DataState.parse((it.value as? JsonObject)?.str("state")) } ?: emptyMap()
            fun rows(view: TradeView, key: String) = (TradeBookParser.parse(view, Json.encodeToString(JsonObject.serializer(), JsonObject(mapOf(view.query to (o[key] ?: JsonArray(emptyList())))))) as? TradeBookState.Ready)?.rows ?: emptyList()
            return PortfolioSummary(
                o.bool("ledger_available") ?: true, o.str("reporting_currency") ?: "USD", o.arr("accounts").map(AccountCard::from), Money.of(t.str("balance")), Money.of(t.str("equity")), Money.of(t.str("floating_pnl")),
                Money.of(t.str("day_pnl")), Money.of(t.str("week_pnl")), t.strList("accounts_in_other_currencies"), Pct.of(r.str("portfolio_heat")), r.strList("kill_switch_active"), r.long("open_trades")?.toInt() ?: 0, ex,
                rows(TradeView.CURRENT, "open_positions"), rows(TradeView.POTENTIAL, "potential_trades"), rows(TradeView.PAST, "recent_trades"), ds,
            )
        }
    }
}

data class MarketStateCard(
    val symbol: String, val asOfMs: Long?, val session: String, val trend: String, val vol: String, val phase: String, val regimeConfidence: Double?, val integrity: String, val eventWindow: String,
    val minutesToEvent: Int?, val quoteAgeMs: Long?, val dataState: DataState, val lastDecision: String?, val lastDecisionReason: String?, val summary: String, val features: Map<String, String>,
) {
    companion object {
        fun from(o: JsonObject): MarketStateCard {
            val r = o.obj("regime") ?: JsonObject(emptyMap())
            return MarketStateCard(
                o.str("symbol") ?: "?", o.long("as_of_ms"), o.str("session") ?: "?", r.str("trend") ?: "?", r.str("vol") ?: "?", r.str("phase") ?: "?", r.num("confidence"), o.str("integrity") ?: "?", o.str("event_window") ?: "NONE",
                o.long("minutes_to_next_event")?.toInt(), o.long("quote_age_ms"), DataState.parse(o.obj("data_state")?.str("state")), o.obj("last_decision")?.str("decision"), o.obj("last_decision")?.str("reason"),
                o.str("van_summary") ?: "", o.obj("features")?.entries?.mapNotNull { e -> (e.value as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content?.let { e.key to it } }?.toMap() ?: emptyMap(),
            )
        }
        fun parseAll(body: String): List<MarketStateCard> = parseObject(body)?.arr("symbols")?.map(::from) ?: emptyList()
    }
}

data class RiskView(
    val asOfMs: Long?, val portfolioHeat: Pct, val equity: Money, val drawdownFromPeak: Pct, val dayPnlPct: Pct, val weekPnlPct: Pct, val limits: Map<String, String>, val killSwitch: List<String>,
    val consecutiveLosses: Int?, val openTrades: Int, val bySymbol: Map<String, Double>, val byCurrency: Map<String, Double>, val byDirection: Map<String, Int>, val positions: List<RiskPosition>,
    val lastDecision: String?, val lastReasonCode: String?,
) {
    /** Fraction of the mandate's open-stop-risk ceiling in use, if both sides are known. */
    val heatUtilisation: Double? get() { val cap = limits["max_open_stop_risk"]?.toDoubleOrNull() ?: return null; val h = portfolioHeat.fraction ?: return null; return if (cap > 0) (h / cap).coerceIn(0.0, 1.5) else null }
    companion object {
        fun parse(body: String): RiskView? {
            val o = parseObject(body) ?: return null
            val c = o.obj("concentration") ?: JsonObject(emptyMap())
            fun dmap(k: String) = c.obj(k)?.entries?.associate { it.key to ((it.value as? JsonPrimitive)?.content?.toDoubleOrNull() ?: 0.0) } ?: emptyMap()
            return RiskView(
                o.long("as_of_ms"), Pct.of(o.str("portfolio_heat")), Money.of(o.str("equity")), Pct.of(o.str("drawdown_from_peak_pct")), Pct.of(o.str("day_pnl_pct")), Pct.of(o.str("week_pnl_pct")),
                o.obj("limits")?.entries?.mapNotNull { e -> (e.value as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content?.let { e.key to it } }?.toMap() ?: emptyMap(), o.strList("kill_switch"), o.long("consecutive_losses")?.toInt(),
                o.long("open_trades")?.toInt() ?: 0, dmap("by_symbol"), dmap("by_currency"), dmap("by_direction").mapValues { it.value.toInt() }, o.arr("positions").map(RiskPosition::from),
                o.obj("last_decision")?.str("decision"), o.obj("last_decision")?.str("reason_code"),
            )
        }
    }
}

data class RiskPosition(val tradeIntentId: String, val symbol: String, val direction: String, val riskPct: Pct, val size: String?, val stop: String?, val state: String) {
    companion object { fun from(o: JsonObject) = RiskPosition(o.str("trade_intent_id") ?: "", o.str("symbol") ?: "?", o.str("direction") ?: "", Pct.of(o.str("approved_risk_pct")), o.str("approved_size"), o.str("stop"), o.str("state") ?: "?") }
}

data class BarPoint(val t: Long, val o: Double, val h: Double, val l: Double, val c: Double, val v: Double = 0.0) {
    companion object {
        fun from(o: JsonObject): BarPoint? { val t = o.long("t") ?: return null; return BarPoint(t, o.num("o") ?: return null, o.num("h") ?: return null, o.num("l") ?: return null, o.num("c") ?: return null, o.num("v") ?: 0.0) }
    }
}

data class BarSeries(val symbol: String, val timeframe: String, val bars: List<BarPoint>, val provenance: List<String>, val dataState: DataState, val lakeAvailable: Boolean) {
    val isSimulated: Boolean get() = provenance.isNotEmpty() && provenance.all { it == "SYNTHETIC" }
    companion object {
        fun parse(body: String): BarSeries? {
            val o = parseObject(body) ?: return null
            val ds = if (o.bool("lake_available") == false) DataState.OFFLINE else DataState.parse(o.obj("data_state")?.str("state"))
            return BarSeries(o.str("symbol") ?: "?", o.str("timeframe") ?: "?", o.arr("bars").mapNotNull(BarPoint::from), o.strList("provenance"), ds, o.bool("lake_available") ?: true)
        }
    }
}

data class TimelineEntry(val atMs: Long, val kind: String, val text: String, val hash: String) {
    companion object { fun from(o: JsonObject) = TimelineEntry(o.long("at_ms") ?: 0L, o.str("kind") ?: "?", o.str("text") ?: "", o.str("hash") ?: "") }
}

data class ChartMarker(val atMs: Long, val kind: String, val price: Double?)

data class TradeDetail(
    val row: TradeRow, val tradeIntentId: String, val accountAlias: String?, val strategyState: String?, val riskDecision: String?, val reasonCode: String?, val approvedSize: String?, val approvedRisk: Pct,
    val entry: Double?, val fill: Double?, val stop: Double?, val target: Double?, val exit: Double?, val pnl: Money, val rMultiple: Double?, val outcome: String?, val polarity: String?, val lessons: List<String>,
    val multipliers: Map<String, String>, val timeline: List<TimelineEntry>, val interpretation: List<String>, val chartTimeframe: String?, val chart: List<BarPoint>, val markers: List<ChartMarker>,
    val decisionHash: String?, val marketSnapshotHash: String?, val decidedMs: Long?, val openedMs: Long?, val closedMs: Long?, val costRatio: Double?, val view: TradeView,
) {
    companion object {
        fun parse(body: String): TradeDetail? {
            val o = parseObject(body) ?: return null
            if (o.str("trade_intent_id").isNullOrBlank() || o.str("symbol").isNullOrBlank()) return null
            val view = when (o.str("state")) { "CLOSED" -> TradeView.PAST; "OPEN", "WORKING", "AWAITING_OWNER_TICKET" -> TradeView.CURRENT; else -> TradeView.POTENTIAL }
            val row = (TradeBookParser.parse(view, Json.encodeToString(JsonObject.serializer(), JsonObject(mapOf(view.query to JsonArray(listOf(o)))))) as? TradeBookState.Ready)?.rows?.firstOrNull() ?: return null
            val lv = o.obj("levels") ?: JsonObject(emptyMap()); val rv = o.obj("review"); val ch = o.obj("chart")
            return TradeDetail(
                row, o.str("trade_intent_id") ?: "", o.str("account_alias"), o.str("strategy_state"), o.str("risk_decision"), o.str("reason_code"), o.str("approved_size"), Pct.of(o.str("approved_risk_pct")),
                lv.num("entry"), lv.num("fill"), lv.num("stop"), lv.num("target"), lv.num("exit"), Money.of(o.str("pnl") ?: rv?.str("pnl")), o.num("r_multiple") ?: rv?.num("r_multiple"), o.str("outcome") ?: rv?.str("outcome"), o.str("polarity") ?: rv?.str("polarity"),
                o.strList("lessons").ifEmpty { rv?.strList("lessons") ?: emptyList() }, o.obj("multipliers")?.entries?.mapNotNull { e -> (e.value as? JsonPrimitive)?.content?.let { e.key to it } }?.toMap() ?: emptyMap(),
                o.arr("timeline").map(TimelineEntry::from), o.strList("van_interpretation"), ch?.str("timeframe"), ch?.arr("bars")?.mapNotNull(BarPoint::from) ?: emptyList(),
                ch?.arr("markers")?.map { ChartMarker(it.long("at_ms") ?: 0L, it.str("kind") ?: "?", it.num("price")) } ?: emptyList(),
                o.str("decision_hash"), o.str("market_snapshot_hash"), o.long("decided_ms"), o.long("opened_ms"), o.long("closed_ms"), o.num("cost_ratio"), view,
            )
        }
    }
}


data class CognitionModelRow(
    val modelId: String,
    val assessments: Int,
    val verdict: String?,
    val confidence: Double?,
    val qualified: Boolean?,
    val sampleSufficient: Boolean?,
)

data class ResearchMissionRow(
    val missionId: String,
    val state: String,
    val hypothesis: String,
)

data class ImprovementProposalRow(
    val proposalId: String,
    val title: String,
    val liveAffecting: Boolean,
    val admission: String?,
)

data class CognitionSnapshot(
    val ledgerAvailable: Boolean,
    val cognitionMode: String,
    val liveAdvisory: String,
    val liveStatus: String,
    val modelHierarchy: List<String>,
    val summary: Map<String, Int>,
    val models: List<CognitionModelRow>,
    val missions: List<ResearchMissionRow>,
    val proposals: List<ImprovementProposalRow>,
    val rejectionCategories: Map<String, Int>,
    val expansionModes: Map<String, Int>,
) {
    companion object {
        fun parse(body: String): CognitionSnapshot? {
            val root = parseObject(body) ?: return null
            val authority = root.obj("authority") ?: return null
            val summary = root.obj("summary")?.entries?.mapNotNull { (k, v) ->
                (v as? JsonPrimitive)?.content?.toIntOrNull()?.let { k to it }
            }?.toMap() ?: emptyMap()
            val models = root.arr("models").map { row ->
                val perf = row.obj("performance")
                val qualification = perf?.obj("qualification")
                CognitionModelRow(
                    modelId = row.str("model_id") ?: "unknown",
                    assessments = row.long("assessments")?.toInt() ?: 0,
                    verdict = row.obj("latest")?.str("verdict"),
                    confidence = row.obj("latest")?.num("confidence"),
                    qualified = perf?.bool("qualified") ?: qualification?.bool("qualified"),
                    sampleSufficient = perf?.bool("sample_sufficient"),
                )
            }
            val missions = root.obj("research")?.arr("missions")?.map { row ->
                ResearchMissionRow(
                    missionId = row.str("mission_id") ?: "?",
                    state = row.str("state") ?: "UNKNOWN",
                    hypothesis = row.str("hypothesis") ?: "",
                )
            } ?: emptyList()
            val proposals = root.obj("evolution")?.arr("proposals")?.map { row ->
                ImprovementProposalRow(
                    proposalId = row.str("proposal_id") ?: "?",
                    title = row.str("title") ?: "Untitled proposal",
                    liveAffecting = row.bool("live_affecting") ?: false,
                    admission = row.obj("admission")?.let {
                        it.str("state") ?: it.str("decision")
                    },
                )
            } ?: emptyList()
            fun intMap(parent: JsonObject?, key: String): Map<String, Int> =
                parent?.obj(key)?.entries?.mapNotNull { (k, v) ->
                    (v as? JsonPrimitive)?.content?.toIntOrNull()?.let { k to it }
                }?.toMap() ?: emptyMap()
            return CognitionSnapshot(
                ledgerAvailable = root.bool("ledger_available") ?: false,
                cognitionMode = authority.str("cognition_mode") ?: "UNKNOWN",
                liveAdvisory = authority.str("live_advisory") ?: "UNKNOWN",
                liveStatus = authority.str("live_status") ?: "UNKNOWN",
                modelHierarchy = authority.strList("model_hierarchy"),
                summary = summary,
                models = models,
                missions = missions,
                proposals = proposals,
                rejectionCategories = intMap(root.obj("rejections"), "by_category"),
                expansionModes = intMap(root.obj("expansion"), "mode_counts"),
            )
        }
    }
}
