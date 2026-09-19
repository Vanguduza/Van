package com.dial.van.trading

import kotlin.math.abs
import kotlin.math.roundToLong

/**
 * Numbers and ledger keys, in the owner's language.
 *
 * P3-AND-010 — risk caps rendered as `cap 2.0000000000000004%`, which is a `Double` printed
 * with `toString()` and is the tell that nobody looked at this screen. Raw ledger keys like
 * `max_open_stop_risk` were shown as labels, which is the same problem one layer up: the
 * owner is reading the trading system's internal vocabulary.
 *
 * P3-AND-011 — the empty state told the owner to run `python -m vati lake`. There is no
 * phone on which that is an instruction a person can follow, and an empty state that tells
 * the owner to open a terminal is an empty state that tells them the product is not for them.
 *
 * Pure Kotlin, so what the owner reads is executed in `android/verification` rather than
 * inspected on a screenshot.
 */
object TradingFormat {

    // ------------------------------------------------------------------------
    // Moved here verbatim from TradingModels.kt (P3-AND-010). Two formatters in the same
    // package would not have compiled, and two formatters in different packages is how the
    // owner ends up reading two different renderings of the same number on two screens.
    // Bringing them together also puts the existing ones in the JVM harness, where what the
    // owner reads can be executed rather than inspected on a screenshot.
    fun price(v: Double?, digits: Int = 5): String = v?.let { String.format(java.util.Locale.ROOT, "%.${digits}f", it) } ?: "—"
    fun digitsFor(symbol: String): Int = when { symbol.uppercase().contains("JPY") -> 3; symbol.uppercase().startsWith("XAU") || symbol.uppercase().startsWith("XAG") -> 2; symbol.length <= 5 -> 2; else -> 5 }
    fun r(v: Double?): String = v?.let { (if (it >= 0) "+" else "") + String.format(java.util.Locale.ROOT, "%.2fR", it) } ?: "—"
    fun age(nowMs: Long, thenMs: Long?): String { if (thenMs == null || thenMs <= 0) return "never"; val s = (nowMs - thenMs) / 1000; return when { s < 60 -> "${s}s ago"; s < 3600 -> "${s / 60}m ago"; s < 86400 -> "${s / 3600}h ago"; else -> "${s / 86400}d ago" } }
    fun hash8(h: String?): String = h?.take(8) ?: "—"
    fun timeHm(ms: Long): String { val t = java.time.Instant.ofEpochMilli(ms).atZone(java.time.ZoneOffset.UTC); return String.format(java.util.Locale.ROOT, "%02d:%02d", t.hour, t.minute) }
    fun dateShort(ms: Long): String { val t = java.time.Instant.ofEpochMilli(ms).atZone(java.time.ZoneOffset.UTC); return String.format(java.util.Locale.ROOT, "%02d %s", t.dayOfMonth, t.month.name.take(3).lowercase().replaceFirstChar { it.uppercase() }) }

    /**
     * A percentage, at the precision a percentage is meaningful.
     *
     * Two decimals: a risk cap of 2% is 2.00%, and the 2.0000000000000004 that binary
     * floating point produces never reaches the owner.
     */
    fun percent(value: Double?, decimals: Int = 2): String {
        if (value == null || !value.isFinite()) return "—"
        return "${trim(value, decimals)}%"
    }

    /** Money, grouped, with the sign when the sign is the point. */
    fun money(value: Double?, signed: Boolean = false): String {
        if (value == null || !value.isFinite()) return "—"
        val body = group(trim(abs(value), 2))
        val sign = when {
            !signed -> if (value < 0) "-" else ""
            value > 0 -> "+"
            value < 0 -> "-"
            else -> ""
        }
        return "$sign$body"
    }

    // `price` is the one above, moved from TradingModels.kt. It pads to a fixed number of
    // decimals rather than trimming, which is correct for a price axis: a column where
    // 1.1 and 1.10000 are both printed as written is a column the eye cannot scan.

    fun lots(value: Double?): String {
        if (value == null || !value.isFinite()) return "—"
        return trim(value, 2)
    }

    /**
     * Round to [decimals] and drop trailing zeros, but never the last one before the point.
     *
     * Rounded with a scaled integer rather than `String.format`, because these values are
     * grouped afterwards and re-parsing a formatted string to group it is how a thousands
     * separator ends up inside a decimal.
     */
    private fun trim(value: Double, decimals: Int): String {
        var scale = 1L
        repeat(decimals.coerceIn(0, 9)) { scale *= 10 }
        val scaled = (value * scale).roundToLong()
        val whole = scaled / scale
        val fraction = abs(scaled % scale)
        if (decimals <= 0) return whole.toString()
        val padded = fraction.toString().padStart(decimals, '0').trimEnd('0')
        val sign = if (value < 0 && whole == 0L) "-" else ""
        return if (padded.isEmpty()) "$sign$whole" else "$sign$whole.$padded"
    }

    private fun group(text: String): String {
        val dot = text.indexOf('.')
        val whole = if (dot < 0) text else text.substring(0, dot)
        val rest = if (dot < 0) "" else text.substring(dot)
        val negative = whole.startsWith("-")
        val digits = if (negative) whole.drop(1) else whole
        val grouped = digits.reversed().chunked(3).joinToString(",").reversed()
        return (if (negative) "-" else "") + grouped + rest
    }

    /**
     * Ledger keys, in the owner's words.
     *
     * The map is closed and a key it does not know is de-snaked rather than shown raw: a new
     * key appearing on this screen should read as slightly awkward English, never as
     * `max_open_stop_risk`.
     */
    val LEDGER_LABELS: Map<String, String> = mapOf(
        "max_open_stop_risk" to "Most you can lose on open trades",
        "max_daily_loss" to "Daily loss limit",
        "max_weekly_loss" to "Weekly loss limit",
        "max_position_risk" to "Most you can risk on one trade",
        "portfolio_heat" to "How much of your money is at risk now",
        "margin_level_pct" to "Margin level",
        "free_margin" to "Margin you have left",
        "equity" to "Account value",
        "balance" to "Cash balance",
        "floating_pnl" to "Open profit and loss",
        "day_pnl" to "Today",
        "week_pnl" to "This week",
        "open_trades" to "Open trades",
        "kill_switch_active" to "Trading stopped because",
        "reporting_currency" to "Shown in",
    )

    fun label(key: String): String =
        LEDGER_LABELS[key] ?: key.replace('_', ' ').replaceFirstChar { it.uppercase() }

    // ----------------------------------------------------------- P3-AND-011

    /**
     * What an empty trading screen says.
     *
     * Every one of these tells the owner what is true and what, if anything, they can do
     * about it — and none of them mentions a command line. If the answer is "someone has to
     * do something on a server", that is what it says, because an owner who cannot act is
     * better off knowing than being given an instruction they cannot follow.
     */
    fun emptyState(view: String): String = when (view.trim().lowercase()) {
        "current", "open" -> "No open trades."
        "potential" -> "No setups are waiting."
        "past" -> "No closed trades yet."
        "accounts" -> "No trading accounts are connected yet."
        "bars", "chart" ->
            "No price history for this instrument yet. VAN shows what the trading system " +
                "has recorded; it does not fetch prices itself."
        "risk" -> "No risk limits have been published yet."
        else ->
            "Nothing here yet. VAN reads the trading system's ledger; when it has something " +
                "to show, it appears here."
    }

    /**
     * What to say when the ledger itself cannot be read. Never the same as empty.
     *
     * The reason comes from a layer below and may be a fragment rather than a sentence, so
     * it is terminated here: a message that trails off mid-thought reads as a bug, which
     * undercuts the one thing this line is for — telling the owner that VAN knows it does
     * not know.
     */
    fun unavailableState(reason: String?): String {
        val trimmed = reason?.trim().orEmpty()
        if (trimmed.isEmpty()) {
            return "VAN cannot read the trading ledger right now, so it is not telling you it is fine."
        }
        val terminated = if (trimmed.last() in ".!?") trimmed else "$trimmed."
        return "VAN cannot read the trading ledger right now: $terminated"
    }
}
