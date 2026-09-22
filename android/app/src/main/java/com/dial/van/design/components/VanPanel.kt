package com.dial.van.design.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.dial.van.design.LocalVanTokens

/**
 * DNA §1: "Panels are acrylic (opaque surface tier + 1px hairline + soft shadow). No glass on
 * cards." Every screen except the embodiment shell and the overlay draws its containers with
 * this, never with `com.dial.van.visual.VanGlassSurface` — that composable is reserved for the
 * one glass shell per screen DNA's glass policy allows, and `android_design_lint.py` flags a
 * bare `Card(`/`ElevatedCard(` outside `design/` precisely so a screen reaches for this
 * instead of Material's own card or the glass surface.
 */
@Composable
fun VanPanel(
    modifier: Modifier = Modifier,
    dense: Boolean = false,
    header: (@Composable () -> Unit)? = null,
    content: @Composable () -> Unit,
) {
    val tokens = LocalVanTokens.current
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(tokens.radius.m),
        color = tokens.color.surfaceAcrylic,
        contentColor = tokens.color.textPrimary,
        border = BorderStroke(tokens.radius.hairline, tokens.color.lineHair),
        tonalElevation = tokens.elevation.panel,
        shadowElevation = tokens.elevation.panel,
    ) {
        Column(modifier = Modifier.padding(tokens.space.panelPaddingFor(dense))) {
            if (header != null) {
                header()
            }
            content()
        }
    }
}
