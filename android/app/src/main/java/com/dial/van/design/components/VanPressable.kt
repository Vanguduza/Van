package com.dial.van.design.components

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.dial.van.design.LocalVanTokens

/**
 * DNA §2: "Press scale 0.97 at `instant`" — the one press affordance every tappable VAN
 * surface uses, so a card, a chip and a mission row all compress by the same amount at the
 * same speed instead of each screen picking its own `animateFloatAsState` spec.
 *
 * Ripple is deliberately suppressed (`indication = null`): the scale *is* the feedback DNA
 * asks for, and stacking a Material ripple under a 3% scale reads as two different presses.
 *
 * Enforces the ≥48dp touch target itself via [Modifier.sizeIn] — a caller cannot accidentally
 * ship a 32dp icon button through this composable, because the minimum is baked into the one
 * place every pressable surface passes through.
 */
@Composable
fun VanPressable(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    /** DNA §2 Haptics: "confirm on approval completion, tick on dock/snap... Never on scroll." */
    hapticOnPress: Boolean = false,
    role: Role = Role.Button,
    contentDescription: String? = null,
    content: @Composable BoxScope.() -> Unit,
) {
    val tokens = LocalVanTokens.current
    val interactionSource = remember { MutableInteractionSource() }
    val pressed by interactionSource.collectIsPressedAsState()
    val scale by animateFloatAsState(
        targetValue = if (pressed) tokens.motion.pressScale else 1f,
        animationSpec = tween(
            durationMillis = tokens.motion.durations.instantMs,
            easing = tokens.motion.standardEasing,
        ),
        label = "VanPressableScale",
    )
    val haptics = LocalHapticFeedback.current
    var sized = Modifier
        .sizeIn(minWidth = MIN_TOUCH_TARGET_DP.dp, minHeight = MIN_TOUCH_TARGET_DP.dp)
        .graphicsLayer { scaleX = scale; scaleY = scale }
    if (contentDescription != null) {
        sized = sized.semantics { this.contentDescription = contentDescription }
    }
    Box(
        modifier = modifier
            .then(sized)
            .clip(RoundedCornerShape(tokens.radius.m))
            .clickable(
                interactionSource = interactionSource,
                indication = null,
                enabled = enabled,
                role = role,
                onClick = {
                    if (hapticOnPress) haptics.performHapticFeedback(HapticFeedbackType.LongPress)
                    onClick()
                },
            ),
        content = content,
    )
}

/** DNA constraint: "touch targets ≥ 48dp." */
const val MIN_TOUCH_TARGET_DP = 48
