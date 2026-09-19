package com.dial.van.trading

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * Owner preview of the trade book (Rev 4 Part K.4) for the floating overlay.
 *
 * Pure Kotlin so it is unit-testable off-device. It parses the gateway's
 * `GET /v1/trading/trades` read model and formats rows for the glass panel. It carries
 * no action: nothing on this surface can place, size, modify or cancel a trade, and the
 * confidence score is the uncalibrated display signal the gateway labels it as.
 */
enum class TradeView(val query: String, val label: String) {
    PAST("past", "Past"),
    CURRENT("current", "Current"),
    POTENTIAL("potential", "Potential"),
    ;

    /**
     * P3-AND-011 — the empty copy lived here as three literals and there were a dozen more
     * scattered through the screens, one of which told the owner to run `python -m vati
     * lake`. There is one place now, and it is executed in `android/verification`.
     */
    val emptyCopy: String get() = TradingFormat.emptyState(query)
}

enum class ConfidenceBand(val label: String, val argb: Long) {
    HIGH("High", 0xFF69F0AEL),
    MEDIUM("Medium", 0xFF00E5FFL),
    LOW("Low", 0xFFFFB300L),
    MINIMAL("Minimal", 0xFF78909CL),
    UNKNOWN("n/a", 0xFF78909CL);

    companion object {
        fun parse(raw: String?): ConfidenceBand =
            entries.firstOrNull { it.name.equals(raw, ignoreCase = true) } ?: UNKNOWN

        /** Same thresholds as `vati.arbiter.confidence.band_for`. */
        fun forScore(score: Double): ConfidenceBand = when {
            score >= 0.75 -> HIGH
            score >= 0.50 -> MEDIUM
            score >= 0.25 -> LOW
            else -> MINIMAL
        }
    }
}

data class TradeConfidence(val score: Double?, val band: ConfidenceBand) {
    /** "72%" or "n/a"; the panel never shows a bare decimal the owner has to interpret. */
    val percentLabel: String get() = score?.let { "${(it * 100).toInt()}%" } ?: "n/a"
}

data class TradeRow(
    val view: TradeView,
    val symbol: String,
    val direction: String,
    val strategyId: String,
    val state: String,
    val headline: String,
    val detail: String,
    val confidence: TradeConfidence,
    val timestampMs: Long,
    val reasons: List<String> = emptyList(),
    /** Ledger intent id when the row is a real intent (past, current, risk-rejected); null for assessment candidates. */
    val tradeIntentId: String? = null,
    val stopPrice: Double? = null,
    val entryPrice: Double? = null,
)

sealed class TradeBookState {
    data object Loading : TradeBookState()
    data class Ready(val view: TradeView, val rows: List<TradeRow>, val ledgerAvailable: Boolean, val basis: String) : TradeBookState()
    data class Unavailable(val view: TradeView, val reason: String) : TradeBookState()
}

object TradeBookParser {
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    fun parse(view: TradeView, body: String): TradeBookState {
        val root = runCatching { json.parseToJsonElement(body).jsonObject }.getOrElse {
            return TradeBookState.Unavailable(view, "Trade ledger response unreadable")
        }
        val available = root.bool("ledger_available") ?: true
        val basis = root.str("confidence_basis") ?: "confidence is an uncalibrated display signal"
        val items = root[view.query]?.let { if (it is JsonArray) it else null } ?: JsonArray(emptyList())
        val rows = items.mapNotNull { el -> runCatching { row(view, el.jsonObject) }.getOrNull() }
        return TradeBookState.Ready(view, rows, available, basis)
    }

    private fun row(view: TradeView, o: JsonObject): TradeRow {
        val symbol = o.str("symbol") ?: "?"
        val direction = o.str("direction") ?: ""
        val strategy = o.str("strategy_id") ?: "?"
        val conf = confidence(o["confidence"])
        val id = o.str("trade_intent_id")?.takeIf { it.isNotBlank() }
        val stopPx = o.num("protective_stop_price") ?: o.num("stop")
        val entryPx = o.num("fill") ?: o.num("entry")
        return when (view) {
            TradeView.PAST -> {
                val r = o.num("r_multiple")
                val pnl = o.num("pnl")
                TradeRow(
                    view, symbol, direction, strategy,
                    state = o.str("outcome") ?: "CLOSED",
                    headline = "$symbol ${direction.lowercase()} · ${formatR(r)} · ${formatPnl(pnl)}",
                    detail = listOfNotNull(o.str("outcome"), o.str("exit_reason")?.let { "exit $it" }, shortStrategy(strategy)).joinToString(" · "),
                    confidence = conf,
                    timestampMs = o.long("closed_ms") ?: 0L,
                    reasons = o.strList("lessons"),
                    tradeIntentId = id, stopPrice = stopPx, entryPrice = entryPx,
                )
            }
            TradeView.CURRENT -> {
                val ticket = o["owner_ticket"]?.takeIf { it is JsonObject }?.jsonObject
                val stop = o.str("protective_stop_price") ?: o.str("stop")
                TradeRow(
                    view, symbol, direction, strategy,
                    state = o.str("state") ?: "OPEN",
                    headline = "$symbol ${direction.lowercase()} · size ${o.str("approved_size") ?: "?"} · ${o.str("state") ?: "OPEN"}",
                    detail = listOfNotNull(
                        o.str("fill")?.let { "fill $it" },
                        stop?.let { "stop $it" },
                        if (o.bool("protective_stop_confirmed") == false) "STOP NOT CONFIRMED" else null,
                        ticket?.let { "ticket ${it.str("ticket")} ${it.str("status")}" },
                        shortStrategy(strategy),
                    ).joinToString(" · "),
                    confidence = conf,
                    timestampMs = o.long("opened_ms") ?: o.long("decided_ms") ?: 0L,
                    tradeIntentId = id, stopPrice = stopPx, entryPrice = entryPx,
                )
            }
            TradeView.POTENTIAL -> {
                val label = o.str("label") ?: o.str("decision") ?: "?"
                TradeRow(
                    view, symbol, direction, strategy,
                    state = label,
                    headline = "$symbol ${direction.lowercase()} · $label",
                    detail = listOfNotNull(
                        o.str("entry")?.let { "entry $it" },
                        o.str("stop")?.let { "stop $it" },
                        o.str("cost_multiple")?.let { "edge ${trimDecimal(it)}× cost" },
                        shortStrategy(strategy),
                    ).joinToString(" · "),
                    confidence = conf,
                    timestampMs = o.long("assessed_ms") ?: o.long("decided_ms") ?: 0L,
                    reasons = o.strList("reasons"),
                    tradeIntentId = id, stopPrice = stopPx, entryPrice = entryPx,
                )
            }
        }
    }

    private fun confidence(el: JsonElement?): TradeConfidence {
        val o = (el as? JsonObject) ?: return TradeConfidence(null, ConfidenceBand.UNKNOWN)
        val score = o.num("score")
        val band = o.str("band")?.let { ConfidenceBand.parse(it) } ?: score?.let { ConfidenceBand.forScore(it) } ?: ConfidenceBand.UNKNOWN
        return TradeConfidence(score, band)
    }

    internal fun formatR(r: Double?): String = r?.let { (if (it >= 0) "+" else "") + String.format(java.util.Locale.ROOT, "%.2fR", it) } ?: "R n/a"
    internal fun formatPnl(p: Double?): String = p?.let { (if (it >= 0) "+" else "") + String.format(java.util.Locale.ROOT, "%.2f", it) } ?: "P&L n/a"
    internal fun shortStrategy(id: String): String = id.substringBeforeLast("-")
    private fun trimDecimal(s: String): String = s.toDoubleOrNull()?.let { String.format(java.util.Locale.ROOT, "%.1f", it) } ?: s

    private fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content
    private fun JsonObject.num(k: String): Double? = str(k)?.toDoubleOrNull()
    private fun JsonObject.long(k: String): Long? = str(k)?.toDoubleOrNull()?.toLong()
    private fun JsonObject.bool(k: String): Boolean? = (this[k] as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content?.toBooleanStrictOrNull()
    private fun JsonObject.strList(k: String): List<String> = (this[k] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.takeIf { p -> p !is JsonNull }?.content } ?: emptyList()
}
