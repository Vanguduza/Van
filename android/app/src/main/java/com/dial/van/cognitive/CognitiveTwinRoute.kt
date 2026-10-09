package com.dial.van.cognitive

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.dial.van.VanApplication
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.SectionHeader
import kotlinx.coroutines.delay

/** Same DDS CognitiveTwinProjection consumed by MCP App/Space; no independent state store. */
@Composable
fun CognitiveTwinRoute(app: VanApplication, onBack: () -> Unit) {
    val tokens = LocalVanTokens.current
    var tick by remember { mutableIntStateOf(0) }
    var body by remember { mutableStateOf<String?>(null) }
    var clock by remember { mutableStateOf(System.currentTimeMillis()) }
    LaunchedEffect(tick) {
        body = null
        body = runCatching { app.gatewayClient.cognitiveTwin() }.getOrElse { "{\"state\":\"DEGRADED\",\"reason\":\"TWIN_UNREACHABLE\"}" }
    }
    LaunchedEffect(Unit) {
        while (true) { delay(1000); clock = System.currentTimeMillis() }
    }
    val twin = body?.let { CognitiveTwin.parse(it) }
    LazyColumn(modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = tokens.space.pageGutter, vertical = tokens.space.space3),
        verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
        item { SectionHeader(title = "Cognitive Twin", detail = "Current DIAL projection and its evidence") }
        item { OutlinedButton(onClick = onBack) { Text("Back to Work") } }
        item { OutlinedButton(onClick = { tick += 1 }) { Text("Refresh from DIAL") } }
        if (body == null) item { Text("Reading the current projection…") }
        else if (twin == null) item { Text("Twin unavailable: ${CognitiveTwin.unavailableReason(body!!)}") }
        else {
            item { Text("${twin.scopeId} · ${twin.kind} · ${if (twin.staleAt(clock)) "STALE — refresh before relying on this view" else "CURRENT"}") }
            item { Text("Projection ${twin.projectionRevision}", style = tokens.type.body) }
            item { Text("Repository ${twin.repositorySha}\nProject Truth ${twin.projectTruthHash}\nMachine facts ${twin.machineFactsHash}", style = tokens.type.body) }
            val sections = listOf("Machine facts" to twin.facts, "Derived current state" to twin.derivedState,
                "Owner attention" to twin.attention, "Cognitive observations" to twin.observations,
                "Hypotheses" to twin.hypotheses, "Owner annotations" to twin.annotations)
            for ((title, records) in sections) {
                item { SectionHeader(title = title, detail = "${records.size} source records") }
                for (record in records.take(50)) item {
                    Text("${record.id} · ${record.authority}\n${record.summary}\n${record.evidenceRefs.joinToString("\n")}", style = tokens.type.body)
                }
            }
            item { Text("This view is a derived projection. Owner commands and approvals use VAN's existing authority path.", style = tokens.type.body) }
        }
    }
}
