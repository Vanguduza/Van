package com.dial.van.overlay

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.visual.VanDoubleTapAction
import com.dial.van.visual.VanExpressionLevel

@Composable
internal fun OverlayPersonalControls(state: VanOverlaySurfaceState, actions: VanOverlayActions, accent: Int) {
    val p = state.preferences
    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        com.dial.van.visual.VanCharacterReviewNotice()
        Text("VAN behaviour", color = Color(accent), fontSize = 16.sp)
        Text("Warnings, approvals and explicit guidance stay visible in every mode.", color = Color(0xFFB8CBD2), fontSize = 12.sp)
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(5.dp)) {
            VanExpressionLevel.entries.forEach { level ->
                WorkChip(level.name.lowercase().replaceFirstChar { it.titlecase() }, accent,
                    enabled = state.localReady, selected = p.expression == level) { actions.onPreferences(p.copy(expression = level)) }
            }
        }
        PreferenceSwitch("Reduce motion", p.reducedMotion, state.localReady) { actions.onPreferences(p.copy(reducedMotion = it)) }
        Text("System reduced motion and thermal limits always take priority.", color = Color(0xFFB8CBD2), fontSize = 12.sp)
        Text("Resting visibility", color = Color(accent), fontSize = 13.sp)
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(5.dp)) {
            listOf(60,80,100).forEach { opacity ->
                WorkChip("$opacity%", accent, enabled = state.localReady, selected = p.idleOpacityPercent == opacity) {
                    actions.onPreferences(p.copy(idleOpacityPercent = opacity))
                }
            }
        }
        Text("Only an idle floating character dims. Conversations and critical states do not.", color = Color(0xFFB8CBD2), fontSize = 12.sp)
        Text("Double tap", color = Color(accent), fontSize = 13.sp)
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(5.dp)) {
            VanDoubleTapAction.entries.forEach { tap ->
                WorkChip(tap.name.lowercase().replaceFirstChar { it.titlecase() }, accent,
                    enabled = state.localReady, selected = p.doubleTap == tap) { actions.onPreferences(p.copy(doubleTap = tap)) }
            }
        }
        PreferenceSwitch("Keep an encrypted local draft", p.rememberDraft, state.localReady) { actions.onPreferences(p.copy(rememberDraft = it)) }
        Text("Recovery keeps the last completed save for up to seven days. Reopening never sends or starts voice.", color = Color(0xFFB8CBD2), fontSize = 12.sp)
        WorkChip("Discard local draft", accent, enabled = state.localReady) { actions.onDiscardDraft() }
        WorkChip("Retry local save", accent, enabled = state.localReady) { actions.onRetrySave() }
        Text(state.storageMessage, color = Color(0xFFB8CBD2), fontSize = 12.sp,
            modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite })
    }
}

@Composable
private fun PreferenceSwitch(label: String, checked: Boolean, enabled: Boolean, change: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = Color(0xFFE5EFF3), fontSize = 13.sp, modifier = Modifier.weight(1f))
        Switch(checked = checked, onCheckedChange = change, enabled = enabled, modifier = Modifier.semantics { contentDescription = label })
    }
}

@Composable
internal fun OverlayDraftRecovery(state: VanOverlaySurfaceState, actions: VanOverlayActions, accent: Int) {
    if (state.recoveredDraftAvailable) {
        Text("An earlier local draft is available. Check conversation/task status before resending; Resume opens it for review.", color = Color(0xFFE5EFF3), fontSize = 12.sp)
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            WorkChip("Resume draft", accent) { actions.onResumeDraft() }
            WorkChip("Discard", accent) { actions.onDiscardDraft() }
        }
    }
    Text(state.storageMessage, color = Color(0xFFB8CBD2), fontSize = 11.sp)
}
