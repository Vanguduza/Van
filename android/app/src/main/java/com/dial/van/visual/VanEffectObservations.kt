package com.dial.van.visual

import android.content.BroadcastReceiver
import android.content.ComponentCallbacks2
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.res.Configuration
import android.hardware.display.DisplayManager
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.util.Log
import android.view.View
import android.view.WindowManager
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.core.content.ContextCompat
import com.dial.van.runtime.DeviceRuntimeReadings
import com.dial.van.runtime.RuntimeReading
import com.dial.van.runtime.VanResourceEnvelope
import java.util.function.Consumer

/** Native observations only. VanResourceEnvelope remains the single budget owner. */
private data class VanDeviceEffects(
    val runtime: RuntimeReading,
    val blurEnabled: Boolean,
)

private fun readDeviceEffects(context: Context): VanDeviceEffects = VanDeviceEffects(
    runtime = DeviceRuntimeReadings.read(context),
    blurEnabled = runCatching {
        context.getSystemService(WindowManager::class.java)?.isCrossWindowBlurEnabled == true
    }.getOrDefault(false),
)

/**
 * One native subscription per Application, shared by simultaneous overlay/workboard surfaces.
 * No timer or frame loop: platform changes refresh readings. The last consumer unregisters
 * everything; a late callback cannot revive a disposed observation or retain an Activity.
 */
private object VanEffectObservations {
    private val observations = mutableMapOf<Context, NativeObservation>()

    fun subscribe(context: Context, listener: (VanDeviceEffects) -> Unit): AutoCloseable {
        check(Looper.myLooper() == Looper.getMainLooper())
        val app = context.applicationContext
        val observation = observations.getOrPut(app) { NativeObservation(app) }
        observation.add(listener)
        var closed = false
        return AutoCloseable {
            check(Looper.myLooper() == Looper.getMainLooper())
            if (!closed) {
                closed = true
                if (observation.remove(listener)) observations.remove(app)
            }
        }
    }

    private class NativeObservation(private val context: Context) {
        private val power = context.getSystemService(PowerManager::class.java)
        private val window = context.getSystemService(WindowManager::class.java)
        private val listeners = linkedSetOf<(VanDeviceEffects) -> Unit>()
        private var snapshot = readDeviceEffects(context)
        private var closed = false
        private var receiverRegistered = false
        private var thermalRegistered = false
        private var blurRegistered = false
        private var componentRegistered = false
        private val thermal = PowerManager.OnThermalStatusChangedListener { status ->
            refresh(thermalStatus = status)
        }
        private val blur = Consumer<Boolean> { enabled -> refresh(blurEnabled = enabled) }
        private val receiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context?, intent: Intent?) { refresh() }
        }
        private val components = object : ComponentCallbacks2 {
            override fun onConfigurationChanged(newConfig: Configuration) { refresh() }
            override fun onLowMemory() { refresh(trimLevel = ComponentCallbacks2.TRIM_MEMORY_RUNNING_CRITICAL) }
            override fun onTrimMemory(level: Int) {
                // UI_HIDDEN is not RAM pressure. Preserve the envelope's running-pressure semantics.
                val runningLevel = when (level) {
                    ComponentCallbacks2.TRIM_MEMORY_RUNNING_LOW,
                    ComponentCallbacks2.TRIM_MEMORY_RUNNING_CRITICAL -> level
                    else -> 0
                }
                refresh(trimLevel = runningLevel)
            }
        }

        fun add(listener: (VanDeviceEffects) -> Unit) {
            check(!closed)
            listeners.add(listener)
            listener(snapshot)
            if (listeners.size == 1) start()
        }

        fun remove(listener: (VanDeviceEffects) -> Unit): Boolean {
            listeners.remove(listener)
            if (listeners.isNotEmpty()) return false
            closed = true
            if (receiverRegistered) attempt { context.unregisterReceiver(receiver) }
            if (thermalRegistered) attempt { power?.removeThermalStatusListener(thermal) }
            if (blurRegistered) attempt { window?.removeCrossWindowBlurEnabledListener(blur) }
            if (componentRegistered) attempt { context.unregisterComponentCallbacks(components) }
            return true
        }

        private fun start() {
            receiverRegistered = attempt {
                ContextCompat.registerReceiver(context, receiver, IntentFilter().apply {
                    addAction(Intent.ACTION_BATTERY_CHANGED)
                    addAction(PowerManager.ACTION_POWER_SAVE_MODE_CHANGED)
                    addAction(Intent.ACTION_SCREEN_ON)
                    addAction(Intent.ACTION_USER_PRESENT)
                }, ContextCompat.RECEIVER_NOT_EXPORTED)
            }
            thermalRegistered = power != null && attempt {
                power.addThermalStatusListener(context.mainExecutor, thermal)
            }
            blurRegistered = window != null && attempt {
                window.addCrossWindowBlurEnabledListener(context.mainExecutor, blur)
            }
            componentRegistered = attempt { context.registerComponentCallbacks(components) }
            // Close the gap between construction and registration; initial callbacks can be queued.
            refresh()
        }

        private fun refresh(
            thermalStatus: Int? = null,
            blurEnabled: Boolean? = null,
            trimLevel: Int? = null,
        ) {
            if (closed) return
            val fresh = readDeviceEffects(context)
            val next = fresh.copy(
                runtime = fresh.runtime.copy(
                    thermalStatus = thermalStatus ?: fresh.runtime.thermalStatus,
                    memoryTrimLevel = trimLevel ?: fresh.runtime.memoryTrimLevel,
                ),
                blurEnabled = blurEnabled ?: fresh.blurEnabled,
            )
            if (next == snapshot) return
            snapshot = next
            listeners.toList().forEach { it(next) }
        }

        private inline fun attempt(block: () -> Unit): Boolean = try {
            block()
            true
        } catch (error: Exception) {
            Log.w("VanEffectRuntime", "Native effect observation unavailable: ${error.javaClass.simpleName}")
            false
        }
    }
}

@Composable
internal fun rememberObservedVanEffectBudget(): VanEffectBudget {
    val app = LocalContext.current.applicationContext
    var snapshot by remember(app) { mutableStateOf(readDeviceEffects(app)) }
    DisposableEffect(app) {
        val subscription = VanEffectObservations.subscribe(app) { snapshot = it }
        onDispose { subscription.close() }
    }
    val reducedMotion = rememberReducedMotion()
    return VanResourceEnvelope.effectBudget(
        snapshot.runtime,
        VanEffectConditions(
            batterySaver = snapshot.runtime.powerSaveMode,
            thermalStatus = snapshot.runtime.thermalStatus,
            reducedMotion = reducedMotion,
            crossWindowBlurEnabled = snapshot.blurEnabled,
        ),
    )
}

/** Refresh rate belongs to the view's actual display, not an assumed 60 Hz global device. */
@Composable
internal fun rememberVanDisplayRefreshRate(): Float {
    val view = LocalView.current
    fun readRate() = VanFrameCadenceFeedback.validRefreshRate(view.display?.refreshRate ?: 60f)
    var refreshRate by remember(view) { mutableStateOf(readRate()) }
    DisposableEffect(view) {
        val displayManager = view.context.getSystemService(DisplayManager::class.java)
        var disposed = false
        var registered = false
        fun refresh() { if (!disposed) refreshRate = readRate() }
        val listener = object : DisplayManager.DisplayListener {
            override fun onDisplayAdded(displayId: Int) { refresh() }
            override fun onDisplayRemoved(displayId: Int) { refresh() }
            override fun onDisplayChanged(displayId: Int) {
                if (view.display?.displayId == displayId) refresh()
            }
        }
        val attachment = object : View.OnAttachStateChangeListener {
            override fun onViewAttachedToWindow(v: View) { refresh() }
            override fun onViewDetachedFromWindow(v: View) { refresh() }
        }
        view.addOnAttachStateChangeListener(attachment)
        if (displayManager != null) registered = runCatching {
            displayManager.registerDisplayListener(listener, Handler(Looper.getMainLooper()))
        }.isSuccess
        refresh()
        onDispose {
            disposed = true
            view.removeOnAttachStateChangeListener(attachment)
            if (registered) runCatching { displayManager?.unregisterDisplayListener(listener) }
        }
    }
    return refreshRate
}
