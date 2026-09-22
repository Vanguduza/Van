package com.dial.van.trading

import com.dial.van.design.StatusSemantics
import com.dial.van.design.ThesisState
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * GAP-F-003 — the five trading intelligence read models
 * (`trading/vati/readmodels/active.py`), parsed and classified the same way the Android
 * screens read them: `ledger_available: false` never silently becomes an empty list, thesis
 * states map onto the design system's closed [ThesisState] set, and the History screen's
 * quadrant tally counts exactly the rows it was given.
 */
class TradingReadModelsTest {

    // ------------------------------------------------------------------------- thesis state

    @Test
    fun `ledger thesis states map onto the design system's closed set`() {
        assertEquals(ThesisState.CONFIRMED, TradingReadModels.thesisStateFor("CONFIRMED"))
        assertEquals(ThesisState.MONITORING, TradingReadModels.thesisStateFor("UNCHANGED"))
        assertEquals(ThesisState.WEAKENING, TradingReadModels.thesisStateFor("WEAKER"))
        assertEquals(ThesisState.WEAKENING, TradingReadModels.thesisStateFor("RISKIER"))
        assertEquals(ThesisState.WEAKENING, TradingReadModels.thesisStateFor("OVEREXTENDED"))
        assertEquals(ThesisState.INVALIDATED, TradingReadModels.thesisStateFor("INVALIDATED"))
        // Unknown/absent never reads as CONFIRMED — a claim that has not yet earned a
        // confirmed or weakening read is a hypothesis, not silently "good."
        assertEquals(ThesisState.HYPOTHESIS, TradingReadModels.thesisStateFor(null))
        assertEquals(ThesisState.HYPOTHESIS, TradingReadModels.thesisStateFor("SOMETHING_NEW"))
    }

    @Test
    fun `health never reads more favourable than the thesis, only as bad or worse`() {
        assertEquals(StatusSemantics.ROLE_CRITICAL, TradingReadModels.roleForHealth(ThesisState.CONFIRMED, "FAILING"))
        assertEquals(StatusSemantics.ROLE_DETERIORATING, TradingReadModels.roleForHealth(ThesisState.CONFIRMED, "IMPAIRED"))
        // Invalidated + impaired stays critical — impaired never downgrades an invalidated read.
        assertEquals(StatusSemantics.ROLE_CRITICAL, TradingReadModels.roleForHealth(ThesisState.INVALIDATED, "IMPAIRED"))
        assertEquals(StatusSemantics.ROLE_FAVOURABLE, TradingReadModels.roleForHealth(ThesisState.CONFIRMED, null))
    }

    // ---------------------------------------------------------------------------- materiality

    @Test
    fun `significant events keeps only materiality at or above threshold`() {
        val impacts = listOf(
            EventImpactRow(null, null, null, "EURUSD", 0.9, null, "war", null, 1L),
            EventImpactRow(null, null, null, "GBPUSD", 0.4, null, "rumour", null, 2L),
            EventImpactRow(null, null, null, "USDJPY", null, null, "unscored", null, 3L),
            EventImpactRow(null, null, null, "AUDUSD", 0.5, null, "at threshold", null, 4L),
        )
        val significant = TradingReadModels.significantImpacts(impacts)
        assertEquals(setOf("EURUSD", "AUDUSD"), significant.map { it.symbol }.toSet())
    }

    @Test
    fun `trust tier maps to a status role, never a raw colour`() {
        assertEquals(StatusSemantics.ROLE_FAVOURABLE, TradingReadModels.roleForTrust("HIGH"))
        assertEquals(StatusSemantics.ROLE_EVENT_RISK, TradingReadModels.roleForTrust("LOW"))
        assertEquals(StatusSemantics.ROLE_MONITOR, TradingReadModels.roleForTrust(null))
    }

    // ------------------------------------------------------------------------------ quadrant

    @Test
    fun `quadrant tally counts exactly the rows given, independent of a server total`() {
        val trades = listOf(
            closedTrade("a", "GOOD_DECISION_GOOD_OUTCOME"),
            closedTrade("b", "GOOD_DECISION_GOOD_OUTCOME"),
            closedTrade("c", "BAD_DECISION_BAD_OUTCOME"),
            closedTrade("d", null),
        )
        val tally = TradingReadModels.quadrantTally(trades)
        assertEquals(2, tally["GOOD_DECISION_GOOD_OUTCOME"])
        assertEquals(1, tally["BAD_DECISION_BAD_OUTCOME"])
        assertFalse(tally.containsKey(null.toString()))
        assertEquals(2, tally.size)
    }

    @Test
    fun `quadrant role never rewards a lucky bad decision as favourable`() {
        assertEquals(StatusSemantics.ROLE_FAVOURABLE, TradingReadModels.roleForQuadrant("GOOD_DECISION_GOOD_OUTCOME"))
        assertEquals(StatusSemantics.ROLE_EVENT_RISK, TradingReadModels.roleForQuadrant("BAD_DECISION_GOOD_OUTCOME"))
        assertEquals(StatusSemantics.ROLE_MONITOR, TradingReadModels.roleForQuadrant("GOOD_DECISION_BAD_OUTCOME"))
        assertEquals(StatusSemantics.ROLE_CRITICAL, TradingReadModels.roleForQuadrant("BAD_DECISION_BAD_OUTCOME"))
    }

    @Test
    fun `quadrant label reads as English`() {
        assertEquals("Good decision good outcome", TradingReadModels.quadrantLabel("GOOD_DECISION_GOOD_OUTCOME"))
        assertEquals("Unclassified", TradingReadModels.quadrantLabel(null))
    }

    private fun closedTrade(id: String, quadrant: String?) = ClosedTrade(
        tradeIntentId = id, strategyId = null, outcome = null, polarity = null, rMultiple = null,
        pnl = null, exitReason = null, closedMs = 0L,
        quadrant = quadrant?.let { TradeQuadrant(it, null, null, emptyList(), null, null, null) },
        attribution = null, lessons = emptyList(),
    )

    // ------------------------------------------------------------------------------- parsing

    @Test
    fun `positions parses the ledger's own shape, including a ledger-unavailable body`() {
        val body = """
            {"ledger_available": true, "count": 1, "positions": [
              {"trade_intent_id": "ti-1", "symbol": "EURUSD", "direction": "LONG",
               "strategy_id": "s1", "opened_ms": 1000,
               "exposure": {"entry": "1.1000", "quantity": "1.0", "approved_size": "0.5 lots",
                            "approved_risk_pct": "0.01", "portfolio_heat_after": "0.02"},
               "protection": {"stop": "1.0950", "confirmed": true, "at_or_beyond_break_even": false},
               "unrealised_r": "0.4",
               "thesis": {"seal": "abc", "statement": "trend continuation",
                          "expected_path": "up", "invalidation": "below 1.09",
                          "confirmation": "above 1.11", "adverse_signals": ["news"],
                          "event_sensitivity": "high", "original_approved_risk_pct": "0.01",
                          "created_ms": 500},
               "thesis_state": "CONFIRMED",
               "latest_assessment": {"state": "CONFIRMED", "previous_state": "MONITORING",
                                      "reasons": ["price above confirmation"], "reason_detail": null,
                                      "evidence": ["e1"], "event_materiality": "0.2",
                                      "argues_for_less": false, "assessed_ms": 900},
               "health": {"state": "HEALTHY", "reasons": [], "blocks_scaling": false,
                          "requires_preservation": false, "assessed_ms": 900},
               "latest_proposal": null,
               "linked_events": [{"headline_id": "h1", "headline_title": "Central bank speaks",
                                   "materiality": "0.6", "uncertainty": "0.1", "concern": "rates",
                                   "relevance_basis": "symbol", "at_ms": 800}]
              }
            ]}
        """.trimIndent()
        val parsed = PositionsReadModel.parse(body)
        assertNotNull(parsed)
        assertTrue(parsed.ledgerAvailable)
        assertEquals(1, parsed.positions.size)
        val row = parsed.positions.single()
        assertEquals("EURUSD", row.symbol)
        assertEquals(ThesisState.CONFIRMED, row.thesisState)
        assertEquals(0.4, row.unrealisedR)
        assertTrue(row.protectionConfirmed)
        assertEquals(1, row.linkedEvents.size)
        assertEquals("Central bank speaks", row.linkedEvents.single().headlineTitle)

        val empty = PositionsReadModel.parse("""{"ledger_available": false, "count": 0, "positions": []}""")
        assertNotNull(empty)
        assertFalse(empty.ledgerAvailable)
        assertTrue(empty.positions.isEmpty())
    }

    @Test
    fun `events parses both headline and calendar-release rows plus impacts`() {
        val body = """
            {"ledger_available": true, "count": 2,
             "events": [
               {"kind": "HEADLINE", "headline_id": "h1", "source_id": "reuters", "trust": "HIGH",
                "title": "War escalates", "currencies": ["USD"], "symbols": ["EURUSD"],
                "concern": "risk-off", "severity": "HIGH", "relayed_by": "news_ingress",
                "published_ms": 1000, "authority": "REDUCE_ONLY"},
               {"kind": "CALENDAR_RELEASE", "event_key": "nfp", "name": "Non-farm payrolls",
                "tier": 1, "currencies": ["USD"], "actual": "200k", "forecast": "180k",
                "status": "RELEASED", "usable": true, "published_ms": 2000,
                "authority": "BLACKOUT_AUTHORITY"}
             ],
             "impacts": [
               {"headline_id": "h1", "subject_kind": "SYMBOL", "subject_id": "EURUSD",
                "symbol": "EURUSD", "materiality": "0.8", "uncertainty": "0.1",
                "concern": "risk-off", "actionable": true, "at_ms": 1100}
             ]}
        """.trimIndent()
        val parsed = EventsReadModel.parse(body)
        assertNotNull(parsed)
        assertEquals(2, parsed.events.size)
        assertTrue(parsed.events[0].isHeadline)
        assertFalse(parsed.events[1].isHeadline)
        assertEquals(1, parsed.impacts.size)
        assertEquals(0.8, parsed.impacts.single().materiality)
    }

    @Test
    fun `potential parses candidates with risk requirement and invalidation`() {
        val body = """
            {"ledger_available": true, "count": 1, "potential_trades": [
              {"kind": "CANDIDATE", "symbol": "GBPUSD", "direction": "SHORT",
               "strategy_id": "s2", "entry": "1.30", "stop": "1.31", "cost_multiple": "2.5",
               "label": "SETUP", "reasons": ["breakdown"],
               "confidence": {"score": "0.62", "band": "MEDIUM"}, "assessed_ms": 700,
               "linked_events": [], "evidence_refs": ["ev1", "ev2"],
               "risk_requirement": {"capsule_risk_ceiling": "0.01", "stop": "1.31",
                                     "entry": "1.30", "valid_until_ms": 9999},
               "invalidation": {"stop": "1.31", "expires_ms": 9999}}
            ]}
        """.trimIndent()
        val parsed = PotentialReadModel.parse(body)
        assertNotNull(parsed)
        val candidate = parsed.trades.single()
        assertEquals("GBPUSD", candidate.symbol)
        assertEquals(ConfidenceBand.MEDIUM, candidate.confidence.band)
        assertEquals(2, candidate.evidenceRefs.size)
        assertNotNull(candidate.riskRequirement)
        assertNotNull(candidate.invalidation)
    }

    @Test
    fun `history parses closed trades with quadrant, attribution and lessons`() {
        val body = """
            {"ledger_available": true, "count": 1, "by_quadrant": {"GOOD_DECISION_GOOD_OUTCOME": 1},
             "history": [
               {"trade_intent_id": "ti-2", "strategy_id": "s1", "outcome": "WIN",
                "polarity": "POSITIVE", "r_multiple": "1.5", "pnl": "150.0",
                "exit_reason": "target", "closed_ms": 5000,
                "quadrant": {"quadrant": "GOOD_DECISION_GOOD_OUTCOME", "decision_quality": "GOOD",
                             "outcome_quality": "GOOD", "faults": [], "fault_detail": null,
                             "is_lucky": false, "is_unlucky": false},
                "attribution": {"realised": "150.0", "buckets": {"edge": "120.0", "cost": "-5.0"},
                                 "dominant_bucket": "edge", "counterfactual": "160.0"},
                "lessons": [{"lesson_id": "l1", "quadrant": "GOOD_DECISION_GOOD_OUTCOME",
                             "keep": "wait for confirmation", "avoid": null, "confidence": "0.7"}]}
             ]}
        """.trimIndent()
        val parsed = HistoryReadModel.parse(body)
        assertNotNull(parsed)
        assertEquals(1, parsed.byQuadrant["GOOD_DECISION_GOOD_OUTCOME"])
        val trade = parsed.trades.single()
        assertEquals(1.5, trade.rMultiple)
        assertEquals("edge", trade.attribution?.dominantBucket)
        assertEquals("wait for confirmation", trade.lessons.single().keep)
    }

    @Test
    fun `assessment reports the invoker state honestly, including unconfigured`() {
        val configured = """
            {"ledger_available": true, "urgent_risks": [], "portfolio_heat": "0.03",
             "max_open_stop_risk": "0.06", "available_risk": "0.03",
             "available_risk_note": "headroom", "open_positions": 2,
             "active_theses": {"CONFIRMED": 2}, "kill_switch_active": [],
             "cognition": {"cognition_invoker": "fable", "state": "READY"}}
        """.trimIndent()
        val parsed = AssessmentReadModel.parse(configured)
        assertNotNull(parsed)
        assertEquals("fable", parsed.cognition.invoker)
        assertEquals(0.5f, parsed.heatFraction)

        val unconfigured = """
            {"ledger_available": true, "urgent_risks": [], "portfolio_heat": null,
             "max_open_stop_risk": null, "available_risk": null, "available_risk_note": null,
             "open_positions": 0, "active_theses": {}, "kill_switch_active": [],
             "cognition": {"cognition_invoker": "none", "state": "MODEL_INVOKER_UNCONFIGURED"}}
        """.trimIndent()
        val parsedUnconfigured = AssessmentReadModel.parse(unconfigured)
        assertNotNull(parsedUnconfigured)
        assertEquals("MODEL_INVOKER_UNCONFIGURED", parsedUnconfigured.cognition.state)
        assertNull(parsedUnconfigured.heatFraction)
    }
}
