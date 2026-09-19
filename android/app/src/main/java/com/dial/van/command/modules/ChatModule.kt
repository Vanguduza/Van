package com.dial.van.command.modules

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.fragment.app.FragmentActivity
import com.dial.van.VanApplication
import com.dial.van.command.AdminCard
import com.dial.van.command.CommandMessageBubble
import com.dial.van.command.TruthMessage
import com.dial.van.control.VanCommandSource
import com.dial.van.visual.VanGlassTokens

/** The owner's conversation with VAN. Split out of `CommandCentreActivity` (P3-AND-009). */

@Composable
internal fun ChatModule(app: VanApplication, glass: com.dial.van.visual.VanGlassStyle) {
    val state by app.commandController.state.collectAsState()
    var draft by remember { mutableStateOf("") }
    val activity = LocalContext.current as? FragmentActivity

    Column(modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp, vertical = 8.dp)) {
        AdminCard(glass) {
            Column {
                Text("Owner chat", color = Color.White, fontSize = 17.sp, fontWeight = FontWeight.Bold)
                Text(
                    state.selectedProjectId?.let { "Project context: $it" } ?: "Global owner context",
                    color = Color(VanGlassTokens.EDGE_CYAN),
                    fontSize = 11.sp,
                )
                Text(
                    "Typing and speaking reach VAN the same way.",
                    color = Color(0xFFBCD1D8),
                    fontSize = 10.sp,
                )
            }
        }
        Spacer(Modifier.height(8.dp))
        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(7.dp),
            contentPadding = PaddingValues(vertical = 6.dp),
        ) {
            if (state.messages.isEmpty()) {
                item { TruthMessage("No conversation messages yet.") }
            }
            items(state.messages, key = { it.id }) { message ->
                CommandMessageBubble(message, glass)
            }
        }
        state.pendingA4Approval?.let { pending ->
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(
                        "Owner approval required",
                        color = Color(VanGlassTokens.ACCENT_AMBER),
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        pending.resolvedActionId,
                        color = Color.White,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        "VAN needs your fingerprint or face before doing this, because you cannot easily undo it.",
                        color = Color(0xFFBCD1D8),
                        fontSize = 10.sp,
                    )
                    Button(
                        enabled = activity != null && !state.submitting,
                        onClick = { activity?.let { app.commandController.approvePendingA4(it) } },
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF6D4514)),
                    ) {
                        Text("Approve")
                    }
                    if (activity == null) {
                        Text(
                            "Biometric approval is unavailable on this surface.",
                            color = Color(VanGlassTokens.ACCENT_AMBER),
                            fontSize = 10.sp,
                        )
                    }
                }
            }
            Spacer(Modifier.height(8.dp))
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(7.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            OutlinedTextField(
                value = draft,
                onValueChange = { draft = it },
                modifier = Modifier.weight(1f),
                label = { Text("Owner command") },
                maxLines = 4,
            )
            Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Button(onClick = {
                    val text = draft.trim()
                    if (text.isNotEmpty()) {
                        app.commandController.submitText(text, VanCommandSource.CHAT)
                        draft = ""
                    }
                }) { Text("Send") }
                Button(onClick = { app.voiceSession.beginOwnerTurn() }) { Text("Voice") }
            }
        }
        if (state.submitting) {
            Text("Sending…", color = Color(VanGlassTokens.EDGE_CYAN), fontSize = 10.sp)
        }
    }
}
