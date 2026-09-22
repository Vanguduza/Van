package com.dial.van.instrumentation

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.assertExists
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isSelectable
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
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
 * Each destination is also captured to `<additionalTestOutputDir>/screenshots/<route>.png`,
 * which AGP pulls into `build/outputs/connected_android_test_additional_output` and CI
 * uploads as `van-instrumentation-screenshots`: the visual evidence for the redesign is what
 * the device rendered, not a mock-up.
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
            navItem("Home").assertIsDisplayed().assertIsSelected()
            for (label in listOf("Attention", "Work", "Trading", "Memory")) {
                navItem(label).assertIsDisplayed()
            }
            compose.onNodeWithText("More").assertIsDisplayed()
            capture("home")
        }
    }

    @Test
    fun everyPrimaryDestinationRendersOffline() {
        ActivityScenario.launch(CommandCentreActivity::class.java).use {
            compose.waitForIdle()
            for (label in listOf("Attention", "Work", "Trading", "Memory")) {
                navItem(label).performClick()
                compose.waitForIdle()
                navItem(label).assertIsSelected()
                capture(label.lowercase())
            }
            compose.onNodeWithText("More").performClick()
            // The More sheet is a ModalBottomSheet in its own window with an enter
            // animation; wait for its items to exist rather than asserting mid-slide.
            for (label in listOf("Projects", "Connected", "Settings")) {
                compose.waitUntil(5_000) {
                    compose.onAllNodesWithText(label).fetchSemanticsNodes().isNotEmpty()
                }
                compose.onNodeWithText(label).assertExists()
            }
            compose.waitForIdle()
            capture("more")
        }
    }

    @Test
    fun deepLinkSelectsNamedDestination() {
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse("van://attention"))
            .setClass(context, CommandCentreActivity::class.java)
        ActivityScenario.launch<CommandCentreActivity>(intent).use {
            compose.waitForIdle()
            navItem("Attention").assertIsSelected()
            capture("deeplink-attention")
        }
    }

    /** The navigation item, not a screen header that happens to carry the same word. */
    private fun navItem(label: String) = compose.onNode(hasText(label) and isSelectable())

    private fun capture(name: String) {
        // AGP's additional-test-output channel: the runner argument names a directory the
        // Gradle plugin pulls into build/outputs/connected_android_test_additional_output
        // before it uninstalls the app (an uninstall is what erased the files dir before).
        val additional = InstrumentationRegistry.getArguments().getString("additionalTestOutputDir")
        val root = additional?.let(::File) ?: context.filesDir
        val dir = File(root, "screenshots").apply { mkdirs() }
        val bitmap = compose.onRoot().captureToImage().asAndroidBitmap()
        File(dir, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }
}
