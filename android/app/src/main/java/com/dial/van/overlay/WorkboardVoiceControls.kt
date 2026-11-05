package com.dial.van.overlay

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.distinctUntilChanged
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.VanApplication

/** Microphone, speech and task cancellation are deliberately separate meanings. */
@Composable
internal fun WorkboardVoiceControls(app: VanApplication, actions: VanOverlayActions, accent: Int) {
    val input by app.voiceUi.state.collectAsState()
    val turnPending by app.voiceSession.ownerTurnActive.collectAsState()
    val speaking by remember(app) { app.ttsOutput.visualState.map { it.speaking }.distinctUntilChanged() }.collectAsState(false)
    val status = OverlayUsabilityPolicy.voiceStatus(input.listening, speaking, turnPending)
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Text(status, color = Color(accent), fontSize = 12.sp,
            modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite })
        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(5.dp)) {
            if (input.listening) WorkChip("Send voice", accent) { app.voiceSession.endOwnerTurn() }
            else WorkChip("Start listening", accent, enabled = !turnPending) { actions.onVoice() }
            WorkChip("Stop voice", accent, enabled = input.listening || turnPending || speaking) { actions.onStopVoice() }
        }
        if (input.errorCode != null) Text("Voice input unavailable. Try again or type a message.", color = Color(0xFFFFB300), fontSize = 12.sp)
        if (input.errorCode != null) Text("Voice input stopped. Retry when ready or use text.",
            color = Color(0xFFFFC166), fontSize = 12.sp,
            modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite })
        if (input.partialTranscript.isNotBlank()) Text(input.partialTranscript, color = Color(0xFFB8CBD2), fontSize = 12.sp, maxLines = 2)
        Text("Stopping voice does not cancel submitted tasks.", color = Color(0xFFB8CBD2), fontSize = 11.sp)
    }
}
