package com.dial.van.memory

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import com.dial.van.VanApplication
import com.dial.van.control.VanCommandSource
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.ScreenAction
import com.dial.van.design.ScreenState
import com.dial.van.design.ScreenStateMerge
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.design.components.VanPressable
import com.dial.van.design.components.VanScreen
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * DNA §4 destination 5: "Memory — facts, decisions, assumptions, preferences, unresolved
 * threads, provenance; add/correct/forget."
 *
 * @DataSource("GET /v1/context/export") — every fact VAN holds, with provenance. Preferred
 * over `GET /v1/context/memory` (`contextMemory()`), which is a per-store row *count*
 * (`backend/van_gateway/context/forget.py::OwnerMemory.inventory`) and carries no
 * subject/predicate/value at all — nothing this screen shows could come from it.
 * @DataSource("GET /v1/context/conflicts") — "things I'm unsure about".
 *
 * `contextExport()` is not yet on `VanGatewayClient` (see this worker's handback report);
 * it is called here by the name the manager is asked to add, mirroring `GET
 * /v1/context/export` exactly the way `contextMemory()` mirrors `GET /v1/context/memory`.
 */
private data class MemoryData(
    val facts: List<MemoryFact>,
    val conflicts: List<MemoryConflict>,
)

private enum class MemoryDialog { NONE, REMEMBER, CORRECT, FORGET }

@Composable
fun MemoryRoute(app: VanApplication, onBack: () -> Unit) {
    val tokens = LocalVanTokens.current
    val scope = rememberCoroutineScope()
    var data by remember { mutableStateOf<MemoryData?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var notice by remember { mutableStateOf<String?>(null) }
    var dialog by remember { mutableStateOf(MemoryDialog.NONE) }
    var actingOn by remember { mutableStateOf<MemoryFact?>(null) }

    fun load() {
        scope.launch {
            loading = true
            runCatching {
                MemoryData(
                    facts = MemoryReadModel.parseExportFacts(app.gatewayClient.contextExport()),
                    conflicts = MemoryReadModel.parseConflicts(app.gatewayClient.contextConflicts()),
                )
            }.onSuccess { data = it; error = null; loading = false }
                .onFailure { error = it.message ?: "VAN could not open its own memory."; loading = false }
        }
    }
    LaunchedEffect(Unit) { load() }

    val state: ScreenState<MemoryData> = ScreenStateMerge.merge(
        content = data,
        loading = loading,
        errorMessage = error,
        emptySentence = "VAN does not hold anything about you yet.",
        emptyAction = ScreenAction("Remember something"),
    )

    VanScreen(state = state, onRetry = ::load, onEmptyAction = { dialog = MemoryDialog.REMEMBER }) { memory ->
        val now = System.currentTimeMillis()
        val byScope = MemoryReadModel.factsByScope(memory.facts, now)
        val decisions = MemoryReadModel.decisions(memory.facts, now)
        val preferences = MemoryReadModel.preferences(memory.facts, now)
        val recent = MemoryReadModel.recentChanges(memory.facts)
        val uncertainty = MemoryReadModel.uncertainty(memory.facts, memory.conflicts, now)

        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(horizontal = tokens.space.pageGutter),
            verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
            contentPadding = PaddingValues(vertical = tokens.space.space3),
        ) {
            item {
                SectionHeader(
                    "Memory",
                    detail = "What VAN knows about you, and why it believes it",
                    trailing = {
                        OutlinedButton(onClick = { dialog = MemoryDialog.REMEMBER }) {
                            Text("Remember", style = tokens.type.label)
                        }
                    },
                )
            }

            notice?.let { message ->
                item {
                    VanPanel(dense = true) {
                        Text(message, style = tokens.type.label, color = tokens.color.textSecondary)
                    }
                }
            }

            item { SectionHeader("What I know about you", detail = if (byScope.isEmpty()) null else "${byScope.values.sumOf { it.size }} facts") }
            if (byScope.isEmpty()) {
                item { Text("Nothing here yet.", style = tokens.type.body, color = tokens.color.textSecondary) }
            }
            byScope.forEach { (scopeName, facts) ->
                item {
                    Text(scopeName, style = tokens.type.label, color = tokens.color.textTertiary)
                }
                items(facts, key = { "know:" + it.factId }) { fact ->
                    FactRow(
                        fact = fact,
                        now = now,
                        onCorrect = { actingOn = fact; dialog = MemoryDialog.CORRECT },
                        onForget = { actingOn = fact; dialog = MemoryDialog.FORGET },
                    )
                }
            }

            item { SectionHeader("Decisions you made") }
            if (decisions.isEmpty()) {
                item { Text("No decisions recorded yet — say \"record decision: …\" and VAN will keep it.", style = tokens.type.body, color = tokens.color.textSecondary) }
            }
            items(decisions, key = { "decision:" + it.factId }) { fact ->
                FactRow(fact = fact, now = now, onCorrect = { actingOn = fact; dialog = MemoryDialog.CORRECT }, onForget = { actingOn = fact; dialog = MemoryDialog.FORGET })
            }

            item { SectionHeader("Preferences") }
            if (preferences.isEmpty()) {
                item { Text("VAN has not learned any preferences yet.", style = tokens.type.body, color = tokens.color.textSecondary) }
            }
            items(preferences, key = { "pref:" + it.factId }) { fact ->
                FactRow(fact = fact, now = now, onCorrect = { actingOn = fact; dialog = MemoryDialog.CORRECT }, onForget = { actingOn = fact; dialog = MemoryDialog.FORGET })
            }

            item { SectionHeader("Things I'm unsure about", detail = if (uncertainty.isEmpty) "Nothing right now" else null) }
            if (uncertainty.isEmpty) {
                item { Text("No contradictions and nothing about to lapse.", style = tokens.type.body, color = tokens.color.textSecondary) }
            }
            items(uncertainty.conflicts, key = { "conflict:" + it.subject + it.predicate + it.scope }) { conflict ->
                ConflictCard(
                    conflict = conflict,
                    onResolve = { side ->
                        scope.launch {
                            runCatching {
                                app.gatewayClient.stateOwnerFact(conflict.subject, conflict.predicate, side.value, conflict.scope)
                            }.onSuccess { notice = "VAN will use \"${side.value}\" from now on."; load() }
                                .onFailure { notice = "Could not resolve: ${it.message}" }
                        }
                    },
                )
            }
            items(uncertainty.staleOrExpiring, key = { "stale:" + it.factId }) { fact ->
                FactRow(fact = fact, now = now, onCorrect = { actingOn = fact; dialog = MemoryDialog.CORRECT }, onForget = { actingOn = fact; dialog = MemoryDialog.FORGET }, showFreshness = true)
            }

            item { SectionHeader("Recent changes") }
            if (recent.isEmpty()) {
                item { Text("Nothing has changed yet.", style = tokens.type.body, color = tokens.color.textSecondary) }
            }
            items(recent, key = { "recent:" + it.factId }) { fact ->
                VanPanel(dense = true) {
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                        Text("${fact.predicate.replace('_', ' ')} → ${fact.value}", style = tokens.type.body, color = tokens.color.textPrimary)
                        Text(RelativeTime.describe(fact.validFromMs, now), style = tokens.type.label, color = tokens.color.textTertiary)
                    }
                }
            }
        }
    }

    if (dialog == MemoryDialog.REMEMBER) {
        RememberDialog(
            onDismiss = { dialog = MemoryDialog.NONE },
            onSubmitStatement = { statement ->
                dialog = MemoryDialog.NONE
                app.commandController.submitText("remember that $statement", VanCommandSource.CHAT)
                notice = "Sent to VAN to remember."
                scope.launch { delay(1_200); load() }
            },
            onSubmitStructured = { predicate, value ->
                dialog = MemoryDialog.NONE
                scope.launch {
                    runCatching { app.gatewayClient.stateOwnerFact("OWNER", predicate, value, "global") }
                        .onSuccess { notice = "Remembered."; load() }
                        .onFailure { notice = "Could not remember that: ${it.message}" }
                }
            },
        )
    }

    if (dialog == MemoryDialog.CORRECT) {
        actingOn?.let { fact ->
            CorrectDialog(
                fact = fact,
                onDismiss = { dialog = MemoryDialog.NONE },
                onSubmit = { newValue ->
                    dialog = MemoryDialog.NONE
                    scope.launch {
                        runCatching { app.gatewayClient.stateOwnerFact(fact.subject, fact.predicate, newValue, fact.scope) }
                            .onSuccess { notice = "Updated."; load() }
                            .onFailure { notice = "Could not correct: ${it.message}" }
                    }
                },
            )
        }
    }

    if (dialog == MemoryDialog.FORGET) {
        actingOn?.let { fact ->
            AlertDialog(
                onDismissRequest = { dialog = MemoryDialog.NONE },
                title = { Text("Forget this?") },
                text = { Text("VAN will stop treating \"${fact.predicate.replace('_', ' ')}\" as \"${fact.value}\". This does not undo anything already done with it.") },
                confirmButton = {
                    Button(
                        onClick = {
                            dialog = MemoryDialog.NONE
                            scope.launch {
                                runCatching { app.gatewayClient.forgetOwnerFact(fact.subject, fact.predicate, fact.scope) }
                                    .onSuccess { notice = "Forgotten."; load() }
                                    .onFailure { notice = "Could not forget: ${it.message}" }
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = LocalVanTokens.current.color.forStatusRole(StatusSemantics.ROLE_CRITICAL)),
                    ) { Text("Forget") }
                },
                dismissButton = { TextButton(onClick = { dialog = MemoryDialog.NONE }) { Text("Cancel") } },
            )
        }
    }
}

@Composable
private fun FactRow(
    fact: MemoryFact,
    now: Long,
    onCorrect: () -> Unit,
    onForget: () -> Unit,
    showFreshness: Boolean = false,
) {
    val tokens = LocalVanTokens.current
    val tier = ProvenanceTiers.forAuthority(fact.authority)
    VanPanel(dense = true) {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(tokens.space.space2),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(fact.predicate.replace('_', ' '), style = tokens.type.headline, color = tokens.color.textPrimary)
                    Text(fact.value, style = tokens.type.body, color = tokens.color.textSecondary)
                }
                StatusChip(label = tier.name, role = ProvenanceTiers.statusRole(tier))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                Text("Confidence ${fact.confidencePercent}%", style = tokens.type.label, color = tokens.color.textTertiary)
                if (showFreshness || fact.validUntilMs != null) {
                    Text(RelativeTime.describeValidity(fact.validUntilMs, now), style = tokens.type.label, color = tokens.color.textTertiary)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
                TextButton(onClick = onCorrect) { Text("Correct", style = tokens.type.label) }
                TextButton(onClick = onForget) { Text("Forget", style = tokens.type.label) }
            }
        }
    }
}

@Composable
private fun ConflictCard(conflict: MemoryConflict, onResolve: (MemoryConflictSide) -> Unit) {
    val tokens = LocalVanTokens.current
    VanPanel {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                Text(conflict.predicate.replace('_', ' '), style = tokens.type.headline, color = tokens.color.textPrimary)
                StatusChip(
                    label = if (conflict.blocking) "CONFLICT" else "UNCONFIRMED CONFLICT",
                    role = if (conflict.blocking) StatusSemantics.ROLE_CRITICAL else StatusSemantics.ROLE_EVENT_RISK,
                )
            }
            Text("VAN holds two different answers for this. You choose which stands.", style = tokens.type.label, color = tokens.color.textTertiary)
            conflict.sides.forEach { side ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(tokens.space.space2),
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(side.value, style = tokens.type.body, color = tokens.color.textPrimary)
                        Text(side.authority, style = tokens.type.label, color = tokens.color.textTertiary)
                    }
                    OutlinedButton(onClick = { onResolve(side) }) { Text("Use this", style = tokens.type.label) }
                }
            }
        }
    }
}

@Composable
private fun RememberDialog(
    onDismiss: () -> Unit,
    onSubmitStatement: (String) -> Unit,
    onSubmitStructured: (predicate: String, value: String) -> Unit,
) {
    val tokens = LocalVanTokens.current
    var statement by remember { mutableStateOf("") }
    var predicate by remember { mutableStateOf("") }
    var value by remember { mutableStateOf("") }
    var structured by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Remember something") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space3)) {
                Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    RememberModeChip(label = "Say it", selected = !structured, onClick = { structured = false })
                    RememberModeChip(label = "Structured", selected = structured, onClick = { structured = true })
                }
                if (!structured) {
                    OutlinedTextField(
                        value = statement,
                        onValueChange = { statement = it },
                        label = { Text("e.g. my coffee order is a flat white", style = tokens.type.label) },
                        modifier = Modifier.fillMaxWidth().semantics { contentDescription = "What should VAN remember" },
                    )
                } else {
                    OutlinedTextField(
                        value = predicate,
                        onValueChange = { predicate = it },
                        label = { Text("Field, e.g. coffee_order", style = tokens.type.label) },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    OutlinedTextField(
                        value = value,
                        onValueChange = { value = it },
                        label = { Text("Value, e.g. flat white", style = tokens.type.label) },
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        },
        confirmButton = {
            Button(
                enabled = if (!structured) statement.isNotBlank() else predicate.isNotBlank() && value.isNotBlank(),
                onClick = {
                    if (!structured) onSubmitStatement(statement.trim()) else onSubmitStructured(predicate.trim(), value.trim())
                },
            ) { Text("Remember") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun CorrectDialog(fact: MemoryFact, onDismiss: () -> Unit, onSubmit: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    var value by remember { mutableStateOf(fact.value) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Correct \"${fact.predicate.replace('_', ' ')}\"") },
        text = {
            OutlinedTextField(
                value = value,
                onValueChange = { value = it },
                label = { Text("New value", style = tokens.type.label) },
                modifier = Modifier.fillMaxWidth(),
            )
        },
        confirmButton = {
            Button(enabled = value.isNotBlank() && value != fact.value, onClick = { onSubmit(value.trim()) }) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun RememberModeChip(label: String, selected: Boolean, onClick: () -> Unit) {
    VanPressable(onClick = onClick, contentDescription = "$label${if (selected) ", selected" else ""}") {
        StatusChip(label = label, role = if (selected) StatusSemantics.ROLE_ENGAGED else StatusSemantics.ROLE_DISABLED, filled = selected)
    }
}

/** Presentation-only relative time, kept out of the pure `MemoryReadModel`. */
private object RelativeTime {
    private const val DAY_MS = 24 * 60 * 60 * 1000L

    fun describe(atMs: Long, nowMs: Long): String {
        if (atMs <= 0L) return "unknown time"
        val diff = (nowMs - atMs).coerceAtLeast(0L)
        val days = diff / DAY_MS
        return when {
            days <= 0L -> "today"
            days == 1L -> "yesterday"
            days < 30L -> "$days days ago"
            else -> "${days / 30L} months ago"
        }
    }

    fun describeValidity(validUntilMs: Long?, nowMs: Long): String {
        validUntilMs ?: return "No expiry"
        val diff = validUntilMs - nowMs
        return if (diff <= 0L) "Expired" else "Expires in ${(diff / DAY_MS).coerceAtLeast(1L)} days"
    }
}
