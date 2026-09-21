package com.dial.van.command.modules

import com.dial.van.runtime.DeviceRuntimeReadings
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.VanApplication
import com.dial.van.command.AdminCard
import com.dial.van.command.CommandMessageBubble
import com.dial.van.command.SectionHeader
import com.dial.van.command.TruthMessage
import com.dial.van.command.objectList
import com.dial.van.command.stringList
import com.dial.van.control.VanMessageRole
import com.dial.van.events.EventPage
import com.dial.van.events.EventRecord
import com.dial.van.events.EventStream
import com.dial.van.events.EventStreamState
import com.dial.van.events.PreferencesEventCursorStore
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Tasks, projects and activity. Split out of `CommandCentreActivity` (P3-AND-009). */

@Composable
internal fun TasksModule(
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
    openChat: () -> Unit,
) {
    val conversation by app.commandController.state.collectAsState()
    val operational = conversation.messages.filter { it.status != null && it.role != VanMessageRole.OWNER }
    val queueCount = app.commandQueue.size()

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { SectionHeader("Tasks", "What VAN is doing, and what is waiting to be sent") }
        item {
            AdminCard(glass) {
                Column {
                    Text("Encrypted offline queue", color = Color.White, fontWeight = FontWeight.Bold)
                    Text("$queueCount command(s) currently queued", color = Color(0xFFBCD1D8), fontSize = 12.sp)
                }
            }
        }
        if (operational.isEmpty()) item { TruthMessage("No dispatched owner work is present in this session.") }
        items(operational.reversed(), key = { it.id }) { message ->
            CommandMessageBubble(message, glass)
        }
        item { Button(onClick = openChat) { Text("Send instruction") } }
    }
}

@Composable
internal fun ProjectsModule(
    app: VanApplication,
    glass: com.dial.van.visual.VanGlassStyle,
    selectForChat: (String) -> Unit,
) {
    val scope = rememberCoroutineScope()
    var projects by remember { mutableStateOf<List<String>?>(null) }
    var truthSummary by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        runCatching { app.gatewayClient.projects().stringList() }
            .onSuccess { projects = it }
            .onFailure { error = it.message ?: "VAN could not read your projects just now." }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { SectionHeader("Projects", "What VAN knows you are working on") }
        if (projects == null && error == null) item { TruthMessage("Loading project registry…") }
        if (error != null) item { TruthMessage(error!!, warning = true) }
        if (projects?.isEmpty() == true) item { TruthMessage("Gateway returned no registered projects.") }
        items(projects.orEmpty(), key = { it }) { projectId ->
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(projectId, color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.Bold)
                    truthSummary[projectId]?.let { Text(it, color = Color(0xFFBCD1D8), fontSize = 10.sp, maxLines = 4) }
                    Row(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                        Button(onClick = { selectForChat(projectId) }) { Text("Select + Chat") }
                        Button(onClick = {
                            scope.launch {
                                runCatching { app.gatewayClient.projectTruth(projectId) }
                                    .onSuccess { obj ->
                                        val summary = if (obj.optBoolean("ok")) {
                                            "Truth ${obj.optString("truth_sha").take(12)} • repo ${obj.optString("repo_sha").take(12)}"
                                        } else {
                                            "Truth unavailable: ${obj.optString("error", obj.optString("degraded", "unknown"))}"
                                        }
                                        truthSummary = truthSummary + (projectId to summary)
                                    }
                                    .onFailure { t -> truthSummary = truthSummary + (projectId to "Truth load failed: ${t.message}") }
                            }
                        }) { Text("Truth") }
                    }
                }
            }
        }
    }
}

/**
 * P3-AND-002 — the event stream, actually streamed.
 *
 * This was a single `events(0)` in the initial composition with a hardcoded cursor. Anything
 * the gateway published afterwards never reached the screen. It now restores a persisted
 * cursor, polls continuously, catches up immediately on a truncated page and backs off on
 * failure — all decided by [EventStream], which is pure and tested on the JVM.
 */

@Composable
internal fun ActivityModule(app: VanApplication, glass: com.dial.van.visual.VanGlassStyle) {
    val context = LocalContext.current
    val cursorStore = remember(context) { PreferencesEventCursorStore(context) }
    var stream by remember { mutableStateOf(EventStreamState(cursor = cursorStore.load())) }
    val events = if (stream.loaded) stream.events else null
    val error = stream.error
        ?: if (!app.gatewayClient.isEnrolled()) {
            "Device is not enrolled; event replay requires an enrolled device identity."
        } else {
            null
        }

    LaunchedEffect(Unit) {
        if (!app.gatewayClient.isEnrolled()) return@LaunchedEffect
        while (true) {
            var truncated = false
            runCatching { app.gatewayClient.events(stream.cursor) }
                .onSuccess { body ->
                    val page = EventPage(
                        events = body.optJSONArray("events")?.objectList().orEmpty().map {
                            EventRecord(
                                seq = it.optLong("seq"),
                                type = it.optString("event_type", "event"),
                                payloadJson = it.optJSONObject("payload")?.toString() ?: "",
                                createdAtUnix = it.optLong("created_at_unix"),
                            )
                        },
                        nextCursor = body.optLong("next_cursor", stream.cursor),
                        truncated = body.optBoolean("truncated", false),
                    )
                    truncated = page.truncated
                    stream = EventStream.applyPage(stream, page)
                    cursorStore.save(stream.cursor)
                }
                .onFailure { failure ->
                    stream = EventStream.applyFailure(
                        stream, failure.message ?: "Unable to load activity",
                    )
                }
            // P3-PERF-003 — the poll rate answers to the whole-runtime envelope. A null
            // means the device has minutes left and this stream is not what the owner would
            // spend them on; the loop ends rather than spinning, and a new composition
            // restarts it once the phone recovers.
            val wait = EventStream.nextDelayMillis(
                stream, truncated, DeviceRuntimeReadings.pressure(context),
            ) ?: break
            delay(wait)
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { SectionHeader("Activity", "Gateway event replay") }
        if (events == null && error == null) item { TruthMessage("Loading activity…") }
        if (error != null) item { TruthMessage(error!!, warning = true) }
        if (events?.isEmpty() == true) item { TruthMessage("No gateway events returned.") }
        items(events.orEmpty(), key = { it.seq }) { event ->
            AdminCard(glass) {
                Column {
                    Text(event.type, color = Color.White, fontWeight = FontWeight.Bold)
                    Text(
                        event.payloadJson.take(360).ifEmpty { "No payload" },
                        color = Color(0xFFBCD1D8),
                        fontSize = 10.sp,
                    )
                }
            }
        }
    }
}
