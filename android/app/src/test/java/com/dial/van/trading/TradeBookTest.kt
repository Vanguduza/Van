package com.dial.van.trading

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The overlay trade preview must show the ledger truth, never invent a score, and never carry an action. */
class TradeBookTest {

    private val book = """
    {"view":"all","ledger_available":true,"confidence_basis":"RULES_V0_UNCALIBRATED: display/ranking only, never a size",
     "past":[{"symbol":"EURUSD","direction":"LONG","strategy_id":"FX-TREND-PULLBACK-01","outcome":"GOOD_WIN","exit_reason":"TARGET","pnl":"42.10","r_multiple":"1.35",
              "closed_ms":1757990000000,"confidence":{"score":"0.81","band":"HIGH","basis":"x"},"lessons":["exit: TARGET"]},
             {"symbol":"XAUUSD","direction":"SHORT","strategy_id":"GOLD-TREND-POSITION-01","outcome":"GOOD_LOSS","pnl":"-30","r_multiple":"-1.00","closed_ms":1757980000000,
              "confidence":{"score":"0.40"}}],
     "current":[{"symbol":"DELTA","direction":"LONG","strategy_id":"ZSE-VALUE-ROTATION-01","state":"AWAITING_OWNER_TICKET","approved_size":"1200","fill":null,"stop":"23.50",
                 "protective_stop_confirmed":true,"owner_ticket":{"ticket":"ZSE-T-1","status":"OPEN"},"decided_ms":1500,"confidence":{"score":"0.65","band":"MEDIUM","basis":"x"}},
                {"symbol":"EURUSD","direction":"LONG","strategy_id":"FX-LONDON-BREAKOUT-01","state":"OPEN","approved_size":"0.10","fill":"1.10210","protective_stop_price":"1.09900",
                 "protective_stop_confirmed":false,"owner_ticket":null,"opened_ms":1757991000000,"confidence":{"score":"0.20","band":"MINIMAL","basis":"x"}}],
     "potential":[{"kind":"CANDIDATE","symbol":"EURUSD","direction":"LONG","strategy_id":"FX-TREND-PULLBACK-01","label":"WAIT","entry":"1.1000","stop":"1.0980","cost_multiple":"4.6667",
                   "reasons":["regime in TRANSITION"],"assessed_ms":1757992000000,"confidence":{"score":"0.55","band":"MEDIUM","basis":"x"}},
                  {"kind":"RISK_REJECTED","symbol":"EURUSD","direction":"SHORT","strategy_id":"FX-EVENT-DRIFT-01","label":"REJECTED:MAX_POSITIONS_PER_INSTRUMENT","reasons":["already 1 open"],
                   "decided_ms":1757991500000,"confidence":{"score":"0.90","band":"HIGH","basis":"x"}}],
     "counts":{"past":2,"current":2,"potential":2}}
    """.trimIndent()

    @Test
    fun pastRowsCarryOutcomeRAndConfidence() {
        val st = TradeBookParser.parse(TradeView.PAST, book) as TradeBookState.Ready
        assertEquals(2, st.rows.size)
        val w = st.rows[0]
        assertEquals("EURUSD long · +1.35R · +42.10", w.headline)
        assertEquals("GOOD_WIN · exit TARGET · FX-TREND-PULLBACK", w.detail)
        assertEquals(ConfidenceBand.HIGH, w.confidence.band)
        assertEquals("81%", w.confidence.percentLabel)
        assertEquals(listOf("exit: TARGET"), w.reasons)
        // band derived from the score when the gateway omits it; same thresholds as the backend
        val l = st.rows[1]
        assertEquals(ConfidenceBand.LOW, l.confidence.band)
        assertEquals("XAUUSD short · -1.00R · -30.00", l.headline)
        assertTrue(st.basis.contains("never a size"))
    }

    @Test
    fun currentRowsShowTicketAndUnconfirmedStopLoudly() {
        val st = TradeBookParser.parse(TradeView.CURRENT, book) as TradeBookState.Ready
        val zse = st.rows[0]
        assertEquals("AWAITING_OWNER_TICKET", zse.state)
        assertEquals("DELTA long · size 1200 · AWAITING_OWNER_TICKET", zse.headline)
        assertEquals("stop 23.50 · ticket ZSE-T-1 OPEN · ZSE-VALUE-ROTATION", zse.detail)
        assertEquals("65%", zse.confidence.percentLabel)
        val fx = st.rows[1]
        assertTrue(fx.detail.contains("STOP NOT CONFIRMED"))
        assertEquals(ConfidenceBand.MINIMAL, fx.confidence.band)
        assertEquals(1757991000000L, fx.timestampMs)
    }

    @Test
    fun potentialRowsIncludeCandidatesAndRiskRejections() {
        val st = TradeBookParser.parse(TradeView.POTENTIAL, book) as TradeBookState.Ready
        assertEquals(listOf("WAIT", "REJECTED:MAX_POSITIONS_PER_INSTRUMENT"), st.rows.map { it.state })
        assertEquals("entry 1.1000 · stop 1.0980 · edge 4.7× cost · FX-TREND-PULLBACK", st.rows[0].detail)
        assertEquals(listOf("regime in TRANSITION"), st.rows[0].reasons)
        assertEquals(ConfidenceBand.HIGH, st.rows[1].confidence.band)
    }

    @Test
    fun missingLedgerAndGarbageFailClosedWithoutInventingRows() {
        val empty = TradeBookParser.parse(TradeView.CURRENT, """{"view":"current","ledger_available":false,"current":[],"counts":{"current":0}}""") as TradeBookState.Ready
        assertFalse(empty.ledgerAvailable)
        assertTrue(empty.rows.isEmpty())
        val bad = TradeBookParser.parse(TradeView.PAST, "<html>502</html>")
        assertTrue(bad is TradeBookState.Unavailable)
        val noConf = TradeBookParser.parse(TradeView.PAST, """{"past":[{"symbol":"EURUSD","direction":"LONG","strategy_id":"S-01"}]}""") as TradeBookState.Ready
        assertEquals(ConfidenceBand.UNKNOWN, noConf.rows[0].confidence.band)
        assertEquals("n/a", noConf.rows[0].confidence.percentLabel)
        assertEquals("EURUSD long · R n/a · P&L n/a", noConf.rows[0].headline)
    }

    @Test
    fun bandThresholdsMatchBackend() {
        assertEquals(ConfidenceBand.HIGH, ConfidenceBand.forScore(0.75))
        assertEquals(ConfidenceBand.MEDIUM, ConfidenceBand.forScore(0.50))
        assertEquals(ConfidenceBand.LOW, ConfidenceBand.forScore(0.25))
        assertEquals(ConfidenceBand.MINIMAL, ConfidenceBand.forScore(0.2499))
        assertEquals(ConfidenceBand.UNKNOWN, ConfidenceBand.parse("whatever"))
    }

    @Test
    fun surfaceHasNoActionVocabulary() {
        // The preview surface is read-only by construction: no row type exposes an order/size/cancel affordance.
        val names = TradeRow::class.java.declaredFields.map { it.name.lowercase() }
        listOf("order", "submit", "cancel", "modify", "size").forEach { banned ->
            assertFalse("TradeRow must not carry '$banned'", names.any { it.contains(banned) })
        }
    }
}
