package com.dial.van.runtime

import android.app.ActivityManager
import android.content.Context
import android.net.ConnectivityManager
import android.os.BatteryManager
import android.os.Build
import android.os.PowerManager

/**
 * The device's own account of itself, read with no permission of any kind.
 *
 * Separated from [VanResourceEnvelope] because this half cannot be executed anywhere in
 * this repository — it is Android API calls — while the arithmetic that decides what VAN
 * gives up can be, and is, in `android/verification`. Keeping them in one file would have
 * dragged the policy out of the harness, which is how the audit found so much Android logic
 * that had never been run.
 *
 * Every failure falls back to *unknown* rather than to a healthy value, and
 * [RuntimeReading] treats unknown as contributing no pressure. That is deliberate and it is
 * the safe direction here: an OEM that does not answer the battery capacity property gets a
 * full-strength VAN rather than one permanently crippled by a reading nobody could take.
 * Thermal status is the input that actually protects the hardware and it is available from
 * Android Q on every device.
 */
object DeviceRuntimeReadings {

    fun read(context: Context): RuntimeReading {
        val power = context.getSystemService(PowerManager::class.java)
        val battery = context.getSystemService(BatteryManager::class.java)
        val percent = runCatching {
            battery?.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
                ?: RuntimeReading.UNKNOWN
        }.getOrDefault(RuntimeReading.UNKNOWN)
        val thermal = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            runCatching { power?.currentThermalStatus ?: 0 }.getOrDefault(0)
        } else {
            0
        }
        val memoryLow = runCatching {
            val info = ActivityManager.MemoryInfo()
            context.getSystemService(ActivityManager::class.java)?.getMemoryInfo(info)
            info.lowMemory
        }.getOrDefault(false)
        return RuntimeReading(
            // -1 is BatteryManager's "I do not know"; anything outside 0..100 is a
            // measurement bug, and reporting it as a level is how VAN would decide a phone
            // at minus one percent needs to stop listening.
            batteryPercent = if (percent in 0..100) percent else RuntimeReading.UNKNOWN,
            charging = runCatching { battery?.isCharging == true }.getOrDefault(false),
            powerSaveMode = runCatching { power?.isPowerSaveMode == true }.getOrDefault(false),
            thermalStatus = thermal,
            memoryLow = memoryLow,
            freeStorageBytes = runCatching { context.filesDir.usableSpace }
                .getOrDefault(RuntimeReading.UNKNOWN_BYTES),
        )
    }

    /** The current envelope pressure, for a caller that only needs the verdict. */
    fun pressure(context: Context): RuntimePressure =
        VanResourceEnvelope.evaluate(read(context)).pressure

    /**
     * Rev 1.5 §20.9 — what the owner's data plan says about holding a second socket open.
     *
     * Both readings fail *towards restraint*: a device that will not say whether its link
     * is metered is treated as metered. The asymmetry is deliberate and it is the opposite
     * of [read]'s. An unreadable battery costs VAN capability it probably had; an
     * unreadable data plan would cost the owner money they did not agree to spend, and
     * they cannot undo that by plugging the phone in.
     */
    fun networkCost(context: Context): NetworkCost {
        val manager = context.getSystemService(ConnectivityManager::class.java)
            ?: return NetworkCost(metered = true, dataSaverEnabled = true)
        val metered = runCatching { manager.isActiveNetworkMetered }.getOrDefault(true)
        val restricted = runCatching {
            manager.restrictBackgroundStatus ==
                ConnectivityManager.RESTRICT_BACKGROUND_STATUS_ENABLED
        }.getOrDefault(true)
        return NetworkCost(metered = metered, dataSaverEnabled = restricted)
    }
}

/**
 * What the active link costs, as far as the platform will say.
 *
 * `dataSaverEnabled` is the owner's own setting, which is why §20.9 treats it as an
 * instruction rather than as a hint: a warm standby on mobile data is precisely the
 * background traffic Data Saver exists to stop, and charging does not make the data free.
 */
data class NetworkCost(val metered: Boolean, val dataSaverEnabled: Boolean)
