package com.dial.van.overlay

import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.paneTitle
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import com.dial.van.visual.VanVisualState

private fun movementActions(actions: VanOverlayActions) = listOf(
    CustomAccessibilityAction("Move left") { actions.onMove(-1, 0) },
    CustomAccessibilityAction("Move right") { actions.onMove(1, 0) },
    CustomAccessibilityAction("Move up") { actions.onMove(0, -1) },
    CustomAccessibilityAction("Move down") { actions.onMove(0, 1) },
)

internal fun Modifier.vanAccessibleMovement(actions: VanOverlayActions): Modifier = semantics {
    customActions = movementActions(actions)
}

/** Named alternatives to double tap, long press and precision drag. */
internal fun Modifier.vanAccessibleCharacter(state: VanVisualState, actions: VanOverlayActions): Modifier = semantics {
    role = Role.Button
    stateDescription = state.durableState.name.lowercase().replace('_', ' ')
    customActions = listOf(
        CustomAccessibilityAction("Open chat") { actions.onChat(true); true },
        CustomAccessibilityAction("Open Command Centre") { actions.onCommandCentre(null); true },
        CustomAccessibilityAction("Start voice conversation") { actions.onVoice(); true },
        CustomAccessibilityAction("Stop voice; tasks continue") { actions.onStopVoice(); true },
        CustomAccessibilityAction("Minimize VAN") { actions.onPresentation(VanOverlayPresentation.MINIMIZED); true },
        CustomAccessibilityAction("Dock VAN") { actions.onPresentation(VanOverlayPresentation.DOCKED); true },
        CustomAccessibilityAction("Close floating assistant") { actions.onQuickControl("Close"); true },
    ) + movementActions(actions)
}

/** Own-window system Back and hardware Escape: IME first, then return to character. */
@Composable
internal fun Modifier.vanWorkboardKeyboard(state: VanOverlaySurfaceState, actions: VanOverlayActions): Modifier {
    val focus = LocalFocusManager.current
    val keyboard = LocalSoftwareKeyboardController.current
    val latest = rememberUpdatedState {
        when (OverlayUsabilityPolicy.dismiss(state.presentation in OverlayWindowFlags.WORKBOARDS, state.keyboardVisible)) {
            OverlayDismissStep.HIDE_KEYBOARD -> { keyboard?.hide(); focus.clearFocus(); true }
            OverlayDismissStep.RETURN_TO_CHARACTER -> { actions.onPresentation(VanOverlayPresentation.FULL_FLOATING); true }
            OverlayDismissStep.NONE -> false
        }
    }
    val ownsBack = state.presentation in OverlayWindowFlags.WORKBOARDS
    BindOverlaySystemBack(ownsBack, state.keyboardVisible) {
        actions.onPresentation(VanOverlayPresentation.FULL_FLOATING)
    }
    return this.semantics { paneTitle = "VAN workboard" }.onPreviewKeyEvent { event ->
        if (!ownsBack || (event.key != Key.Escape && event.key != Key.Back)) false
        else if (event.type == KeyEventType.KeyUp) latest.value() else true
    }
}
