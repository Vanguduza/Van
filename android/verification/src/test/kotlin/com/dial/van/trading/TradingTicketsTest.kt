package com.dial.van.trading

import org.json.JSONObject
import kotlin.test.*
import kotlin.test.Test

class TradingTicketsTest {
    private fun ticket(status: String = "OPEN") = TradingTicket("ZSE-T-1", "DELTA", "BUY", "1200", status, null, null, null, null)
    @Test fun missingLedgerObservationIsUnavailable() {
        assertNull(TradingTicketList.parse("{\"tickets\":[]}"))
        assertNull(TradingTicketList.parse("{\"ledger_available\":true}"))
        assertFalse(TradingTicketList.parse("{\"ledger_available\":false,\"tickets\":[]}")!!.ledgerAvailable)
    }
    @Test fun malformedRowDoesNotBecomeEmptyTickets() {
        assertNull(TradingTicketList.parse("{\"ledger_available\":true,\"tickets\":[{}]}"))
    }
    @Test fun commandPreservesExactNoteAndCanonicalAmounts() {
        val prepared = TradingTicketConfirmation.prepare(ticket(), "25.1000", "1100.00", "CN \"quoted\" \\ reference")
        val body = JSONObject(prepared.commandText().removePrefix(TradingTicketConfirmation.COMMAND_PREFIX))
        assertEquals("25.1", body.getString("fill_price"))
        assertEquals("1100", body.getString("filled_qty"))
        assertEquals("CN \"quoted\" \\ reference", body.getString("contract_note_ref"))
        assertEquals("ZSE-T-1", body.getString("ticket_id"))
    }
    @Test fun rejectsInvalidOrUnboundedAmountsAndOverfill() {
        for (price in listOf("NaN", "Infinity", "1e9999999", "-1", "0", "0.123456789")) {
            assertTrue(runCatching { TradingTicketConfirmation.prepare(ticket(), price, "100", "note") }.isFailure)
        }
        assertTrue(runCatching { TradingTicketConfirmation.prepare(ticket(), "1", "1201", "note") }.isFailure)
    }
    @Test fun rejectsConfirmedTicketAndEmptyNote() {
        assertTrue(runCatching { TradingTicketConfirmation.prepare(ticket("CONFIRMED"), "1", "1", "note") }.isFailure)
        assertTrue(runCatching { TradingTicketConfirmation.prepare(ticket(), "1", "1", "  ") }.isFailure)
    }
}
