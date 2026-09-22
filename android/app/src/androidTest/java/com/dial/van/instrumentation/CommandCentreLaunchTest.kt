package com.dial.van.instrumentation

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.dial.van.command.CommandCentreActivity
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * GAP-F-023 — the app's owner surface starts on a real Android runtime, with no gateway
 * behind it. The IA's primary destinations are present and the `van://` deep link lands
 * on the destination it names. Nothing here needs network, pairing or a signed manifest:
 * every screen renders its OFFLINE/EMPTY state honestly when the gateway is unreachable,
 * which is the case this test runs in.
 *
 * Each destination is also captured to `<external files>/screenshots/<route>.png`. CI pulls
 * that directory as the `van-instrumentation-screenshots` artifact: the visual evidence for
 * the redesign is what the device rendered, not a mock-up.
 */
@RunWith(AndroidJUnit4::class)
class CommandCentreLaunchTest {
    @get:Rule
    val compose = createEmptyComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    @Test
    fun launchesOnHomeWithPrimaryDestinations() {
        ActivityScenario.launch(CommandCentreActivity::class.java).use {
            compose.waitForIdle()
            compose.onNodeWithText("Home").assertIsDisplayed().assertIsSelected()
            for (label in listOf("Attention", "Work", "Trading", "Memory", "More")) {
                compose.onNodeWithText(label).assertIsDisplayed()
            }
            capture("home")
        }
    }

    @Test
    fun everyPrimaryDestinationRendersOffline() {
        ActivityScenario.launch(CommandCentreActivity::class.java).use {
            compose.waitForIdle()
            for (label in listOf("Attention", "Work", "Trading", "Memory")) {
                compose.onNodeWithText(label).performClick()
                compose.waitForIdle()
                compose.onNodeWithText(label).assertIsSelected()
                capture(label.lowercase())
            }
            compose.onNodeWithText("More").performClick()
            compose.waitForIdle()
            for (label in listOf("Projects", "Connected", "Settings")) {
                compose.onNodeWithText(label).assertIsDisplayed()
            }
            capture("more")
        }
    }

    @Test
    fun deepLinkSelectsNamedDestination() {
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse("van://attention"))
            .setClass(context, CommandCentreActivity::class.java)
        ActivityScenario.launch<CommandCentreActivity>(intent).use {
            compose.waitForIdle()
            compose.onNodeWithText("Attention").assertIsSelected()
            capture("deeplink-attention")
        }
    }

    private fun capture(name: String) {
        val dir = File(context.getExternalFilesDir(null), "screenshots").apply { mkdirs() }
        val bitmap = compose.onRoot().captureToImage().asAndroidBitmap()
        File(dir, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }
}
