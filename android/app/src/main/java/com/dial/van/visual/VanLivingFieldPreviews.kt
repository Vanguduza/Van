package com.dial.van.visual

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp

/**
 * IDE previews of the shipping Compose field. These complement the JVM evidence sheets, whose
 * Java2D aura painter remains a separate certification surface until it is migrated to the same
 * directional-flow geometry.
 */
@Preview(name = "Living field — idle", widthDp = 160, heightDp = 160, showBackground = false)
@Composable
private fun PreviewLivingFieldIdle() {
    VanEmbodiment(
        state = VanVisualState(durableState = VanDurableState.IDLE),
        budget = VanEffectBudget.FULL,
        characterFraction = 0.58f,
        modifier = Modifier.size(160.dp).background(Color(0xFF070B10)),
    )
}

@Preview(name = "Living field — working", widthDp = 160, heightDp = 160, showBackground = false)
@Composable
private fun PreviewLivingFieldWorking() {
    VanEmbodiment(
        state = VanVisualState(durableState = VanDurableState.WORKING, attentionX = 0.35f),
        budget = VanEffectBudget.FULL,
        characterFraction = 0.58f,
        modifier = Modifier.size(160.dp).background(Color(0xFF070B10)),
    )
}

@Preview(name = "Living field — warning", widthDp = 160, heightDp = 160, showBackground = false)
@Composable
private fun PreviewLivingFieldWarning() {
    VanEmbodiment(
        state = VanVisualState(durableState = VanDurableState.WARNING, urgency = 0.65f),
        budget = VanEffectBudget.FULL,
        characterFraction = 0.58f,
        modifier = Modifier.size(160.dp).background(Color(0xFF070B10)),
    )
}

@Preview(name = "Living field — reduced motion", widthDp = 160, heightDp = 160, showBackground = false)
@Composable
private fun PreviewLivingFieldReducedMotion() {
    VanEmbodiment(
        state = VanVisualState(durableState = VanDurableState.WAITING_FOR_OWNER),
        budget = VanEffectBudget.REDUCED_MOTION,
        characterFraction = 0.58f,
        modifier = Modifier.size(160.dp).background(Color(0xFF070B10)),
    )
}
