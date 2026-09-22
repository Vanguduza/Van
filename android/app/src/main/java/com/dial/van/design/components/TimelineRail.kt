package com.dial.van.design.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.dial.van.design.LocalVanTokens

/** One entry on a [TimelineRail]: mission and trade events with actor + severity (DNA §3). */
data class TimelineEvent(
    val id: String,
    val title: String,
    val actor: String,
    val timeLabel: String,
    /** A [com.dial.van.design.StatusSemantics] role name. */
    val severityRole: String,
    val detail: String? = null,
)

/** The connector dot's diameter and the fallback connector-line height for a bare row. */
private val DOT_SIZE = 8.dp
private val CONNECTOR_MIN_HEIGHT = 24.dp

/**
 * A vertical rail of events, each dot coloured by its severity role. Ordering (newest-first
 * or oldest-first) is the caller's — this draws [events] in the order given.
 */
@Composable
fun TimelineRail(events: List<TimelineEvent>, modifier: Modifier = Modifier) {
    val tokens = LocalVanTokens.current
    Column(modifier = modifier) {
        events.forEachIndexed { index, event ->
            Row(
                modifier = Modifier
                    .semantics { contentDescription = "${event.actor}: ${event.title}, ${event.timeLabel}" },
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Box(
                        modifier = Modifier
                            .padding(top = tokens.space.space1)
                            .width(DOT_SIZE)
                            .height(DOT_SIZE)
                            .clip(CircleShape)
                            .background(tokens.color.forStatusRole(event.severityRole)),
                    )
                    if (index != events.lastIndex) {
                        Box(
                            modifier = Modifier
                                .width(tokens.radius.hairline)
                                .height(CONNECTOR_MIN_HEIGHT)
                                .background(tokens.color.lineHair),
                        )
                    }
                }
                Column(
                    modifier = Modifier
                        .padding(start = tokens.space.space3, bottom = tokens.space.space4)
                        .weight(1f, fill = false),
                    verticalArrangement = Arrangement.spacedBy(tokens.space.space1 / 2),
                ) {
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        Text(event.title, style = tokens.type.body, color = tokens.color.textPrimary)
                        Text(event.timeLabel, style = tokens.type.label, color = tokens.color.textTertiary)
                    }
                    Text(event.actor, style = tokens.type.label, color = tokens.color.textTertiary)
                    if (event.detail != null) {
                        Text(event.detail, style = tokens.type.body, color = tokens.color.textSecondary)
                    }
                }
            }
        }
    }
}
