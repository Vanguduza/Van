package com.dial.van.overlay

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
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
) {
    val live = VanLiveVisualState.frame
    VanEmbodiment(state = OverlayPresentationFrame.character(state, live), modifier = modifier,
        presentation = presentation, budget = budget, characterFraction = characterFraction, animate = animate)
}
