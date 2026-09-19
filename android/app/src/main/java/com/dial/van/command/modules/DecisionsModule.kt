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
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.VanApplication
import com.dial.van.command.AdminCard
import com.dial.van.command.SectionHeader
import com.dial.van.command.TruthMessage
import com.dial.van.command.objectList
import kotlinx.coroutines.launch
import org.json.JSONObject

/** Decisions awaiting the owner. Split out of `CommandCentreActivity` (P3-AND-009). */

@Composable
internal fun DecisionsModule(app: VanApplication, glass: com.dial.van.visual.VanGlassStyle) {
    val scope = rememberCoroutineScope()
    var records by remember { mutableStateOf<List<JSONObject>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    fun refresh() {
        scope.launch {
            runCatching { app.gatewayClient.decisions().objectList() }
                .onSuccess { records = it; error = null }
                .onFailure { error = it.message ?: "Unable to load decisions" }
        }
    }
    LaunchedEffect(Unit) { refresh() }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { SectionHeader("Decisions", "Owner escalations returned by /v1/decisions") }
        if (records == null && error == null) item { TruthMessage("Loading decisions…") }
        if (error != null) item { TruthMessage(error!!, warning = true) }
        if (records?.isEmpty() == true) item { TruthMessage("Nothing is waiting on you.") }
        items(records.orEmpty(), key = { it.optString("id") }) { record ->
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(record.optString("title", "Decision"), color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.Bold)
                    Text(record.optString("body"), color = Color(0xFFD7E7EC), fontSize = 12.sp)
                    Text(
                        "Source: ${record.optString("source", "unknown")} • ${record.optString("status", "OPEN")}",
                        color = Color(0xFFBCD1D8),
                        fontSize = 10.sp,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = {
                            scope.launch {
                                runCatching { app.gatewayClient.resolveDecision(record.getString("id"), true) }
                                    .onSuccess { refresh() }
                                    .onFailure { error = it.message }
                            }
                        }) { Text("Approve") }
                        Button(
                            onClick = {
                                scope.launch {
                                    runCatching { app.gatewayClient.resolveDecision(record.getString("id"), false) }
                                        .onSuccess { refresh() }
                                        .onFailure { error = it.message }
                                }
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF5B2730)),
                        ) { Text("Reject") }
                    }
                }
            }
        }
        item { Button(onClick = { refresh() }) { Text("Refresh") } }
    }
}
