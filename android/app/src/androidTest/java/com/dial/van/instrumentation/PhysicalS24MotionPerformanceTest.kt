package com.dial.van.instrumentation

import android.content.Intent
import android.os.Build
import android.os.Debug
import android.os.Handler
import android.os.HandlerThread
import android.os.PowerManager
import android.os.SystemClock
import android.view.FrameMetrics
import android.view.View
import android.view.ViewGroup
import android.view.Window
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.rive.runtime.kotlin.RiveAnimationView
import com.dial.van.visual.RiveBindingContract
import com.dial.van.visual.RiveCandidateHostActivity
import com.dial.van.visual.VanRiveContextCapabilities
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.security.MessageDigest
import java.util.Collections
import kotlin.math.ceil

/** Explicit physical-device probe. Ordinary emulator CI does not pretend to run it. */
@RunWith(AndroidJUnit4::class)
class PhysicalS24MotionPerformanceTest {
    @Test fun measuredS24CandidateFrameDeadlinesAndMemory() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val args = InstrumentationRegistry.getArguments()
        assumeTrue("Explicit physical VAN motion qualification required", args.getString("vanPhysicalMotion") == "true")
        assertTrue("Physical S24 Ultra required, not an emulator", Build.MODEL.startsWith("SM-S928") && !Build.FINGERPRINT.contains("generic"))
        val expected = args.getString("vanCandidateSha256") ?: error("Exact candidate SHA256 is required")
        assertTrue("Expected SHA must be exact", expected.matches(Regex("[0-9a-f]{64}")))
        val context = instrumentation.targetContext
        val bytes = context.assets.open("van_candidate.riv").use { it.readBytes() }
        val digest = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        assertEquals("Unrelated candidate cannot be qualified", expected, digest)
        val metadata = context.assets.open("van_candidate.context.json").bufferedReader().use { it.readText() }
        assertEquals("Full contextual extension must match the exact staged binary", (15..26).toSet(), VanRiveContextCapabilities.resolve(bytes, metadata))

        val samples = Collections.synchronizedList(mutableListOf<Pair<Long, Long>>())
        var lostMetrics = 0
        val thread = HandlerThread("van-physical-frame-evidence").apply { start() }
        val observer = Window.OnFrameMetricsAvailableListener { _, frame, dropped ->
            if (frame.getMetric(FrameMetrics.FIRST_DRAW_FRAME) == 0L) {
                val total = frame.getMetric(FrameMetrics.TOTAL_DURATION)
                val deadline = frame.getMetric(FrameMetrics.DEADLINE)
                if (total > 0L && deadline > 0L) samples.add(total to deadline)
            }
            synchronized(samples) { lostMetrics += dropped }
        }
        val intent = Intent(context, RiveCandidateHostActivity::class.java)
            .putExtra(RiveCandidateHostActivity.EXTRA_TEST_MODE, true)
            .putExtra(RiveCandidateHostActivity.EXTRA_STATE, 2)
            .putExtra(RiveCandidateHostActivity.EXTRA_SIZE_DP, 96)
        val startPss = Debug.getPss()
        val power = context.getSystemService(PowerManager::class.java)
        val thermalBefore = power.currentThermalStatus
        val started = SystemClock.elapsedRealtime()
        var view: RiveAnimationView? = null
        var actualRefreshRate = 0f
        try {
            ActivityScenario.launch<RiveCandidateHostActivity>(intent).use { scenario ->
                instrumentation.waitForIdleSync()
                // The existing review host applies its first Rive inputs after
                // 250 ms; finish that initialization before sampling later states.
                SystemClock.sleep(400L)
                instrumentation.waitForIdleSync()
                scenario.onActivity { activity ->
                    view = findRive(activity.window.decorView)
                    actualRefreshRate = activity.display?.refreshRate ?: 0f
                    activity.window.addOnFrameMetricsAvailableListener(observer, Handler(thread.looper))
                }
                assertNotNull("Native Rive renderer did not load", view)
                for (code in 0..17) {
                    scenario.onActivity { view!!.setNumberState(RiveBindingContract.STATE_MACHINE, "state", code.toFloat()) }
                    SystemClock.sleep(200)
                }
                for (code in 1..26) {
                    scenario.onActivity {
                        view!!.setNumberState(RiveBindingContract.STATE_MACHINE, "state", 2f)
                        view!!.setNumberState(RiveBindingContract.STATE_MACHINE, "attention_x", 0.8f)
                        view!!.setNumberState(RiveBindingContract.STATE_MACHINE, "attention_y", -0.6f)
                        view!!.setNumberState(RiveBindingContract.STATE_MACHINE, "action_code", code.toFloat())
                    }
                    SystemClock.sleep(800)
                    scenario.onActivity { view!!.setNumberState(RiveBindingContract.STATE_MACHINE, "action_code", 0f) }
                    SystemClock.sleep(120)
                }
                scenario.onActivity { it.window.removeOnFrameMetricsAvailableListener(observer) }
            }
        } finally { thread.quitSafely(); thread.join(2_000) }
        val values = synchronized(samples) { samples.toList() }
        val sorted = values.map { it.first }.sorted()
        val late = values.count { it.first > it.second }
        val p95 = sorted.getOrNull((ceil(sorted.size * .95).toInt() - 1).coerceAtLeast(0)) ?: -1L
        val ratio = if (values.isEmpty()) 1.0 else late.toDouble() / values.size
        val thermalAfter = power.currentThermalStatus
        val report = JSONObject().apply {
            put("schema", "van.physical-motion-window/1")
            put("candidate_sha256", digest); put("model", Build.MODEL); put("android_sdk", Build.VERSION.SDK_INT)
            put("elapsed_ms", SystemClock.elapsedRealtime() - started); put("display_refresh_hz", actualRefreshRate)
            put("valid_window_frames", values.size); put("deadline_missed_frames", late); put("deadline_miss_ratio", ratio)
            put("total_duration_p95_ns", p95); put("lost_metric_callbacks", lostMetrics)
            put("process_pss_before_kb", startPss); put("process_pss_after_kb", Debug.getPss())
            put("thermal_before", thermalBefore); put("thermal_after", thermalAfter)
            put("frame_metrics_ns", JSONArray().apply { values.forEach { put(JSONArray(listOf(it.first, it.second))) } })
            put("measurement_scope", "96dp real candidate in existing native review Activity; not cross-app overlay or power-soak certification")
            put("owner_accepted", false); put("battery_power_qualified", false); put("overlay_qualified", false)
        }
        val directory = File(context.filesDir, "character-forge/physical-motion").apply { mkdirs() }
        File(directory, "$digest-${System.currentTimeMillis()}.json").writeText(report.toString(2))
        assertTrue("Too few actual window frames; no empty pass", values.size >= 120)
        assertTrue("Frame metrics must not be silently dropped", lostMetrics <= values.size / 100)
        assertTrue("More than 5% of frames exceeded the actual display deadline", ratio <= .05)
        assertTrue("Severe thermal throttling invalidates this comparison", thermalAfter < PowerManager.THERMAL_STATUS_SEVERE)
    }

    private fun findRive(node: View): RiveAnimationView? {
        if (node is RiveAnimationView) return node
        if (node is ViewGroup) for (i in 0 until node.childCount) findRive(node.getChildAt(i))?.let { return it }
        return null
    }
}
