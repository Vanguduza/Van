package com.dial.van.command.modules

import com.dial.van.runtime.DeviceRuntimeReadings
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.VanApplication
import com.dial.van.command.AdminCard
import com.dial.van.command.SectionHeader
import com.dial.van.command.TruthMessage
import com.dial.van.command.objectList
import com.dial.van.events.EventPage
import com.dial.van.events.EventRecord
import com.dial.van.events.EventStream
import kotlinx.coroutines.delay

/**
 * The delegated agents/activity feed. Split out of `CommandCentreActivity` (P3-AND-009);
 * `TasksModule` and `ProjectsModule` — this file's other two former occupants — are
 * superseded by the Work route's own conversation+missions surface and by the `projects/`
 * package's `ProjectsRoute`, so only the event stream remains here, called as a Work child
 * (`work/activity`, DNA §4: "delegated agents, activity feed").
 */

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
    // The app's history, not this screen's. It used to be `remember`ed here, which meant
    // it existed only while this screen was composed: a mission finishing while the owner
    // was anywhere else produced nothing they could see, and §20.1's socket had nowhere to
    // deliver a durable page to.
    val store = app.eventStream
    val stream by store.state.collectAsState()
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
            runCatching { app.gatewayClient.events(store.cursor()) }
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
                        nextCursor = body.optLong("next_cursor", store.cursor()),
                        truncated = body.optBoolean("truncated", false),
                    )
                    truncated = page.truncated
                    // Into the shared history, which saves the cursor itself — and
                    // merges seq-keyed with whatever the socket has already pushed.
                    store.apply(page)
                }
                .onFailure { failure ->
                    store.fail(failure.message ?: "Unable to load activity")
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
