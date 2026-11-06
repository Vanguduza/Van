package com.dial.van.visual

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalDensity

/** The native drag owner publishes event samples; no idle animation timer is created. */
object VanLiveInteractionResponse {
    var current by mutableStateOf(VanInteractionResponse()); private set
    fun drag(dxPx: Float, dyPx: Float, density: Float) { current = VanInteractionResponsePolicy.drag(dxPx,dyPx,density) }
    fun release() { current = VanInteractionResponse() }
}

@Composable
fun Modifier.vanPhysicalResponse(state: VanVisualState, enabled: Boolean): Modifier {
    if (!enabled || !VanInteractionResponsePolicy.compatible(state)) return this
    val response = VanLiveInteractionResponse.current
    val lean by animateFloatAsState(response.leanDegrees, spring(dampingRatio = .84f, stiffness = 700f), label = "van-drag-counterlean")
    val lift by animateFloatAsState(response.liftDp, spring(dampingRatio = .84f, stiffness = 700f), label = "van-dock-return")
    val density = LocalDensity.current.density
    return graphicsLayer { rotationZ = lean; translationY = lift * density }
}
