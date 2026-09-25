package com.dial.van.onboarding

import android.content.Intent
import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.slideInVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.fragment.app.FragmentActivity
import com.dial.van.VanApplication
import com.dial.van.command.CommandCentreActivity
import com.dial.van.design.LocalVanTokens
import com.dial.van.overlay.FloatingOverlayService
import com.dial.van.visual.VanAvatar
import com.dial.van.visual.VanDurableState
import com.dial.van.visual.VanFiniteAction
import com.dial.van.visual.VanPresentation
import com.dial.van.visual.VanTheme
import com.dial.van.visual.VanVisualState
import kotlinx.coroutines.delay

/**
 * VAN's own launch screen: the character, waving, welcoming the owner back.
 *
 * Owner direction (2026-09-25) replaced the first-run checklist ("Welcome to Van … a few
 * things first") that used to be the launcher. There is nothing to set up here: the phone
 * is provisioned by the installer (ADR-RB-026). VAN is drawn by the production renderer
 * ([VanAvatar]), so this is Candidate B's animated art today and the Rive rig once it is
 * promoted, with no change here.
 *
 * The only thing VAN may ask for before the Command Centre is what he needs to float with
 * the owner — the overlay, then notifications — and only while missing and not declined
 * ([VanAskPlan.nextFloatingAsk]). Everything else is asked for when a feature needs it.
 */
class WelcomeActivity : FragmentActivity() {

    private val askLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        asking = false
        continueIntoVan()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as VanApplication
        val greeting = VanAskPlan.greeting(
            firstLaunch = !VanAsks.hasMet(this),
            connected = app.gatewayClient.isPaired(),
        )
        setContent {
            VanTheme(dark = true) {
                WelcomeScreen(greeting = greeting, onDone = ::continueIntoVan)
            }
        }
    }

    private var leaving = false
    private var asking = false

    /** Ask for what floating needs, one ask at a time, then go in. Re-entered after each ask. */
    private fun continueIntoVan() {
        // A tap and the timer both come here; one ask at a time.
        if (leaving || asking || isFinishing) return
        val next = VanAskPlan.nextFloatingAsk(
            granted = { VanAsks.isGranted(this, it) },
            declined = { VanAsks.isDeclined(this, it) },
        )
        if (next != null) {
            asking = true
            askLauncher.launch(VanAskActivity.intent(this, next))
            return
        }
        leaving = true
        VanAsks.markMet(this)
        if (VanAsks.isGranted(this, VanPermission.OVERLAY)) {
            runCatching { FloatingOverlayService.start(this) }
        }
        startActivity(Intent(this, CommandCentreActivity::class.java))
        finish()
    }
}

/** How long VAN's hello plays before the owner is taken in; a tap goes in sooner. */
private const val WELCOME_MS = 2_600L

@Composable
private fun WelcomeScreen(greeting: String, onDone: () -> Unit) {
    val tokens = LocalVanTokens.current
    var action by remember { mutableIntStateOf(VanFiniteAction.HELLO_WAVE.code) }
    var shown by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        shown = true
        delay(WELCOME_MS)
        action = 0
        onDone()
    }
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(tokens.color.bgCanvas)
            .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null) { onDone() },
        contentAlignment = Alignment.Center,
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(24.dp),
        ) {
            VanAvatar(
                state = VanVisualState(durableState = VanDurableState.IDLE, actionCode = action),
                modifier = Modifier.size(340.dp),
                presentation = VanPresentation.COMMAND_CENTRE,
            )
            // "Welcome back." large; anything VAN adds (he cannot reach home yet) beneath it.
            val headline = greeting.substringBefore(". ", greeting).let { if (it == greeting) it else "$it." }
            val more = greeting.removePrefix(headline).trim()
            AnimatedVisibility(visible = shown, enter = fadeIn() + slideInVertically { it / 3 }) {
                Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(headline, style = tokens.type.display, color = tokens.color.textPrimary, textAlign = TextAlign.Center)
                    if (more.isNotEmpty()) {
                        Text(more, style = tokens.type.body, color = tokens.color.textSecondary, textAlign = TextAlign.Center)
                    }
                }
            }
        }
    }
}
