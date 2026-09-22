package com.dial.van.instrumentation

import android.content.Intent
import android.net.Uri
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.dial.van.command.CommandCentreActivity
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * GAP-F-023 — the app's owner surface starts on a real Android runtime, with no gateway
 * behind it. The IA's primary destinations are present and the `van://` deep link lands
 * on the destination it names. Nothing here needs network, pairing or a signed manifest:
 * every screen renders its OFFLINE/EMPTY state honestly when the gateway is unreachable,
 * which is the case this test runs in.
 */
@RunWith(AndroidJUnit4::class)
class CommandCentreLaunchTest {
    @get:Rule
    val compose = createEmptyComposeRule()

    private val context get() = ApplicationProvider.getApplicationContext<android.content.Context>()

    @Test
    fun launchesOnHomeWithPrimaryDestinations() {
        ActivityScenario.launch(CommandCentreActivity::class.java).use {
            compose.waitForIdle()
            compose.onNodeWithText("Home").assertIsDisplayed().assertIsSelected()
            for (label in listOf("Attention", "Work", "Trading", "Memory", "More")) {
                compose.onNodeWithText(label).assertIsDisplayed()
            }
        }
    }

    @Test
    fun deepLinkSelectsNamedDestination() {
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse("van://attention"))
            .setClass(context, CommandCentreActivity::class.java)
        ActivityScenario.launch<CommandCentreActivity>(intent).use {
            compose.waitForIdle()
            compose.onNodeWithText("Attention").assertIsSelected()
        }
    }
}
