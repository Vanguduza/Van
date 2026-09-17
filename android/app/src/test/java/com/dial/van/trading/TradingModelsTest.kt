package com.dial.van.trading

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TradingModelsTest {

    private val portfolio = """
    {"ledger_available":true,"reporting_currency":"USD",
     "accounts":[{"alias":"paper_lab","label":"Paper Lab","broker":"PAPER","mode":"DEMO_TRADER","currency":"USD","safety_identity":"PAPER","equity":"10120.50","balance":"10000","floating_pnl":"120.50","day_pnl":"20.5","drawdown_pct":"0.0120","connection_state":"LIVE","open_positions":1,"kill_switch":[],"last_sync_ms":1757990000000},
                 {"alias":"ic_live","label":"IC Markets","broker":"MT5","mode":"LIMITED_LIVE","currency":"EUR","safety_identity":"LIVE","equity":"5000","balance":"5000","connection_state":"NEVER_SYNCED","open_positions":0,"kill_switch":["OWNER_HALT"]}],
     "totals":{"balance":"10000","equity":"10120.50","floating_pnl":"120.50","day_pnl":"20.5","week_pnl":"-3","accounts_in_reporting_currency":1,"accounts_in_other_currencies":["ic_live"]},
     "risk":{"portfolio_heat":"0.0125","kill_switch_active":["OWNER_HALT"],"open_trades":1},"exposure":{"by_symbol":{"EURUSD":1}},
     "recent_trades":[{"symbol":"EURUSD","direction":"LONG","strategy_id":"FX-TREND-PULLBACK-01","outcome":"GOOD_WIN","pnl":"42.1","r_multiple":"1.35","closed_ms":1757980000000,"confidence":{"score":"0.81","band":"HIGH"}}],
     "open_positions":[{"symbol":"EURUSD","direction":"LONG","strategy_id":"FX-LONDON-BREAKOUT-01","state":"OPEN","approved_size":"0.10","fill":"1.10210","protective_stop_price":"1.09900","protective_stop_confirmed":true,"opened_ms":1757991000000,"confidence":{"score":"0.7","band":"MEDIUM"}}],
     "potential_trades":[{"kind":"CANDIDATE","symbol":"XAUUSD","direction":"SHORT","strategy_id":"GOLD-TREND-POSITION-01","label":"WAIT","entry":"2340","stop":"2355","reasons":["regime in TRANSITION"],"assessed_ms":1757992000000,"confidence":{"score":"0.5","band":"MEDIUM"}}],
     "data_state":{"EURUSD":{"state":"LIVE"},"XAUUSD":{"state":"STALE"}}}
    """.trimIndent()

    @Test
    fun portfolioParsesTotalsAccountsSafetyAndWorstDataState() {
        val p = PortfolioSummary.parse(portfolio)!!
        assertEquals("10,120.50", p.equity.plain)
        assertEquals("+120.50", p.floatingPnl.signed)
        assertEquals("-3.00", p.weekPnl.signed)
        assertEquals(listOf("ic_live"), p.otherCurrencyAccounts)
        assertEquals(SafetyIdentity.PAPER, p.accounts[0].safety)
        assertEquals(SafetyIdentity.LIVE, p.accounts[1].safety)
        assertEquals(DataState.OFFLINE, p.accounts[1].connection)              // never synced is not "live"
        assertEquals("1.20%", p.accounts[0].drawdown.label)
        assertEquals(DataState.OFFLINE, p.overallDataState)                     // the worst state leads the headline
        assertEquals("1.25%", p.portfolioHeat.label)
        assertEquals(listOf("OWNER_HALT"), p.killSwitch)
        assertEquals(1, p.openPositions.size); assertEquals(TradeView.CURRENT, p.openPositions[0].view)
        assertEquals("WAIT", p.potential[0].state); assertEquals(ConfidenceBand.MEDIUM, p.potential[0].confidence.band)
        assertEquals("EURUSD long · +1.35R · +42.10", p.recent[0].headline)
        assertEquals(mapOf("EURUSD" to 1), p.exposureBySymbol)
        assertNull(PortfolioSummary.parse("nope"))
    }

    @Test
    fun marketStateRiskBarsAndDetailParse() {
        val ms = MarketStateCard.parseAll("""{"symbols":[{"symbol":"EURUSD","as_of_ms":1,"session":"LONDON","regime":{"trend":"BULL","vol":"NORMAL","phase":"NORMAL","confidence":"0.8"},"integrity":"NORMAL","event_window":"NONE","minutes_to_next_event":95,"quote_age_ms":120,"data_state":{"state":"LIVE"},"last_decision":{"decision":"NO_TRADE","reason":"x"},"van_summary":"EURUSD: bull trend","features":{"atr":"0.0012","rsi":"61.2"}}]}""")
        assertEquals(1, ms.size); assertEquals("BULL", ms[0].trend); assertEquals(95, ms[0].minutesToEvent); assertEquals("0.0012", ms[0].features["atr"]); assertEquals(DataState.LIVE, ms[0].dataState)
        val rk = RiskView.parse("""{"as_of_ms":5,"portfolio_heat":"0.03","equity":"10000","drawdown_from_peak_pct":"0.02","day_pnl_pct":"-0.01","week_pnl_pct":"0.0","limits":{"max_open_stop_risk":"0.06","max_daily_loss":"0.05"},"kill_switch":[],"consecutive_losses":2,"open_trades":2,
            "concentration":{"by_symbol":{"EURUSD":"0.02","XAUUSD":"0.01"},"by_currency":{"EUR":"0.02","USD":"0.03","XAUUSD":"0.01"},"by_direction":{"LONG":2}},"positions":[{"trade_intent_id":"i1","symbol":"EURUSD","direction":"LONG","approved_risk_pct":"0.02","approved_size":"0.1","stop":"1.09","state":"OPEN"}],"last_decision":{"decision":"REJECTED","reason_code":"MAX_OPEN_STOP_RISK"}}""")!!
        assertEquals(0.5, rk.heatUtilisation!!, 1e-9)
        assertEquals("3.00%", rk.portfolioHeat.label); assertEquals(2, rk.consecutiveLosses); assertEquals("MAX_OPEN_STOP_RISK", rk.lastReasonCode); assertEquals("2.00%", rk.positions[0].riskPct.label)
        val bs = BarSeries.parse("""{"symbol":"EURUSD","timeframe":"H1","bars":[{"t":1,"o":"1.1","h":"1.2","l":"1.0","c":"1.15","v":"3"},{"t":2,"o":"x"}],"count":2,"provenance":["SYNTHETIC"],"data_state":{"state":"LIVE"},"lake_available":true}""")!!
        assertEquals(1, bs.bars.size); assertTrue(bs.isSimulated); assertEquals(DataState.LIVE, bs.dataState)
        assertEquals(DataState.OFFLINE, BarSeries.parse("""{"symbol":"EURUSD","timeframe":"H1","bars":[],"lake_available":false,"data_state":{"state":"UNAVAILABLE"}}""")!!.dataState)
        val d = TradeDetail.parse("""{"trade_intent_id":"i1","symbol":"EURUSD","direction":"LONG","strategy_id":"FX-TREND-PULLBACK-01","state":"CLOSED","outcome":"GOOD_WIN","pnl":"42.1","r_multiple":"1.35","closed_ms":9,"decided_ms":1,"opened_ms":2,"risk_decision":"APPROVED","approved_size":"0.1","approved_risk_pct":"0.005",
            "confidence":{"score":"0.81","band":"HIGH"},"levels":{"entry":"1.1","fill":"1.1001","stop":"1.095","target":"1.11","exit":"1.108"},"review":{"lessons":["exit: TARGET"]},"multipliers":{"regime_multiplier":"1"},
            "timeline":[{"at_ms":1,"kind":"RISK_DECISION","text":"approved","hash":"a"},{"at_ms":2,"kind":"EXECUTION","text":"filled","hash":"b"}],"van_interpretation":["Confidence 0.81 (HIGH)"],"chart":{"timeframe":"H1","bars":[{"t":1,"o":"1.1","h":"1.11","l":"1.09","c":"1.105"}],"markers":[{"at_ms":2,"kind":"ENTRY","price":"1.1001"}]},"decision_hash":"deadbeef00","account_alias":"paper_lab"}""")!!
        assertEquals(TradeView.PAST, d.view); assertEquals("EURUSD long · +1.35R · +42.10", d.row.headline); assertEquals(1.095, d.stop!!, 1e-9); assertEquals(listOf("exit: TARGET"), d.lessons)
        assertEquals(2, d.timeline.size); assertEquals("ENTRY", d.markers[0].kind); assertEquals("H1", d.chartTimeframe); assertEquals("deadbeef", TradingFormat.hash8(d.decisionHash)); assertEquals("paper_lab", d.accountAlias)
        assertEquals(1.6, ChartGeometry.riskReward(1.1, 1.095, 1.108)!!, 1e-9)
        assertNull(TradeDetail.parse("{}"))
    }

    @Test
    fun formatHelpers() {
        assertEquals("1.10210", TradingFormat.price(1.1021)); assertEquals("2,340.50", Money.of("2340.5").plain); assertEquals("—", Money.of(null).signed)
        assertEquals(3, TradingFormat.digitsFor("USDJPY")); assertEquals(2, TradingFormat.digitsFor("XAUUSD")); assertEquals(5, TradingFormat.digitsFor("EURUSD")); assertEquals(2, TradingFormat.digitsFor("DELTA"))
        assertEquals("+1.35R", TradingFormat.r(1.35)); assertEquals("5m ago", TradingFormat.age(600_000, 300_000)); assertEquals("never", TradingFormat.age(1, null))
        assertEquals("12:30", TradingFormat.timeHm(45_000_000L)); assertEquals("01 Jan", TradingFormat.dateShort(0L))
        assertEquals(SafetyIdentity.READ_ONLY, SafetyIdentity.parse("READ ONLY")); assertEquals(DataState.UNKNOWN, DataState.parse("weird"))
    }
}
