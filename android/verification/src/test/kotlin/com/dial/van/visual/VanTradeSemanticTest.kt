package com.dial.van.visual

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * P1-AURA-003 — trading state reaches VAN's semantic and visual state.
 *
 * The eight trade aura families existed and their only caller was the PNG board generator.
 * The live trading screen derived VAN's presence from the *degraded-code set*, so whether
 * VAN looked calm or alarmed while the owner's money was at risk depended on whether some
 * subsystem was reporting a fault.
 */
class VanTradeSemanticTest {

    private fun live(
        positions: Int = 0,
        pnl: Double? = null,
        margin: Double? = null,
        refusals: Int = 0,
        halt: Boolean = false,
        triggers: List<String> = emptyList(),
        orders: Int = 0,
        setups: Int = 0,
        watched: Int = 0,
    ) = VanTradeSignals(
        ledgerAvailable = true, ledgerStale = false, ownerHaltActive = halt,
        killSwitchTriggers = triggers, openPositions = positions, workingOrders = orders,
        pendingSetups = setups, watchedInstruments = watched, unrealizedPnl = pnl,
        marginLevelPct = margin, riskRefusalsRecent = refusals,
    )

    @Test
    fun `an owner halt outranks everything`() {
        assertEquals(
            VanTradeSemantic.HALTED,
            VanTradeSemantics.classify(live(positions = 3, pnl = 5000.0, halt = true)),
        )
    }

    @Test
    fun `a ledger VAN cannot read is UNKNOWN and never FLAT`() {
        // The audit's recurring failure, in the visuals: absence of evidence rendered as
        // evidence of calm.
        val unreadable = VanTradeSignals(ledgerAvailable = false, ledgerStale = false)
        val stale = VanTradeSignals(ledgerAvailable = true, ledgerStale = true)
        assertEquals(VanTradeSemantic.UNKNOWN, VanTradeSemantics.classify(unreadable))
        assertEquals(VanTradeSemantic.UNKNOWN, VanTradeSemantics.classify(stale))
        assertNotEquals(VanTradeSemantic.FLAT, VanTradeSemantics.classify(stale))
    }

    @Test
    fun `a default signal set is UNKNOWN, not FLAT`() {
        // Defaults matter: a screen that has not loaded yet must not show a calm field.
        assertEquals(VanTradeSemantic.UNKNOWN, VanTradeSemantics.classify(VanTradeSignals()))
    }

    @Test
    fun `risk pressure outranks profit on the same position`() {
        val profitable = live(positions = 1, pnl = 400.0)
        assertEquals(VanTradeSemantic.PROFIT, VanTradeSemantics.classify(profitable))
        assertEquals(
            VanTradeSemantic.RISK,
            VanTradeSemantics.classify(profitable.copy(marginLevelPct = 150.0)),
        )
        assertEquals(
            VanTradeSemantic.RISK,
            VanTradeSemantics.classify(profitable.copy(riskRefusalsRecent = 1)),
        )
    }

    @Test
    fun `the margin threshold matches the risk authority's floor`() {
        // The owner should not learn about the floor from a refusal they did not see coming.
        val atFloor = live(positions = 1, margin = VanTradeSemantics.MARGIN_PRESSURE_PCT)
        val belowFloor = live(positions = 1, margin = VanTradeSemantics.MARGIN_PRESSURE_PCT - 1)
        assertEquals(VanTradeSemantic.IN_TRADE, VanTradeSemantics.classify(atFloor))
        assertEquals(VanTradeSemantic.RISK, VanTradeSemantics.classify(belowFloor))
        assertEquals(200.0, VanTradeSemantics.MARGIN_PRESSURE_PCT)
    }

    @Test
    fun `the quiet ladder is watching then setup then entry`() {
        assertEquals(VanTradeSemantic.FLAT, VanTradeSemantics.classify(live()))
        assertEquals(VanTradeSemantic.WATCHING, VanTradeSemantics.classify(live(watched = 3)))
        assertEquals(VanTradeSemantic.SETUP, VanTradeSemantics.classify(live(watched = 3, setups = 1)))
        assertEquals(
            VanTradeSemantic.ENTRY,
            VanTradeSemantics.classify(live(watched = 3, setups = 1, orders = 1)),
        )
    }

    @Test
    fun `a kill switch is a stop`() {
        assertEquals(
            VanTradeSemantic.STOP,
            VanTradeSemantics.classify(live(positions = 1, triggers = listOf("DAILY_LOSS_LIMIT"))),
        )
    }

    @Test
    fun `every semantic has its own Zone C topology and no two look the same`() {
        val seen = mutableSetOf<Pair<Int?, List<VanAuraEnvelopeSegment>>>()
        for (semantic in VanTradeSemantic.entries) {
            if (semantic == VanTradeSemantic.FLAT) continue        // FLAT is plain idle
            if (semantic == VanTradeSemantic.UNKNOWN) continue     // shares HALTED's alarm
            val aura = VanTradeSemantics.auraFor(semantic)
            val key = aura.semanticColor to aura.envelopeSegments
            assertTrue(seen.add(key), "$semantic reuses another family's appearance")
        }
    }

    @Test
    fun `semantic colour never lands on VAN's body`() {
        // Rev 2.2: Zone C carries meaning; a trade in profit does not turn VAN green.
        for (semantic in VanTradeSemantic.entries) {
            val aura = VanTradeSemantics.auraFor(semantic)
            assertTrue(
                aura.envelopeCoverageDeg() <= VanAuraSpec.MAX_ENVELOPE_COVERAGE_DEG,
                "$semantic covers ${aura.envelopeCoverageDeg()}° of the outer field",
            )
            assertTrue(aura.faceSafe, "$semantic exceeds the face-safe intensity ceiling")
        }
    }

    @Test
    fun `only the states the owner has to act on move VAN's pose`() {
        // A position quietly in profit is Zone C news, not a reason for VAN to change
        // posture at the owner all day.
        assertNull(VanTradeSemantics.durableStateFor(VanTradeSemantic.PROFIT))
        assertNull(VanTradeSemantics.durableStateFor(VanTradeSemantic.IN_TRADE))
        assertNull(VanTradeSemantics.durableStateFor(VanTradeSemantic.WATCHING))
        assertNotNull(VanTradeSemantics.durableStateFor(VanTradeSemantic.HALTED))
        assertNotNull(VanTradeSemantics.durableStateFor(VanTradeSemantic.RISK))
        assertNotNull(VanTradeSemantics.durableStateFor(VanTradeSemantic.UNKNOWN))
    }

    @Test
    fun `a published trade state reaches the semantic field`() {
        val frame = VanPresenceReducer.trade(VanPresenceFrame(), VanTradeSemantic.RISK)
        assertEquals(VanTradeSemantic.RISK, frame.trade)
        assertEquals(VanDurableState.WARNING, frame.semanticState)
        // And not the pose: semantic colour stays in Zone C.
        assertEquals(VanDurableState.IDLE, frame.poseState)
    }

    @Test
    fun `an owner approval outranks a market`() {
        val waiting = VanPresenceReducer.authority(
            VanPresenceFrame(trade = VanTradeSemantic.RISK),
            VanAuthorityState.WAITING_FOR_OWNER,
        )
        assertEquals(VanDurableState.WAITING_FOR_OWNER, waiting.semanticState)
    }

    @Test
    fun `a calm market does not overwrite a degraded subsystem`() {
        val degraded = VanPresenceFrame(
            health = VanHealthState.DEGRADED, trade = VanTradeSemantic.PROFIT,
        )
        assertEquals(VanDurableState.DEGRADED, degraded.semanticState)
    }

    @Test
    fun `clearing the trade state restores ordinary health truth`() {
        val withTrade = VanPresenceFrame(trade = VanTradeSemantic.HALTED)
        assertEquals(VanDurableState.WAITING_FOR_OWNER, withTrade.semanticState)
        val cleared = VanPresenceReducer.trade(withTrade, null)
        assertEquals(VanDurableState.IDLE, cleared.semanticState)
    }

    @Test
    fun `the capability board and the running app draw the same families`() {
        // The board adapter is a string lookup over the same enum, so a poster and the app
        // cannot drift apart.
        for (semantic in VanTradeSemantic.entries) {
            if (semantic.boardKey.isEmpty()) continue  // a family with no board panel
            val viaBoard = VanAuraSpecs.tradePreview(semantic.boardKey)
            val viaSemantic = VanTradeSemantics.auraFor(semantic)
            assertEquals(
                viaSemantic.envelopeSegments, viaBoard.envelopeSegments,
                "$semantic differs between the board and the app",
            )
        }
        // A flat book has no board panel, and must not silently resolve to another family's.
        assertTrue(VanTradeSemantic.FLAT.boardKey.isEmpty())
    }

    @Test
    fun `every semantic says something a person would say`() {
        for (semantic in VanTradeSemantic.entries) {
            val line = VanTradeSemantics.headlineFor(semantic)
            assertTrue(line.isNotBlank() && line.first().isUpperCase(), "$semantic: $line")
            assertTrue(semantic.name !in line, "$semantic leaks its enum name to the owner")
        }
    }

    // ---- Aura Rev 2 (CF-D-08): the trading field is live, and each family has its own energy ----

    @Test
    fun `a live trade reaches the aura unless authority or health outranks it`() {
        val profit = VanPresenceReducer.trade(VanPresenceFrame(), VanTradeSemantic.PROFIT).toVisualState()
        assertEquals(VanTradeSemantic.PROFIT, profit.trade)
        assertEquals(VanTradeSemantics.auraFor(VanTradeSemantic.PROFIT), VanAuraSpecs.semanticSpecFor(profit))
        val approval = VanPresenceReducer.authority(VanPresenceFrame(trade = VanTradeSemantic.RISK), VanAuthorityState.WAITING_FOR_OWNER)
        assertNull(approval.toVisualState().trade, "an owner approval must outrank the market in the field")
        val offline = VanPresenceFrame(health = VanHealthState.OFFLINE, trade = VanTradeSemantic.PROFIT)
        assertNull(offline.toVisualState().trade)
        val degradedCalm = VanPresenceFrame(health = VanHealthState.DEGRADED, trade = VanTradeSemantic.PROFIT)
        assertNull(degradedCalm.toVisualState().trade, "a degraded subsystem outranks a calm market")
    }

    @Test
    fun `closing a live position pulses the field once`() {
        var frame = VanPresenceReducer.trade(VanPresenceFrame(), VanTradeSemantic.IN_TRADE)
        frame = VanPresenceReducer.trade(frame, VanTradeSemantic.PROFIT)
        assertEquals(0, frame.tradeClosePulse, "moving between live states is not a close")
        frame = VanPresenceReducer.trade(frame, VanTradeSemantic.FLAT)
        assertEquals(1, frame.toVisualState().auraPulseGeneration)
        frame = VanPresenceReducer.trade(frame, VanTradeSemantic.WATCHING)
        assertEquals(1, frame.tradeClosePulse, "a flat book becoming watched is not a close")
        frame = VanPresenceReducer.trade(frame, VanTradeSemantic.STOP)
        assertEquals(1, frame.tradeClosePulse, "a stop firing is an alarm, not a celebration pulse")
    }

    @Test
    fun `each trade family carries its own flame energy`() {
        val calm = VanTradeSemantics.auraFor(VanTradeSemantic.IN_TRADE)
        val risk = VanTradeSemantics.auraFor(VanTradeSemantic.RISK)
        val stop = VanTradeSemantics.auraFor(VanTradeSemantic.STOP)
        val entry = VanTradeSemantics.auraFor(VanTradeSemantic.ENTRY)
        assertTrue(risk.deformation > calm.deformation, "risk must be more turbulent than a calm trade")
        assertTrue(stop.intensity > risk.intensity && stop.arcActivity > risk.arcActivity, "a stop is the highest-energy field")
        assertTrue(entry.sparkRate > calm.sparkRate, "an opportunity sheds more particles")
        val low = VanTradeSemantics.auraFor(VanTradeSemantic.STOP, VanEffectBudget.LOW)
        assertTrue(low.sparkRate < stop.sparkRate, "trade fields must honour the effect budget")
    }
}
