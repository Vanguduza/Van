package com.dial.van.instrumentation

import android.content.Context
import android.provider.Settings
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.dial.van.overlay.FloatingOverlayService
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.BufferedReader
import java.io.InputStreamReader

/**
 * GAP-F-023 — Floating VAN starts and stops as a foreground service on a real runtime.
 * The overlay permission is granted through appops for the test process (the same grant
 * the owner makes in Settings); if the runtime refuses that grant the test is skipped,
 * not faked.
 */
@RunWith(AndroidJUnit4::class)
class FloatingOverlayServiceTest {
    private val context: Context get() = ApplicationProvider.getApplicationContext()

    @Before
    fun grantOverlayPermission() {
        shell("appops set ${context.packageName} SYSTEM_ALERT_WINDOW allow")
        assumeTrue("overlay permission could not be granted on this runtime", Settings.canDrawOverlays(context))
    }

    @After
    fun stopService() {
        FloatingOverlayService.stop(context)
        waitUntil(timeoutMs = 5_000) { !FloatingOverlayService.isRunning() }
    }

    @Test
    fun startsAndStops() {
        FloatingOverlayService.start(context)
        assertTrue("service did not report running", waitUntil(10_000) { FloatingOverlayService.isRunning() })
        FloatingOverlayService.stop(context)
        assertTrue("service did not stop", waitUntil(5_000) { !FloatingOverlayService.isRunning() })
        assertFalse(FloatingOverlayService.isRunning())
    }

    private fun waitUntil(timeoutMs: Long, condition: () -> Boolean): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            if (condition()) return true
            Thread.sleep(100)
        }
        return condition()
    }

    private fun shell(command: String): String {
        val pfd = InstrumentationRegistry.getInstrumentation().uiAutomation.executeShellCommand(command)
        return BufferedReader(InputStreamReader(java.io.FileInputStream(pfd.fileDescriptor))).use { it.readText() }
    }
}
