package com.dial.van.overlay
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.VanApplication
import com.dial.van.trading.TradeView
import com.dial.van.visual.VanEmbodiment
import com.dial.van.visual.VanGlassSurface
import com.dial.van.visual.VanGlassTokens
import com.dial.van.visual.VanLiveVisualState
import com.dial.van.visual.VanPresence
import com.dial.van.visual.VanPresentation
import com.dial.van.visual.VanVisualState
import com.dial.van.design.VanMotionSpec
import com.dial.van.visual.rememberReducedMotion
import com.dial.van.visual.rememberVanEffectBudget

/**
 * The overlay's surface: what VAN looks like in each presentation.
 *
 * Rev 3.0 s41 and P3-AND-009. `FloatingOverlayService` was 1,096 lines and was, at once, a
 * foreground service, a WindowManager client, a drag controller and this entire Compose
 * tree — with every panel reading the service's own mutable fields and calling its private
 * methods directly. s41 says the service is responsible for window and service lifecycle,
 * not for all domain state; this file is the other half of that sentence.
 *
 * Nothing here reaches for Android. The presentation reads [VanOverlaySurfaceState], which
 * the service measures, and acts through [VanOverlayActions], which the service supplies.
 * That is not ceremony: `MaximizedWorkboard` used to size itself from the service's display
 * metrics, and the chips used to call `startActivity` on the service. That coupling is why
 * none of these panels could be named by anything else, and why the file they lived in
 * could not be read to the end.
 */

/**
 * What the workboard is currently showing.
 *
 * Was `private` inside the service, which is why nothing outside it could render it.
 */
internal enum class VanWorkboardMode { CONTEXT, CHAT, VOICE, TRADES }

/**
 * Everything the surface draws from, measured by the service.
 *
 * A snapshot rather than a handle. A composable that can read the service's fields can also
 * write them, and several of these panels did — `workboardMode = ...` from inside a chip is
 * how a presentation ends up owning domain state.
 */
internal data class VanOverlaySurfaceState(
    val presentation: VanOverlayPresentation,
    val quickControlsVisible: Boolean,
    val workboardMode: VanWorkboardMode,
    val chatDraft: String,
    val tradeView: TradeView,
    val tradeRefreshTick: Int,
    /** P1-PERF-002 — false when the screen is off, and the frame loop stops. */
    val animate: Boolean,
    val blurBehindActive: Boolean,
    /** Measured from the window, because only the service has one. */
    val maximizedWidthDp: Float,
    val maximizedHeightDp: Float,
)

/**
 * Everything the surface can ask for.
 *
 * [gestures] is a prebuilt `Modifier` rather than a callback because dragging VAN around is
 * one gesture chain shared by every presentation; rebuilding it per panel is how a drag
 * starts behaving differently depending on what VAN happens to be showing.
 */
internal class VanOverlayActions(
    val gestures: Modifier,
    val onQuickControl: (String) -> Unit,
    val onChat: (expanded: Boolean) -> Unit,
    val onVoice: () -> Unit,
    val onPresentation: (VanOverlayPresentation) -> Unit,
    val onCommandCentre: (String?) -> Unit,
    val onTradingRoute: (String) -> Unit,
    val onWorkboardMode: (VanWorkboardMode) -> Unit,
    val onTradeView: (TradeView) -> Unit,
    val onTradeRefresh: () -> Unit,
    val onDraft: (String) -> Unit,
)

@Composable
internal fun VanOverlaySurface(
    app: VanApplication,
    state: VanOverlaySurfaceState,
    actions: VanOverlayActions,
) {
    val degraded by app.degradedModeStore.state.collectAsState()
    val liveFrame = VanLiveVisualState.frame
    val cue = VanPresence.cue(degraded, live = liveFrame)
    val visualState = VanPresence.visualState(cue, liveFrame)
    val chrome = VanOverlayChrome.resolve(
        cue = cue,
        live = liveFrame.copy(health = cue.health),
        healthLine = VanPresence.healthCue(degraded),
    )
    val budget = rememberVanEffectBudget()
    val glass = VanGlassTokens.forState(
        state = chrome.primaryState,
        liveBlurAvailable = state.blurBehindActive,
        budget = budget,
    )
    val conversation by app.commandController.state.collectAsState()
    val systemLine = chrome.healthLine ?: VanPresence.meshCue(degraded)

    // DNA §6 motion: a presentation change is one continuous surface re-shaping, not a
    // hard cut. Size is owned by the window (the service resizes the layout params), so
    // only the content cross-fades/scales; reduced motion collapses both to 0ms.
    val reducedMotion = rememberReducedMotion()
    val transitionMs = VanMotionSpec.sharedElementDurationMs(reducedMotion)
    MaterialTheme {
        AnimatedContent(
            targetState = state.presentation,
            transitionSpec = {
                (fadeIn(tween(transitionMs)) + scaleIn(tween(transitionMs), initialScale = 0.96f))
                    .togetherWith(fadeOut(tween(transitionMs / 2)))
                    .using(null)
            },
            label = "overlay-presentation",
        ) { presentation ->
        when (presentation) {
            VanOverlayPresentation.FULL_FLOATING -> FullFloatingPresence(
                visualState = visualState,
                showControls = state.quickControlsVisible,
                state = state,
                actions = actions,
            )
            VanOverlayPresentation.WORKBOARD_COMPACT -> CompactWorkboard(
                state = state,
                actions = actions,
                app = app,
                visualState = visualState,
                glass = glass,
                caption = chrome.caption,
                healthLine = chrome.healthLine,
                accent = chrome.accent,
                latestMessage = conversation.messages.lastOrNull()?.text,
            )
            VanOverlayPresentation.WORKBOARD_EXPANDED -> ExpandedWorkboard(
                state = state,
                actions = actions,
                app = app,
                visualState = visualState,
                glass = glass,
                headline = chrome.headline,
                caption = chrome.caption,
                systemLine = systemLine,
                accent = chrome.accent,
                messages = conversation.messages,
            )
            VanOverlayPresentation.WORKBOARD_MAXIMIZED -> MaximizedWorkboard(
                state = state,
                actions = actions,
                app = app,
                visualState = visualState,
                glass = glass,
                headline = chrome.headline,
                systemLine = systemLine,
                accent = chrome.accent,
                messages = conversation.messages,
            )
            VanOverlayPresentation.MINIMIZED -> MinimizedPresence(visualState, actions)
            VanOverlayPresentation.DOCKED -> DockedPresence(visualState, state, actions)
        }
        }
    }
}

@Composable
internal fun FullFloatingPresence(
    visualState: VanVisualState,
    showControls: Boolean,
    state: VanOverlaySurfaceState,
    actions: VanOverlayActions,
) {
    val width = if (showControls) 360 else OverlayTheme.RESTING_HIT_DP
    Box(
        modifier = Modifier
            .width(width.dp)
            .height(OverlayTheme.RESTING_HIT_DP.dp),
        contentAlignment = Alignment.TopStart,
    ) {
        val budget = rememberVanEffectBudget()
        VanEmbodiment(
            animate = state.animate,
            state = visualState,
            budget = budget,
            presentation = VanPresentation.COMPACT,
            characterFraction = OverlayTheme.RESTING_AVATAR_DP / OverlayTheme.RESTING_HIT_DP.toFloat(),
            modifier = Modifier
                .size(OverlayTheme.RESTING_HIT_DP.dp)
                .semantics { contentDescription = "Van floating assistant" }
                .then(actions.gestures),
        )
        if (showControls) {
            QuickControls(
                modifier = Modifier
                    .offset(x = 176.dp, y = 4.dp)
                    .width(176.dp),
                blurBehindActive = state.blurBehindActive,
                onQuickControl = actions.onQuickControl,
            )
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
internal fun QuickControls(
    modifier: Modifier = Modifier,
    blurBehindActive: Boolean,
    onQuickControl: (String) -> Unit,
) {
    VanGlassSurface(
        style = VanGlassTokens.forState(
            state = VanLiveVisualState.current.durableState,
            liveBlurAvailable = blurBehindActive,
        ),
        modifier = modifier,
    ) {
        Column(
            modifier = Modifier.padding(8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            OverlayTheme.QUICK_CONTROLS.forEach { label ->
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(30.dp)
                        .clip(RoundedCornerShape(9.dp))
                        .background(Color(VanGlassTokens.BABY_CYAN).copy(alpha = 0.10f))
                        .combinedClickable(onClick = { onQuickControl(label) })
                        .padding(horizontal = 8.dp),
                    contentAlignment = Alignment.CenterStart,
                ) {
                    Text(label, color = Color(0xFFF4FCFF), fontSize = 11.sp)
                }
            }
        }
    }
}

@Composable
internal fun MinimizedPresence(visualState: VanVisualState, actions: VanOverlayActions) {
    Box(
        modifier = Modifier.size(OverlayTheme.MINIMIZED_TOUCH_DP.dp),
        contentAlignment = Alignment.Center,
    ) {
        VanMinimizedAvatar(
            state = visualState,
            modifier = Modifier
                .size(OverlayTheme.MINIMIZED_VISUAL_DP.dp)
                .then(actions.gestures),
        )
    }
}

@Composable
internal fun DockedPresence(
    visualState: VanVisualState,
    state: VanOverlaySurfaceState,
    actions: VanOverlayActions,
) {
    val budget = rememberVanEffectBudget()
    Box(
        modifier = Modifier
            .size(width = OverlayTheme.DOCK_WIDTH_DP.dp, height = OverlayTheme.DOCK_HIT_DP.dp)
            .semantics { contentDescription = "Van docked" },
    ) {
        Canvas(Modifier.fillMaxSize()) {
            val field = Color(VanGlassTokens.ACCENT_CYAN).copy(alpha = 0.25f)
            val path = androidx.compose.ui.graphics.Path().apply {
                moveTo(size.width * 0.08f, size.height * 0.12f)
                quadraticBezierTo(size.width * 0.95f, size.height * 0.08f, size.width, size.height * 0.42f)
                quadraticBezierTo(size.width * 0.92f, size.height * 0.92f, size.width * 0.10f, size.height * 0.88f)
                quadraticBezierTo(size.width * 0.02f, size.height * 0.50f, size.width * 0.08f, size.height * 0.12f)
                close()
            }
            drawPath(path, field)
        }
        VanEmbodiment(
            animate = state.animate,
            state = visualState,
            budget = budget,
            presentation = VanPresentation.COMPACT,
            modifier = Modifier
                .size(OverlayTheme.DOCK_CHARACTER_DP.dp)
                .align(Alignment.TopCenter)
                .offset(y = (-4).dp)
                .then(actions.gestures),
        )
    }
}
