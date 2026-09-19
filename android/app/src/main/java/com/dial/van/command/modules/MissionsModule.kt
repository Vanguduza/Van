package com.dial.van.command.modules

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.VanApplication
import com.dial.van.command.AdminCard
import com.dial.van.command.SectionHeader
import com.dial.van.command.TruthMessage
import com.dial.van.mission.HomeSnapshot
import com.dial.van.mission.MissionRepository
import com.dial.van.mission.MissionSummary
import kotlinx.coroutines.launch

/**
 * What VAN is doing, and what is waiting on the owner.
 *
 * P2-AND-015. `MissionRepository` is 371 lines of correct owner language whose own
 * docstring says it is "the only place the surfaces get data", and no production file
 * constructed it. Eighteen `VanGatewayClient` reads existed for it and were called by
 * nothing else. The mission surfaces §§33, 35 and 48 describe — what is running, what is
 * waiting on you, whether it was actually checked — were rendered nowhere, so the owner
 * could issue a command and had no screen that would ever tell them how it went.
 *
 * Three things this screen does that a list of missions would not:
 *
 * **It shows the gateway's own status rather than deriving one.** `MissionSummary.ownerStatus`
 * prefers `ownerStatusFromGateway` and falls back to UNKNOWN, never to a working state.
 * P0-EXEC-003 found a projection painting unverified outcomes in the working colour; the
 * projection is the gateway's to make and this renders it.
 *
 * **It separates waiting from working.** A mission in WAITING_FOR_OWNER is not progressing,
 * and showing it among the active ones would tell the owner VAN is busy when it is in fact
 * stuck on them. `HomeSnapshot` already draws that line and the screen keeps it.
 *
 * **It says when something was not checked.** §6's distinction — done, partly done, and
 * finished-but-unconfirmed — reaches the screen through `ownerReadableStatus` rather than
 * being flattened into a tick.
 */
@Composable
internal fun MissionsModule(app: VanApplication, glass: com.dial.van.visual.VanGlassStyle) {
    val scope = rememberCoroutineScope()
    val repository = remember(app) { MissionRepository(app.gatewayClient) }
    var snapshot by remember { mutableStateOf<HomeSnapshot?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    // P2-AND-016 — survives rotation and process death. Losing which mission the owner had
    // open because they turned the phone is a small thing that reads as VAN forgetting.
    var expanded by rememberSaveable { mutableStateOf<String?>(null) }

    fun refresh() {
        scope.launch {
            runCatching { repository.home() }
                .onSuccess { snapshot = it; error = null }
                .onFailure { error = it.message ?: "Unable to reach Van" }
        }
    }
    LaunchedEffect(Unit) { refresh() }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { SectionHeader("Work", "What Van is doing, and what is waiting on you") }

        // "Could not ask" and "nothing is happening" are different answers, and the audit
        // kept finding them collapsed into an empty list.
        if (snapshot == null && error == null) item { TruthMessage("Loading…") }
        if (error != null) item { TruthMessage(error!!, warning = true) }

        val current = snapshot
        if (current != null) {
            if (current.degraded.isNotEmpty()) {
                item {
                    TruthMessage(
                        "Van is not fully working: ${current.degraded.joinToString(", ")}",
                        warning = true,
                    )
                }
            }

            if (current.waitingMissions.isNotEmpty()) {
                item { SectionHeader("Waiting for you", "These are not progressing") }
                items(current.waitingMissions, key = { "wait-${it.missionId}" }) { mission ->
                    MissionCard(glass, mission, expanded == mission.missionId) {
                        expanded = if (expanded == mission.missionId) null else mission.missionId
                    }
                }
            }

            item { SectionHeader("Running", "Van is working on these") }
            if (current.activeMissions.isEmpty()) {
                item { TruthMessage("Nothing is running.") }
            }
            items(current.activeMissions, key = { "run-${it.missionId}" }) { mission ->
                MissionCard(glass, mission, expanded == mission.missionId) {
                    expanded = if (expanded == mission.missionId) null else mission.missionId
                }
            }
        }

        item { Button(onClick = { refresh() }) { Text("Refresh") } }
    }
}

@Composable
private fun MissionCard(
    glass: com.dial.van.visual.VanGlassStyle,
    mission: MissionSummary,
    expanded: Boolean,
    onToggle: () -> Unit,
) {
    AdminCard(glass) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(
                mission.title,
                color = Color.White,
                fontSize = 15.sp,
                fontWeight = FontWeight.Bold,
            )
            // The owner's situation, not the state machine's name for it.
            Text(mission.ownerReadableStatus, color = Color(0xFFD7E7EC), fontSize = 12.sp)
            if (expanded) {
                Text(mission.goal, color = Color(0xFFBCD1D8), fontSize = 11.sp)
                mission.finalOutcome?.let {
                    Text(it, color = Color(0xFFBCD1D8), fontSize = 11.sp)
                }
                // Stated rather than implied by absence: §6 insists that "not checked" is
                // a different answer from "checked and fine", and a screen that shows only
                // the first is the screen P0-VERIFY-001 was about.
                Text(
                    "Verification: ${mission.verificationState}",
                    color = Color(0xFFBCD1D8),
                    fontSize = 11.sp,
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = onToggle,
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF1E3A44)),
                ) { Text(if (expanded) "Less" else "Details") }
            }
        }
    }
}
