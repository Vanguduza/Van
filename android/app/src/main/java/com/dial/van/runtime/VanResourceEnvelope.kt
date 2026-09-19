package com.dial.van.runtime

import com.dial.van.visual.VanEffectBudget
import com.dial.van.visual.VanEffectConditions
import com.dial.van.visual.VanEffectPolicy

/**
 * One envelope for the whole runtime, and the order in which VAN gives things up.
 *
 * P3-PERF-003. Always-available voice, the animated embodiment, the event stream, trading
 * updates, notification processing, telemetry and any local index all run on one phone.
 * The audit's phrasing was "each has its own budget; nothing owns the sum", which was
 * generous: only the visual layer had a budget at all. `VanEffectPolicy` shed decoration on
 * thermal status and power-save mode, `DeviceTelemetryReporter` flushed on a fixed minute,
 * `EventStream` polled on a fixed fifteen seconds, and nothing else consulted the device's
 * condition in any way. A phone at four percent with power-save switched off rendered the
 * full field.
 *
 * So this is not another budget beside the others. It is the one the others answer to, and
 * three properties make that true rather than decorative.
 *
 * **Pressure is the worst input, not the latest one.** A phone on a charger is not a phone
 * that has stopped being hot, and a cool phone at three percent is still nearly dead. Each
 * input contributes a level independently and the envelope takes the maximum, naming which
 * input set it so a CRITICAL reading is arguable rather than mysterious.
 *
 * **Some things are never shed.** An envelope that throttles the wake word is worse than no
 * envelope: the owner says "Hey Van", nothing happens, and the cause is the mechanism meant
 * to protect them. Hearing the owner, carrying out what they asked, and saying which parts
 * of VAN are unwell are [NEVER_SHED] at every pressure including SURVIVAL. Everything that
 * yields is something VAN does *for* the owner without being asked.
 *
 * **The visual ladder resolves through the ceiling rather than beside it.** `effectBudget`
 * takes the weaker of what `VanEffectPolicy` decided and what the envelope permits, so the
 * subsystem that already had a budget is now governed by the sum instead of competing with
 * it. Reproducing the ladder here would have recreated the finding one level up.
 *
 * Pure Kotlin. No Android imports, so it is compiled and executed by `android/verification`
 * rather than only reasoned about — which matters, because nothing in this repository can
 * run the app and the arithmetic is the part that can be wrong.
 *
 * What this file does not claim: that the envelope keeps a real phone cool. It declares the
 * policy and the readings it responds to. Whether the S24 thermally throttles under VAN's
 * actual load is a measurement, it is Gate 14's, and no amount of testing here substitutes
 * for it.
 */
enum class RuntimePressure(val rank: Int) {
    /** Nothing is constrained. VAN may run everything it offers. */
    NOMINAL(0),

    /** Restraint asked for or approaching. Background cadence stretches; nothing stops. */
    CONSTRAINED(1),

    /** The device is in trouble. Everything discretionary stops. */
    CRITICAL(2),

    /** Minutes of usable device left. Only what the owner would notice losing survives. */
    SURVIVAL(3),
    ;

    fun atLeast(other: RuntimePressure): Boolean = rank >= other.rank
}

/**
 * What the device says about itself, in one reading.
 *
 * Every field is permission-free on Android: BatteryManager's capacity property,
 * PowerManager's save mode and thermal status, ActivityManager's low-memory flag and the
 * data directory's usable space. An envelope that needed a runtime permission would be an
 * envelope the owner could decline, leaving VAN with no idea what it was doing to their
 * phone.
 *
 * Unknown is [UNKNOWN] rather than a default. A battery percent of zero and a battery
 * percent nobody could read are very different, and treating the second as the first would
 * put VAN into SURVIVAL on a device whose battery API simply did not answer.
 */
data class RuntimeReading(
    /** 0..100, or [UNKNOWN]. */
    val batteryPercent: Int = UNKNOWN,
    val charging: Boolean = false,
    /** `PowerManager.isPowerSaveMode`. */
    val powerSaveMode: Boolean = false,
    /** `PowerManager.getCurrentThermalStatus()`; 0 = none. */
    val thermalStatus: Int = 0,
    /** `ActivityManager.MemoryInfo.lowMemory`. */
    val memoryLow: Boolean = false,
    /** `ComponentCallbacks2.TRIM_MEMORY_*`; 0 = no trim requested. */
    val memoryTrimLevel: Int = 0,
    /** Usable bytes in the app's data directory, or [UNKNOWN_BYTES]. */
    val freeStorageBytes: Long = UNKNOWN_BYTES,
) {
    companion object {
        const val UNKNOWN = -1
        const val UNKNOWN_BYTES = -1L
    }
}

/** The envelope's verdict, and why it reached it. */
data class EnvelopeState(
    val pressure: RuntimePressure,
    /**
     * Every input that contributed at the winning level, in a fixed order.
     *
     * Named rather than counted: "CRITICAL" with no reason is a number an engineer cannot
     * argue with and an owner cannot act on. "thermal_severe" tells them to take the phone
     * out of the sun.
     */
    val reasons: List<String>,
)

/** The things that compete for one phone. Named, so the shed order is a list and not a habit. */
enum class VanSubsystem {
    /** Listening for the owner. */
    WAKE_WORD,

    /** Carrying out what the owner asked, including the offline queue's replay. */
    OWNER_COMMAND,

    /** Saying which parts of VAN are not working. */
    DEGRADED_REPORTING,

    /** The animated embodiment. */
    EMBODIMENT,

    /** Polling the gateway's event stream. */
    EVENT_STREAM,

    /** Posting device telemetry to the gateway. */
    TELEMETRY,

    /** Live trading prices and positions. */
    TRADING_UPDATES,

    /** Reading and classifying incoming notifications. */
    NOTIFICATION_PROCESSING,

    /** Building or refreshing any on-device index. */
    LOCAL_INDEX,
}

/**
 * How a subsystem is allowed to behave at the current pressure.
 *
 * [cadenceScale] multiplies a poller's interval: 1.0 is its declared cadence, 4.0 is four
 * times slower. It is a scale rather than a replacement interval because each subsystem
 * still owns what its normal rate should be; the envelope owns how much of it the device
 * can afford.
 */
data class Allowance(val running: Boolean, val cadenceScale: Double) {
    companion object {
        val FULL = Allowance(running = true, cadenceScale = 1.0)
        val STOPPED = Allowance(running = false, cadenceScale = 0.0)
    }
}

object VanResourceEnvelope {

    // ---- thresholds, each with the reason it is where it is ---------------------

    /** `PowerManager.THERMAL_STATUS_MODERATE`. Throttling has begun. */
    const val THERMAL_MODERATE = 2

    /** `PowerManager.THERMAL_STATUS_SEVERE`. The system is already shedding work. */
    const val THERMAL_SEVERE = 3

    /** `THERMAL_STATUS_CRITICAL` and above: the platform is protecting the hardware. */
    const val THERMAL_CRITICAL = 4

    /** Enough left for a day's ordinary use; VAN should stop being extravagant. */
    const val BATTERY_CONSTRAINED_PERCENT = 20

    /** The band where the owner starts looking for a charger. */
    const val BATTERY_CRITICAL_PERCENT = 10

    /** Minutes left. Anything VAN does that the owner did not ask for costs them a call. */
    const val BATTERY_SURVIVAL_PERCENT = 5

    /** `ComponentCallbacks2.TRIM_MEMORY_RUNNING_LOW`. */
    const val TRIM_RUNNING_LOW = 10

    /** `ComponentCallbacks2.TRIM_MEMORY_RUNNING_CRITICAL`. */
    const val TRIM_RUNNING_CRITICAL = 15

    /** Below this, an index rebuild or a queue flush can fail partway. */
    const val STORAGE_CONSTRAINED_BYTES = 250L * 1024 * 1024

    /** Below this, writing anything at all is a gamble. */
    const val STORAGE_CRITICAL_BYTES = 50L * 1024 * 1024

    /**
     * What VAN never gives up, whatever the device is doing.
     *
     * This is the part of the envelope that is a promise rather than a policy. VAN's whole
     * proposition is that it is there when spoken to; an envelope that can switch that off
     * has optimised the phone by removing the reason it is on it.
     */
    val NEVER_SHED: Set<VanSubsystem> = setOf(
        VanSubsystem.WAKE_WORD,
        VanSubsystem.OWNER_COMMAND,
        VanSubsystem.DEGRADED_REPORTING,
    )

    // ---- pressure ---------------------------------------------------------------

    /**
     * The envelope's state, as the worst of every input.
     *
     * Contributions are independent on purpose. An earlier shape of this took the most
     * recent signal, which meant a phone that got hot and then reported a battery reading
     * dropped straight back to NOMINAL while still throttling.
     */
    fun evaluate(reading: RuntimeReading): EnvelopeState {
        val contributions = buildList {
            add("thermal" to thermalPressure(reading.thermalStatus))
            add("battery" to batteryPressure(reading))
            add("power_save" to powerSavePressure(reading))
            add("memory" to memoryPressure(reading))
            add("storage" to storagePressure(reading))
        }
        val pressure = contributions.maxOf { it.second }
        return EnvelopeState(
            pressure = pressure,
            reasons = if (pressure == RuntimePressure.NOMINAL) {
                emptyList()
            } else {
                contributions.filter { it.second == pressure }.map { it.first }
            },
        )
    }

    private fun thermalPressure(status: Int): RuntimePressure = when {
        status >= THERMAL_CRITICAL -> RuntimePressure.SURVIVAL
        status >= THERMAL_SEVERE -> RuntimePressure.CRITICAL
        status >= THERMAL_MODERATE -> RuntimePressure.CONSTRAINED
        else -> RuntimePressure.NOMINAL
    }

    /**
     * Charging clears battery pressure and nothing else.
     *
     * It is the one input where "the situation is being fixed" is true, because a plugged-in
     * phone is genuinely refilling. It is emphatically not true of heat: a phone charging
     * while hot is a phone getting hotter, which is why this function only looks at battery.
     */
    private fun batteryPressure(reading: RuntimeReading): RuntimePressure {
        if (reading.batteryPercent == RuntimeReading.UNKNOWN) return RuntimePressure.NOMINAL
        if (reading.charging) return RuntimePressure.NOMINAL
        return when {
            reading.batteryPercent <= BATTERY_SURVIVAL_PERCENT -> RuntimePressure.SURVIVAL
            reading.batteryPercent <= BATTERY_CRITICAL_PERCENT -> RuntimePressure.CRITICAL
            reading.batteryPercent <= BATTERY_CONSTRAINED_PERCENT -> RuntimePressure.CONSTRAINED
            else -> RuntimePressure.NOMINAL
        }
    }

    /**
     * Power-save mode is a request, and it caps at CONSTRAINED deliberately.
     *
     * Someone — the owner or the system on their behalf — has asked for restraint. That is
     * a reason to stretch cadence, not to decide the device is in trouble; a phone at eighty
     * percent with battery saver switched on by habit is not an emergency, and treating it
     * as one would leave VAN permanently crippled for a large number of people.
     */
    private fun powerSavePressure(reading: RuntimeReading): RuntimePressure =
        if (reading.powerSaveMode) RuntimePressure.CONSTRAINED else RuntimePressure.NOMINAL

    private fun memoryPressure(reading: RuntimeReading): RuntimePressure = when {
        reading.memoryTrimLevel >= TRIM_RUNNING_CRITICAL -> RuntimePressure.CRITICAL
        reading.memoryLow -> RuntimePressure.CRITICAL
        reading.memoryTrimLevel >= TRIM_RUNNING_LOW -> RuntimePressure.CONSTRAINED
        else -> RuntimePressure.NOMINAL
    }

    private fun storagePressure(reading: RuntimeReading): RuntimePressure = when {
        reading.freeStorageBytes == RuntimeReading.UNKNOWN_BYTES -> RuntimePressure.NOMINAL
        reading.freeStorageBytes < STORAGE_CRITICAL_BYTES -> RuntimePressure.CRITICAL
        reading.freeStorageBytes < STORAGE_CONSTRAINED_BYTES -> RuntimePressure.CONSTRAINED
        else -> RuntimePressure.NOMINAL
    }

    // ---- allowances --------------------------------------------------------------

    /**
     * What a subsystem may do at a pressure.
     *
     * The order things are surrendered in is visible here as a table rather than distributed
     * across the subsystems that implement it, which is the whole correction: before this,
     * the shed order was whatever each subsystem happened to decide, and most decided
     * nothing.
     */
    fun allowance(subsystem: VanSubsystem, pressure: RuntimePressure): Allowance {
        if (subsystem in NEVER_SHED) return Allowance.FULL
        // Exhaustive over the enum with no `else`, so adding a subsystem is a compile error
        // rather than a silent Allowance.FULL. A resource envelope whose default for
        // anything new is "unconstrained" would decay back into the finding one subsystem at
        // a time, which is roughly how it got here.
        return when (subsystem) {
            VanSubsystem.WAKE_WORD,
            VanSubsystem.OWNER_COMMAND,
            VanSubsystem.DEGRADED_REPORTING,
            -> Allowance.FULL

            // Decoration is the first thing to go and the cheapest to lose, but it does not
            // yield on cadence — it yields on richness, through effectCeiling. Reading this
            // FULL as "the embodiment ignores the envelope" would be wrong; it is constrained
            // by a different knob, and the still floor is what STATIC is for. A VAN with no
            // visible presence at all reads as a VAN that has crashed.
            VanSubsystem.EMBODIMENT -> Allowance.FULL

            // Telemetry is VAN watching itself. Useful, and the first thing an owner would
            // trade for battery.
            VanSubsystem.TELEMETRY -> when {
                pressure.atLeast(RuntimePressure.CRITICAL) -> Allowance.STOPPED
                pressure.atLeast(RuntimePressure.CONSTRAINED) -> Allowance(true, 4.0)
                else -> Allowance.FULL
            }

            // An index rebuild is the classic background battery burner, and it is the one
            // job that can always be finished later at no cost to the owner.
            VanSubsystem.LOCAL_INDEX -> when {
                pressure.atLeast(RuntimePressure.CRITICAL) -> Allowance.STOPPED
                pressure.atLeast(RuntimePressure.CONSTRAINED) -> Allowance(true, 8.0)
                else -> Allowance.FULL
            }

            // Prices are live data the owner may be watching. Slowed hard before stopped,
            // and a stale price is worse than no price, which is the trading surface's
            // problem to report rather than this envelope's to hide.
            VanSubsystem.TRADING_UPDATES -> when {
                pressure.atLeast(RuntimePressure.SURVIVAL) -> Allowance.STOPPED
                pressure.atLeast(RuntimePressure.CRITICAL) -> Allowance(true, 8.0)
                pressure.atLeast(RuntimePressure.CONSTRAINED) -> Allowance(true, 3.0)
                else -> Allowance.FULL
            }

            // How the owner's screen learns anything changed. Stretched, and only stopped
            // when the device has minutes left.
            VanSubsystem.EVENT_STREAM -> when {
                pressure.atLeast(RuntimePressure.SURVIVAL) -> Allowance.STOPPED
                pressure.atLeast(RuntimePressure.CRITICAL) -> Allowance(true, 6.0)
                pressure.atLeast(RuntimePressure.CONSTRAINED) -> Allowance(true, 2.0)
                else -> Allowance.FULL
            }

            // Event-driven rather than polled, so there is no cadence to stretch: it either
            // processes what arrives or it does not.
            VanSubsystem.NOTIFICATION_PROCESSING -> when {
                pressure.atLeast(RuntimePressure.SURVIVAL) -> Allowance.STOPPED
                else -> Allowance.FULL
            }
        }
    }

    // ---- the visual ceiling ------------------------------------------------------

    /** The richest the embodiment may be at a pressure, whatever its own ladder decided. */
    fun effectCeiling(pressure: RuntimePressure): VanEffectBudget = when (pressure) {
        RuntimePressure.NOMINAL -> VanEffectBudget.FULL
        // Matches what the existing ladder already does for power-save mode, which is the
        // most common way to arrive at CONSTRAINED.
        RuntimePressure.CONSTRAINED -> VanEffectBudget.LOW
        RuntimePressure.CRITICAL -> VanEffectBudget.STATIC
        RuntimePressure.SURVIVAL -> VanEffectBudget.STATIC
    }

    /**
     * Richness order, for clamping. Not a property of the enum, because it is not one.
     *
     * REDUCED_MOTION sits beside LOW rather than above or below it: it is an accessibility
     * decision about motion, not a rung on a cost ladder, and ranking it as cheap or
     * expensive would let a clamp trade the owner's accessibility setting for a few
     * milliwatts.
     */
    private fun rank(budget: VanEffectBudget): Int = when (budget) {
        VanEffectBudget.STATIC -> 0
        VanEffectBudget.REDUCED_MOTION -> 1
        VanEffectBudget.LOW -> 1
        VanEffectBudget.REDUCED -> 2
        VanEffectBudget.FULL -> 3
    }

    /**
     * The embodiment's budget, resolved through the envelope instead of beside it.
     *
     * `VanEffectPolicy` still decides — it knows about reduced motion and cross-window blur,
     * which are not resource questions — and the envelope only ever makes the answer weaker.
     * That direction is the whole point: the sum may veto a subsystem's budget and may never
     * raise it.
     */
    fun effectBudget(reading: RuntimeReading, conditions: VanEffectConditions): VanEffectBudget {
        val ladder = VanEffectPolicy.resolve(conditions)
        val ceiling = effectCeiling(evaluate(reading).pressure)
        return if (rank(ladder) <= rank(ceiling)) ladder else ceiling
    }
}
