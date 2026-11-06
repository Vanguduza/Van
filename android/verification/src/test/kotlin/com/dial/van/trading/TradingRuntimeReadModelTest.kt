package com.dial.van.trading

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class TradingRuntimeReadModelTest {
    private val now = 1_000_000L
    private val current = TradingRuntimeReadModel(true, true, false, now - 100, null, false, emptyList(), "chain-1")
    @Test fun `live requires available verified nonstale ledger with real current event time`() {
        assertEquals(TradingRuntimeReadModel.Freshness.LIVE, current.freshness(now))
        assertEquals(TradingRuntimeReadModel.Freshness.OFFLINE, current.copy(ledgerAvailable = false).freshness(now))
        for (changed in listOf(current.copy(chainOk = false), current.copy(chainOk = null),
            current.copy(stale = null), current.copy(lastEventMs = null), current.copy(lastEventMs = 0), current.copy(lastEventMs = now + 1))) {
            assertEquals(TradingRuntimeReadModel.Freshness.UNKNOWN, changed.freshness(now))
        }
        assertEquals(TradingRuntimeReadModel.Freshness.STALE, current.copy(stale = true).freshness(now))
        assertEquals(TradingRuntimeReadModel.Freshness.STALE,
            current.copy(lastEventMs = now - TradingReadModels.LEDGER_STALENESS_MS).freshness(now))
    }
    @Test fun `halt state comes from owner trigger and never from another active switch`() {
        assertFalse(current.ownerHaltRecorded!!)
        assertNull(current.copy(killSwitchActive = null).ownerHaltRecorded)
        assertFalse(current.copy(killSwitchActive = true, killSwitchTriggers = listOf("DAILY_LOSS")).ownerHaltRecorded!!)
        assertTrue(current.copy(killSwitchActive = true, killSwitchTriggers = listOf("OWNER_HALT")).ownerHaltRecorded!!)
    }
    @Test fun `missing runtime fields remain unknown and do not become successful defaults`() {
        val unavailable = TradingRuntimeReadModel.parse("""{"ledger_available":false,"chain_ok":null,"kill_switch_active":null}""")!!
        assertEquals(TradingRuntimeReadModel.Freshness.OFFLINE, unavailable.freshness(now))
        assertNull(unavailable.killSwitchActive)
        assertNull(TradingRuntimeReadModel.parse("{}"))
        val partial = TradingRuntimeReadModel.parse("""{"ledger_available":true,"chain_ok":true}""")!!
        assertEquals(TradingRuntimeReadModel.Freshness.UNKNOWN, partial.freshness(now))
    }
    @Test fun `parse failures are source unavailable and independent loads still run`() = runBlocking {
        val malformed = loadTradingData<String>(parse = { throw IllegalArgumentException("malformed section") }, call = { "body" })
        val next = loadTradingData(parse = { it }, call = { "healthy source" })
        assertTrue(malformed is Loaded.Unavailable)
        assertEquals("healthy source", (next as Loaded.Ready).value)
    }
    @Test fun `trading cancellation is not swallowed as an unavailable ledger`() {
        assertFailsWith<CancellationException> { runBlocking {
            loadTradingData(parse = { it }, call = { throw CancellationException("gone") })
        } }
    }
}
