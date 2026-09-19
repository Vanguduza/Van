package com.dial.van.runtime

import com.dial.van.visual.VanEffectBudget
import com.dial.van.visual.VanEffectConditions
import com.dial.van.visual.VanEffectPolicy
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * P3-PERF-003 — the envelope, executed rather than reasoned about.
 *
 * The finding said each subsystem had its own budget and nothing owned the sum. Only the
 * visual layer had a budget at all; the rest ran at a fixed cost whatever the phone was
 * doing. These tests are written against the ways an envelope can look correct and leave
 * the owner worse off:
 *
 * - one that reads the latest signal instead of the worst, so a hot phone reporting a
 *   battery reading drops back to NOMINAL while still throttling;
 * - one where being on a charger clears thermal pressure, which is exactly backwards;
 * - one that throttles the wake word, so the owner says "Hey Van", nothing happens, and the
 *   cause is the mechanism meant to protect them;
 * - one that trades the owner's reduced-motion accessibility setting for a few milliwatts;
 * - one that can raise a subsystem's own budget rather than only lowering it.
 */
class VanResourceEnvelopeTest {

    private fun nominal() = RuntimeReading(batteryPercent = 90, freeStorageBytes = 8L shl 30)

    // ---- pressure is the worst input -------------------------------------------

    @Test
    fun `a healthy device is nominal and says nothing`() {
        val state = VanResourceEnvelope.evaluate(nominal())
        assertEquals(RuntimePressure.NOMINAL, state.pressure)
        assertEquals(emptyList(), state.reasons)
    }

    @Test
    fun `pressure is the worst input and not the last one`() {
        // Severe thermal (CRITICAL) alongside a perfectly good battery (NOMINAL).
        val state = VanResourceEnvelope.evaluate(
            nominal().copy(thermalStatus = VanResourceEnvelope.THERMAL_SEVERE),
        )
        assertEquals(RuntimePressure.CRITICAL, state.pressure)
        assertEquals(listOf("thermal"), state.reasons)
    }

    @Test
    fun `every input that reached the winning level is named`() {
        val state = VanResourceEnvelope.evaluate(
            nominal().copy(
                batteryPercent = 15,
                powerSaveMode = true,
                freeStorageBytes = 100L * 1024 * 1024,
            ),
        )
        assertEquals(RuntimePressure.CONSTRAINED, state.pressure)
        // A CONSTRAINED with no reason is a number nobody can argue with or act on.
        assertEquals(listOf("battery", "power_save", "storage"), state.reasons)
    }

    @Test
    fun `charging clears battery pressure and nothing else`() {
        val flat = nominal().copy(batteryPercent = 3)
        assertEquals(RuntimePressure.SURVIVAL, VanResourceEnvelope.evaluate(flat).pressure)
        assertEquals(
            RuntimePressure.NOMINAL,
            VanResourceEnvelope.evaluate(flat.copy(charging = true)).pressure,
        )

        // The counterexample. A phone charging while hot is a phone getting hotter, and an
        // envelope that reads the charger as "the situation is being handled" would remove
        // protection at the exact moment it is needed.
        val hotAndCharging = nominal().copy(
            charging = true,
            thermalStatus = VanResourceEnvelope.THERMAL_CRITICAL,
        )
        assertEquals(RuntimePressure.SURVIVAL, VanResourceEnvelope.evaluate(hotAndCharging).pressure)
    }

    @Test
    fun `an unreadable battery is not a flat battery`() {
        // RuntimeReading.UNKNOWN defaults would otherwise read as zero percent and put every
        // device whose OEM does not answer the capacity property into SURVIVAL forever.
        val state = VanResourceEnvelope.evaluate(
            RuntimeReading(
                batteryPercent = RuntimeReading.UNKNOWN,
                freeStorageBytes = RuntimeReading.UNKNOWN_BYTES,
            ),
        )
        assertEquals(RuntimePressure.NOMINAL, state.pressure)
    }

    @Test
    fun `power save asks for restraint and does not declare an emergency`() {
        // A phone at eighty percent with battery saver on by habit is not in trouble.
        // Treating it as CRITICAL would leave VAN permanently crippled for a lot of people.
        val state = VanResourceEnvelope.evaluate(nominal().copy(powerSaveMode = true))
        assertEquals(RuntimePressure.CONSTRAINED, state.pressure)
    }

    @Test
    fun `battery bands escalate`() {
        fun at(percent: Int) = VanResourceEnvelope.evaluate(nominal().copy(batteryPercent = percent)).pressure
        assertEquals(RuntimePressure.NOMINAL, at(21))
        assertEquals(RuntimePressure.CONSTRAINED, at(20))
        assertEquals(RuntimePressure.CRITICAL, at(10))
        assertEquals(RuntimePressure.SURVIVAL, at(5))
    }

    @Test
    fun `memory and storage contribute independently`() {
        assertEquals(
            RuntimePressure.CRITICAL,
            VanResourceEnvelope.evaluate(nominal().copy(memoryLow = true)).pressure,
        )
        assertEquals(
            RuntimePressure.CRITICAL,
            VanResourceEnvelope.evaluate(
                nominal().copy(memoryTrimLevel = VanResourceEnvelope.TRIM_RUNNING_CRITICAL),
            ).pressure,
        )
        assertEquals(
            RuntimePressure.CRITICAL,
            VanResourceEnvelope.evaluate(nominal().copy(freeStorageBytes = 1024)).pressure,
        )
    }

    // ---- what is never given up --------------------------------------------------

    @Test
    fun `hearing the owner survives every pressure`() {
        // The promise, not the policy. An envelope that can switch this off has optimised
        // the phone by removing the reason VAN is on it.
        for (pressure in RuntimePressure.entries) {
            for (subsystem in VanResourceEnvelope.NEVER_SHED) {
                val allowance = VanResourceEnvelope.allowance(subsystem, pressure)
                assertTrue(allowance.running, "$subsystem stopped at $pressure")
                assertEquals(1.0, allowance.cadenceScale, "$subsystem was slowed at $pressure")
            }
        }
    }

    @Test
    fun `the wake word and the owner's own commands are among them`() {
        // Asserted by name as well as by set membership: a future edit that empties
        // NEVER_SHED would leave the loop above passing vacuously.
        assertTrue(VanSubsystem.WAKE_WORD in VanResourceEnvelope.NEVER_SHED)
        assertTrue(VanSubsystem.OWNER_COMMAND in VanResourceEnvelope.NEVER_SHED)
        assertTrue(VanSubsystem.DEGRADED_REPORTING in VanResourceEnvelope.NEVER_SHED)
    }

    @Test
    fun `saying VAN is unwell is not a luxury`() {
        // The degraded registry is how the owner learns a capability is broken. Shedding it
        // under pressure would make a struggling VAN look like a working one.
        val allowance = VanResourceEnvelope.allowance(
            VanSubsystem.DEGRADED_REPORTING,
            RuntimePressure.SURVIVAL,
        )
        assertTrue(allowance.running)
    }

    // ---- the shed order ----------------------------------------------------------

    @Test
    fun `everything discretionary yields before anything the owner asked for`() {
        val discretionary = VanSubsystem.entries.filterNot { it in VanResourceEnvelope.NEVER_SHED }
        for (subsystem in discretionary) {
            val nominal = VanResourceEnvelope.allowance(subsystem, RuntimePressure.NOMINAL)
            assertTrue(nominal.running, "$subsystem does not run on a healthy device")
        }

        // At SURVIVAL every discretionary poller has stopped. The embodiment is the one
        // exception and it yields on richness rather than cadence — see the ceiling tests.
        val pollers = listOf(
            VanSubsystem.TELEMETRY,
            VanSubsystem.LOCAL_INDEX,
            VanSubsystem.TRADING_UPDATES,
            VanSubsystem.EVENT_STREAM,
            VanSubsystem.NOTIFICATION_PROCESSING,
        )
        for (subsystem in pollers) {
            assertFalse(
                VanResourceEnvelope.allowance(subsystem, RuntimePressure.SURVIVAL).running,
                "$subsystem still runs with minutes of device left",
            )
        }
    }

    @Test
    fun `cadence only ever stretches as pressure rises`() {
        // A subsystem that polls faster under pressure is the defect this envelope exists to
        // prevent, and it is the kind of sign error a table makes easy to write.
        for (subsystem in VanSubsystem.entries) {
            var previous = 0.0
            for (pressure in RuntimePressure.entries) {
                val allowance = VanResourceEnvelope.allowance(subsystem, pressure)
                if (!allowance.running) continue
                assertTrue(
                    allowance.cadenceScale >= previous,
                    "$subsystem polls faster at $pressure than at a lower pressure",
                )
                previous = allowance.cadenceScale
            }
        }
    }

    @Test
    fun `telemetry is traded before the owner's own screen stops updating`() {
        // VAN watching itself is the first thing an owner would give up for battery; the
        // event stream is how their screen learns anything happened.
        assertFalse(
            VanResourceEnvelope.allowance(VanSubsystem.TELEMETRY, RuntimePressure.CRITICAL).running,
        )
        assertTrue(
            VanResourceEnvelope.allowance(VanSubsystem.EVENT_STREAM, RuntimePressure.CRITICAL).running,
        )
    }

    @Test
    fun `a stopped subsystem has no cadence`() {
        // Allowance(running = false, cadenceScale = 15.0) would be read by a caller that
        // checks the scale and not the flag as "poll rarely", which is not "do not poll".
        for (subsystem in VanSubsystem.entries) {
            for (pressure in RuntimePressure.entries) {
                val allowance = VanResourceEnvelope.allowance(subsystem, pressure)
                if (!allowance.running) {
                    assertEquals(0.0, allowance.cadenceScale, "$subsystem stopped but still has a cadence")
                }
            }
        }
    }

    // ---- the visual ceiling ------------------------------------------------------

    @Test
    fun `the envelope may lower the embodiment's budget and never raise it`() {
        // The direction is the whole point. A sum that can raise a subsystem's own budget is
        // not an envelope, it is a sixth opinion.
        val conditions = VanEffectConditions()
        for (reading in listOf(
            nominal(),
            nominal().copy(powerSaveMode = true),
            nominal().copy(batteryPercent = 8),
            nominal().copy(thermalStatus = VanResourceEnvelope.THERMAL_CRITICAL),
        )) {
            val ladder = VanEffectPolicy.resolve(conditions)
            val resolved = VanResourceEnvelope.effectBudget(reading, conditions)
            assertTrue(
                resolved.filamentScale <= ladder.filamentScale,
                "the envelope made the field richer than the ladder asked for",
            )
        }
    }

    @Test
    fun `a nearly flat battery no longer renders the full field`() {
        // The concrete regression. Battery *level* was an input to nothing: a phone at four
        // percent with power-save switched off got FULL.
        val flat = nominal().copy(batteryPercent = 4)
        assertEquals(VanEffectBudget.FULL, VanEffectPolicy.resolve(VanEffectConditions()))
        assertEquals(VanEffectBudget.STATIC, VanResourceEnvelope.effectBudget(flat, VanEffectConditions()))
    }

    @Test
    fun `a still budget is never clamped into a moving one`() {
        // Reduced motion is an accessibility decision, not a rung on a cost ladder. Trading
        // it for a few milliwatts would start VAN moving on a device whose owner asked it
        // not to. Asserted over every combination rather than guarded by a branch, because a
        // guard that cannot fire proves nothing.
        val stillConditions = VanEffectConditions(reducedMotion = true)
        for (reading in listOf(
            nominal(),
            nominal().copy(powerSaveMode = true),
            nominal().copy(batteryPercent = 8),
            nominal().copy(batteryPercent = 2),
            nominal().copy(thermalStatus = VanResourceEnvelope.THERMAL_MODERATE),
            nominal().copy(thermalStatus = VanResourceEnvelope.THERMAL_CRITICAL),
            nominal().copy(memoryLow = true),
        )) {
            val resolved = VanResourceEnvelope.effectBudget(reading, stillConditions)
            assertFalse(
                resolved.allowMotion,
                "the envelope restored motion the owner had switched off, at $reading",
            )
        }
    }

    @Test
    fun `the ceiling tightens as pressure rises and never loosens`() {
        var previous = Float.MAX_VALUE
        for (pressure in RuntimePressure.entries) {
            val ceiling = VanResourceEnvelope.effectCeiling(pressure)
            assertTrue(
                ceiling.filamentScale <= previous,
                "the ceiling loosened at $pressure",
            )
            previous = ceiling.filamentScale
        }
    }

    @Test
    fun `critical state indicators survive the floor`() {
        // The one thing the visual ladder has always promised, re-asserted where the
        // envelope can now force the floor.
        val dying = nominal().copy(batteryPercent = 1, thermalStatus = VanResourceEnvelope.THERMAL_CRITICAL)
        val budget = VanResourceEnvelope.effectBudget(dying, VanEffectConditions())
        assertTrue(budget.keepsStateIndicators)
    }
}
