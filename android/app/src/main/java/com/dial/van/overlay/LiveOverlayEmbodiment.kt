package com.dial.van.overlay

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import com.dial.van.visual.LocalVanPresentationPreferences
import com.dial.van.visual.VanPersonalPresentation
import com.dial.van.visual.vanPhysicalResponse
import com.dial.van.visual.rememberReducedMotion
import com.dial.van.visual.vanMotionEnabled
import com.dial.van.visual.VanEffectBudget
import com.dial.van.visual.VanEmbodiment
import com.dial.van.visual.VanLiveVisualState
import com.dial.van.visual.VanPresentation
import com.dial.van.visual.VanVisualState
import com.dial.van.visual.rememberVanEffectBudget

/** Separate restart scope: animation samples do not invalidate the entire workboard. */
@Composable
internal fun LiveOverlayEmbodiment(
    state: VanVisualState,
    modifier: Modifier = Modifier,
    presentation: VanPresentation = VanPresentation.COMPACT,
    budget: VanEffectBudget = rememberVanEffectBudget(),
    characterFraction: Float = 1f,
    animate: Boolean = true,
    passive: Boolean = false,
) {
    val live = VanLiveVisualState.frame
    val preferences = LocalVanPresentationPreferences.current
    val rendered = VanPersonalPresentation.project(OverlayPresentationFrame.character(state, live), preferences)
    VanEmbodiment(state = rendered,
        modifier = modifier
            .vanPhysicalResponse(rendered, vanMotionEnabled(budget, animate = animate, reducedMotion = rememberReducedMotion()))
            .graphicsLayer { alpha = VanPersonalPresentation.opacity(rendered, preferences, passive) },
        presentation = presentation, budget = budget, characterFraction = characterFraction,
        animate = VanPersonalPresentation.motionAllowed(rendered, preferences, animate))
}
