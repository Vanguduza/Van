package com.dial.van.command.dev

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.EvidenceRow
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.design.components.VanPressable
import com.dial.van.dialdev.DevEvidenceRef
import com.dial.van.dialdev.DevHealthItem
import com.dial.van.dialdev.DevTaskRow
import com.dial.van.dialdev.DialDevAdmission
import com.dial.van.dialdev.DialDevEnvelope
import com.dial.van.dialdev.DialDevFormat
import com.dial.van.dialdev.DialDevHealth
import com.dial.van.dialdev.DialDevRoles
import com.dial.van.dialdev.DialDevSubsystems

/**
 * Shared pieces of the Development Control Centre screens. Tokens and catalogue components
 * only (DNA §2/§3): no colour, size or card is invented here.
 */

/** A list-first page: every development screen is a `LazyColumn`, so TalkBack reaches every row. */
@Composable
fun DevPage(content: LazyListScope.() -> Unit) {
    val tokens = LocalVanTokens.current
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter),
        verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
        contentPadding = PaddingValues(vertical = tokens.space.space3),
        content = content,
    )
}

/** A task row (§6.3): title, DU, stage, the §4 caption, why-now, harness/model/host, heartbeat. */
@Composable
fun DevTaskRowItem(task: DevTaskRow, onOpen: () -> Unit) {
    val tokens = LocalVanTokens.current
    val p = task.presentation
    VanPressable(
        onClick = onOpen,
        modifier = Modifier.fillMaxWidth(),
        contentDescription = "${task.title}. ${p.caption}. Open task ${task.taskId}.",
    ) {
        VanPanel(dense = true) {
            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                Text(task.title, style = tokens.type.body, color = tokens.color.textPrimary)
                StatusChip(label = p.caption, role = p.role)
                val where = listOfNotNull(task.taskId, task.du, task.stage).joinToString(" · ")
                Text(where, style = tokens.type.label, color = tokens.color.textTertiary)
                task.whyNow?.let { Text(it, style = tokens.type.body, color = tokens.color.textSecondary) }
                val runner = listOfNotNull(task.harness, task.model, task.host).joinToString(" · ")
                if (runner.isNotEmpty() || task.heartbeatAgeMs != null) {
                    Text(
                        listOf(runner, task.heartbeatAgeMs?.let { "heartbeat ${DialDevFormat.age(it)} ago" }).filter { !it.isNullOrBlank() }.joinToString(" · "),
                        style = tokens.type.label,
                        color = tokens.color.textTertiary,
                    )
                }
            }
        }
    }
}

/** A label/value pair; a value DIAL did not send reads "not reported", never a default. */
@Composable
fun DevField(label: String, value: String?) {
    val tokens = LocalVanTokens.current
    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2), verticalAlignment = Alignment.Top) {
        Text(label, style = tokens.type.label, color = tokens.color.textTertiary, modifier = Modifier.weight(0.4f))
        Text(
            value?.takeIf { it.isNotBlank() } ?: "not reported",
            style = tokens.type.body,
            color = if (value.isNullOrBlank()) tokens.color.textTertiary else tokens.color.textPrimary,
            modifier = Modifier.weight(0.6f),
        )
    }
}

/** A titled group of [DevField]s in one acrylic panel. */
@Composable
fun DevFieldGroup(title: String, fields: List<Pair<String, String?>>) {
    val tokens = LocalVanTokens.current
    VanPanel {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Text(title, style = tokens.type.headline, color = tokens.color.textPrimary)
            fields.forEach { (label, value) -> DevField(label, value) }
        }
    }
}

/** A chip for a free-form DIAL state word, via the exhaustive vocabularies in `DialDevStatusRoles`. */
@Composable
fun DevHealthChip(item: DevHealthItem) {
    val role = DialDevRoles.roleOrDisabled(DialDevHealth.parse(item.rawState), DialDevRoles::health)
    StatusChip(label = "${DialDevSubsystems.label(item.subsystem)} ${DialDevRoles.chipLabel(item.rawState)}", role = role)
}

/** §6.1 health strip: one chip per subsystem; the whole strip opens `connected`. */
@Composable
fun DevHealthStrip(items: List<DevHealthItem>, onOpen: () -> Unit) {
    val tokens = LocalVanTokens.current
    VanPressable(onClick = onOpen, modifier = Modifier.fillMaxWidth(), contentDescription = "Development fabric health. Open Connected.") {
        LazyRow(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            items(items, key = { it.subsystem }) { DevHealthChip(it) }
        }
    }
}

/** An evidence reference as an [EvidenceRow]: admission state is the trust tier. */
@Composable
fun DevEvidenceItem(ref: DevEvidenceRef, onOpen: (String) -> Unit) {
    val role = DialDevRoles.roleOrDisabled(DialDevAdmission.parse(ref.admission), DialDevRoles::admission)
    EvidenceRow(
        source = listOfNotNull(ref.kind, ref.ref).joinToString(" · "),
        trustTier = DialDevRoles.chipLabel(ref.admission),
        trustRole = role,
        timeLabel = listOfNotNull(ref.result, ref.observedAt).joinToString(" · ").ifBlank { "time not reported" },
        onOpen = { onOpen(ref.ref) },
    )
}

/** Footer: which projection revision the screen shows, so an action's basis is visible. */
@Composable
fun DevRevisionFooter(envelope: DialDevEnvelope?) {
    val tokens = LocalVanTokens.current
    val revision = envelope?.projectionRevision ?: return
    Text(
        "Projection ${DialDevFormat.shortSha(revision)} · observed ${envelope.observedAt ?: "time not reported"}",
        style = tokens.type.label,
        color = tokens.color.textTertiary,
    )
}

/** A plain sentence for an empty section inside otherwise live content. */
@Composable
fun DevNote(text: String, warning: Boolean = false) {
    val tokens = LocalVanTokens.current
    Text(
        text,
        style = tokens.type.body,
        color = if (warning) tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK) else tokens.color.textSecondary,
    )
}
