package com.dial.van.trading

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * P3-AND-010 / P3-AND-011 — `cap 2.0000000000000004%` on a risk screen, and an empty state
 * that told the owner to run `python -m vati lake`.
 */
class TradingFormatTest {

    @Test
    fun `the float artefact never reaches the owner`() {
        // This is the exact value the screen printed: 2.0 arrived as the sum of two
        // percentages and `Double.toString` showed all of it.
        val cap = 0.8 + 1.2000000000000002
        assertEquals("2%", TradingFormat.percent(cap))
        assertEquals("2.5%", TradingFormat.percent(2.5))
        assertEquals("0.75%", TradingFormat.percent(0.7512))
        assertEquals("-1.5%", TradingFormat.percent(-1.5))
    }

    @Test
    fun `a missing number is a dash, not a zero`() {
        // Zero risk and unknown risk are different facts, and printing one as the other is
        // how an owner reads "no exposure" off a screen that simply has not loaded.
        assertEquals("—", TradingFormat.percent(null))
        assertEquals("—", TradingFormat.money(null))
        assertEquals("—", TradingFormat.lots(null))
        assertEquals("—", TradingFormat.percent(Double.NaN))
        assertEquals("—", TradingFormat.money(Double.POSITIVE_INFINITY))
    }

    @Test
    fun `money is grouped so the eye can count the digits`() {
        assertEquals("1,000", TradingFormat.money(1000.0))
        assertEquals("12,345.67", TradingFormat.money(12345.671))
        assertEquals("999", TradingFormat.money(999.0))
        assertEquals("-1,250.5", TradingFormat.money(-1250.5))
    }

    @Test
    fun `a signed number says which way it went`() {
        assertEquals("+320.4", TradingFormat.money(320.4, signed = true))
        assertEquals("-320.4", TradingFormat.money(-320.4, signed = true))
        assertEquals("0", TradingFormat.money(0.0, signed = true))
    }

    @Test
    fun `a separator never lands inside the decimal`() {
        // Grouping a string that was formatted and then re-parsed is how "1,234.5,678"
        // happens. The grouping runs on the whole part only.
        val text = TradingFormat.money(1234567.89)
        assertEquals("1,234,567.89", text)
        assertEquals(1, text.count { it == '.' })
        assertFalse(text.substringAfter('.').contains(','))
    }

    @Test
    fun `a small negative keeps its sign`() {
        assertEquals("-0.25%", TradingFormat.percent(-0.25))
        assertEquals("-0.5", TradingFormat.money(-0.5))
    }

    @Test
    fun `prices keep their padding because a column has to scan`() {
        // Unlike percentages, a price axis wants fixed decimals: a column where 1.1 and
        // 1.10000 are printed as written is a column the eye cannot read down.
        assertEquals("1.10000", TradingFormat.price(1.1))
        assertEquals("1.100", TradingFormat.price(1.1, digits = 3))
        assertEquals("—", TradingFormat.price(null))
    }

    @Test
    fun `no ledger key reaches the owner as a ledger key`() {
        for ((key, label) in TradingFormat.LEDGER_LABELS) {
            assertEquals(label, TradingFormat.label(key))
            assertFalse(label.contains('_'), "$key renders as $label")
        }
        assertEquals("Most you can lose on open trades", TradingFormat.label("max_open_stop_risk"))
    }

    @Test
    fun `an unknown key reads as awkward English rather than as a field name`() {
        assertEquals("Max open swap charge", TradingFormat.label("max_open_swap_charge"))
        assertFalse(TradingFormat.label("some_new_key").contains('_'))
    }

    @Test
    fun `no empty state tells the owner to open a terminal`() {
        // P3-AND-011. There is no phone on which `python -m vati lake` is an instruction a
        // person can follow.
        val states = listOf("current", "potential", "past", "accounts", "bars", "risk", "anything")
            .map(TradingFormat::emptyState) + TradingFormat.unavailableState(null) +
            TradingFormat.unavailableState("the gateway is unreachable")
        for (state in states) {
            assertTrue(state.isNotBlank())
            for (forbidden in listOf("python", "vati", "-m ", "cli", "terminal", "command line")) {
                assertFalse(state.lowercase().contains(forbidden), "\"$state\" contains $forbidden")
            }
            assertTrue(state.first().isUpperCase(), state)
            assertTrue(state.trimEnd().last() in ".!", state)
        }
    }

    @Test
    fun `empty and unavailable are never the same sentence`() {
        // "No open trades" when VAN cannot read the ledger is VAN reporting an absence it
        // has not established.
        assertTrue(
            TradingFormat.emptyState("current") != TradingFormat.unavailableState(null),
        )
        assertTrue(TradingFormat.unavailableState(null).contains("cannot read"))
        assertTrue(
            TradingFormat.unavailableState("the tunnel is down").contains("the tunnel is down"),
        )
    }
}
