package com.dial.van.trading

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class TradingNavigationTest {
    @Test
    fun `the overlay views open their corresponding existing screen`() {
        assertEquals("positions", TradingNavigation.resolveRoute("trades/CURRENT"))
        assertEquals("history", TradingNavigation.resolveRoute("trades/PAST"))
        assertEquals("potential", TradingNavigation.resolveRoute("trades/POTENTIAL"))
    }

    @Test
    fun `a selected trade retains its exact ID in the detail destination`() {
        val id = "closed-trade_4.abc-123"
        assertEquals("positions/$id", TradingNavigation.resolveRoute("trade/$id"))
        assertEquals("positions/$id", TradingNavigation.resolveRoute("positions/$id"))
    }

    @Test
    fun `unknown or malformed links fall back to overview`() {
        for (route in listOf(null, "", "trades/UNKNOWN", "trade/", "trade/a/b", "trade/a?b", "arbitrary")) {
            assertEquals(TradingNavigation.ROOT, TradingNavigation.resolveRoute(route))
            assertNull(TradingNavigation.launchDestination(route, alreadyHandled = false))
        }
    }

    @Test
    fun `launch links navigate after the overview root and restored links do not repeat`() {
        assertEquals("overview", TradingNavigation.ROOT)
        for (requested in listOf("trades/CURRENT", "trades/PAST", "trades/POTENTIAL", "trade/closed-trade-123")) {
            assertEquals(TradingNavigation.resolveRoute(requested), TradingNavigation.launchDestination(requested, alreadyHandled = false))
            assertNull(TradingNavigation.launchDestination(requested, alreadyHandled = true))
        }
        assertNull(TradingNavigation.launchDestination("overview", alreadyHandled = false))
    }
}
