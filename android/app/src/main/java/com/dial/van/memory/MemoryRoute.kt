package com.dial.van.memory

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
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
import com.dial.van.command.nav.VanRoute
import com.dial.van.command.owner.ownerTime
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
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import org.json.JSONObject

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

private enum class MemoryDialog { NONE, REMEMBER, CORRECT, FORGET, HISTORY }

@Composable
fun MemoryRoute(app: VanApplication, onBack: () -> Unit, onOpenRoute: (String) -> Unit = {}) {
    val tokens = LocalVanTokens.current
    val scope = rememberCoroutineScope()
    var data by remember { mutableStateOf<MemoryData?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var notice by remember { mutableStateOf<String?>(null) }
    var conflictsError by remember { mutableStateOf<String?>(null) }
    var mutating by remember { mutableStateOf(false) }
    var mutationError by remember { mutableStateOf<String?>(null) }
    var privacyOpen by remember { mutableStateOf(false) }
    var lastRead by remember { mutableStateOf(0L) }
    var dialog by remember { mutableStateOf(MemoryDialog.NONE) }
    var actingOn by remember { mutableStateOf<MemoryFact?>(null) }

    fun load() {
        scope.launch {
            loading = true
            try {
                val facts = MemoryReadModel.parseExportFacts(app.gatewayClient.contextExport())
                data = MemoryData(facts, data?.conflicts.orEmpty())
                lastRead = System.currentTimeMillis()
                error = null
                mutationError = null
                try {
                    data = MemoryData(facts, MemoryReadModel.parseConflicts(app.gatewayClient.contextConflicts()))
                    conflictsError = null
                } catch (cancel: CancellationException) { throw cancel }
                catch (failure: Exception) { conflictsError = "VAN could not refresh conflicts. Last known conflicts are retained. ${failure.message.orEmpty()}" }
            } catch (cancel: CancellationException) { throw cancel }
            catch (failure: Exception) { error = failure.message ?: "VAN could not open its own memory." }
            finally { loading = false }
        }
    }
    LaunchedEffect(Unit) { load() }
    LaunchedEffect(Unit) {
        while (true) { delay(15_000L); if ((error != null || conflictsError != null) && !loading && !mutating) load() }
    }
    fun mutate(success: String, action: suspend () -> JSONObject) {
        if (mutating || loading || error != null || mutationError != null) return
        mutating = true
        mutationError = null
        scope.launch {
            try {
                action()
                notice = success
                dialog = MemoryDialog.NONE
                load()
            } catch (cancel: CancellationException) { throw cancel }
            catch (failure: Exception) { mutationError = "VAN could not confirm this change. Your draft is kept. Refresh memory before trying again. ${failure.message.orEmpty()}" }
            finally { mutating = false }
        }
    }

    val state: ScreenState<MemoryData> = ScreenStateMerge.merge(
        content = data,
        loading = loading,
        errorMessage = error,
        emptySentence = "VAN does not hold anything about you yet.",
        emptyAction = ScreenAction("Remember something"),
    )

    Column(modifier = Modifier.fillMaxSize()) {
        LazyRow(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2), contentPadding = PaddingValues(horizontal = tokens.space.pageGutter)) {
            item { OutlinedButton(onClick = { onOpenRoute(VanRoute.UNDERSTANDING) }) { Text("Understanding") } }
            item { OutlinedButton(onClick = { onOpenRoute(VanRoute.ADAPTATIONS) }) { Text("Adaptations") } }
            item { OutlinedButton(onClick = { onOpenRoute(VanRoute.GOALS) }) { Text("Goals & evidence") } }
            item { OutlinedButton(onClick = { privacyOpen = true }) { Text("Memory privacy") } }
        }
        Box(modifier = Modifier.weight(1f)) {
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
            item { Text("Last read ${ownerTime(lastRead)}", style = tokens.type.label, color = tokens.color.textTertiary); OutlinedButton(enabled = !loading && !mutating, onClick = ::load) { Text("Refresh memory") } }
            mutationError?.let { item { Text(it, style = tokens.type.body, color = tokens.color.textSecondary) } }

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
                        onHistory = { actingOn = fact; dialog = MemoryDialog.HISTORY },
                    )
                }
            }

            item { SectionHeader("Decisions you made") }
            if (decisions.isEmpty()) {
                item { Text("No decisions recorded yet — say \"record decision: …\" and VAN will keep it.", style = tokens.type.body, color = tokens.color.textSecondary) }
            }
            items(decisions, key = { "decision:" + it.factId }) { fact ->
                FactRow(fact = fact, now = now, onCorrect = { actingOn = fact; dialog = MemoryDialog.CORRECT }, onForget = { actingOn = fact; dialog = MemoryDialog.FORGET }, onHistory = { actingOn = fact; dialog = MemoryDialog.HISTORY })
            }

            item { SectionHeader("Preferences") }
            if (preferences.isEmpty()) {
                item { Text("VAN has not learned any preferences yet.", style = tokens.type.body, color = tokens.color.textSecondary) }
            }
            items(preferences, key = { "pref:" + it.factId }) { fact ->
                FactRow(fact = fact, now = now, onCorrect = { actingOn = fact; dialog = MemoryDialog.CORRECT }, onForget = { actingOn = fact; dialog = MemoryDialog.FORGET }, onHistory = { actingOn = fact; dialog = MemoryDialog.HISTORY })
            }

            item { SectionHeader("Things I'm unsure about", detail = if (uncertainty.isEmpty) "Nothing right now" else null) }
            conflictsError?.let { item { Text(it, style = tokens.type.body, color = tokens.color.textSecondary) } }
            if (uncertainty.isEmpty && conflictsError == null) {
                item { Text("No contradictions and nothing about to lapse.", style = tokens.type.body, color = tokens.color.textSecondary) }
            }
            items(uncertainty.conflicts, key = { "conflict:" + it.subject + it.predicate + it.scope }) { conflict ->
                ConflictCard(
                    conflict = conflict,
                    enabled = !mutating && !loading && mutationError == null && conflictsError == null,
                    onResolve = { side ->
                        mutate("Your correction was recorded for this conflict.") { app.gatewayClient.stateOwnerFact(conflict.subject, conflict.predicate, side.value, conflict.scope).also { check(it.optString("value") == side.value) { "The fact receipt did not match your correction." } } }
                    },
                )
            }
            items(uncertainty.staleOrExpiring, key = { "stale:" + it.factId }) { fact ->
                FactRow(fact = fact, now = now, onCorrect = { actingOn = fact; dialog = MemoryDialog.CORRECT }, onForget = { actingOn = fact; dialog = MemoryDialog.FORGET }, onHistory = { actingOn = fact; dialog = MemoryDialog.HISTORY }, showFreshness = true)
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

        }
    }
    if (dialog == MemoryDialog.REMEMBER) {
        RememberDialog(
            working = mutating,
            errorMessage = mutationError,
            onRetry = ::load,
            onDismiss = { if (!mutating) dialog = MemoryDialog.NONE },
            onSubmitStatement = { statement ->
                dialog = MemoryDialog.NONE
                app.commandController.submitText("remember that $statement", VanCommandSource.CHAT)
                notice = "Request sent. Follow its outcome in Work."
                onOpenRoute(VanRoute.WORK)
            },
            onSubmitStructured = { predicate, value ->
                mutate("Owner-stated fact recorded.") { app.gatewayClient.stateOwnerFact("OWNER", predicate, value, "global").also { check(it.optString("value") == value) { "The fact receipt did not match." } } }
            },
        )
    }

    if (dialog == MemoryDialog.CORRECT) {
        actingOn?.let { fact ->
            CorrectDialog(
                fact = fact,
                working = mutating,
                errorMessage = mutationError,
                onRetry = ::load,
                onDismiss = { if (!mutating) dialog = MemoryDialog.NONE },
                onSubmit = { newValue ->
                    mutate("Correction recorded.") { app.gatewayClient.stateOwnerFact(fact.subject, fact.predicate, newValue, fact.scope).also { check(it.optString("value") == newValue) { "The fact receipt did not match." } } }
                },
            )
        }
    }

    if (dialog == MemoryDialog.FORGET) {
        actingOn?.let { fact ->
            AlertDialog(
                onDismissRequest = { if (!mutating) dialog = MemoryDialog.NONE },
                title = { Text("Withdraw this fact?") },
                text = { Column { Text("VAN will stop treating \"${fact.predicate.replace('_', ' ')}\" as \"${fact.value}\". This does not undo anything already done with it."); mutationError?.let { Text(it); OutlinedButton(onClick = ::load, enabled = !loading) { Text("Refresh memory") } } } },
                confirmButton = {
                    Button(
                        enabled = !mutating && !loading && mutationError == null,
                        onClick = {
                            mutate("Fact withdrawn. Its history remains available.") { app.gatewayClient.forgetOwnerFact(fact.subject, fact.predicate, fact.scope).also { check(it.has("ended")) { "No withdrawal receipt was returned." } } }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = LocalVanTokens.current.color.forStatusRole(StatusSemantics.ROLE_CRITICAL)),
                    ) { Text("Withdraw fact") }
                },
                dismissButton = { TextButton(enabled = !mutating, onClick = { dialog = MemoryDialog.NONE }) { Text("Cancel") } },
            )
        }
    }
    if (dialog == MemoryDialog.HISTORY) actingOn?.let { FactHistoryDialog(app, it, onDismiss = { dialog = MemoryDialog.NONE }) }
    if (privacyOpen) MemoryPrivacyDialog(app, onDismiss = { privacyOpen = false }, onRequestErasure = { store ->
        val command = if (store == null) "forget all owner-derived memory" else "forget owner-derived memory store $store"
        app.commandController.submitText(command, VanCommandSource.CHAT)
        privacyOpen = false
        onOpenRoute(VanRoute.WORK)
    }, onRequestRecordErasure = { command ->
        app.commandController.submitText(command, VanCommandSource.QUICK_ACTION, actionClass = "A4")
        privacyOpen = false
        onOpenRoute(VanRoute.WORK)
    })
}

@Composable
private fun FactRow(
    fact: MemoryFact,
    now: Long,
    onCorrect: () -> Unit,
    onForget: () -> Unit,
    onHistory: () -> Unit,
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
                TextButton(onClick = onForget) { Text("Withdraw", style = tokens.type.label) }
                TextButton(onClick = onHistory) { Text("History", style = tokens.type.label) }
            }
            Text("${fact.subject} · ${fact.scope}\nSource: ${fact.sourceRef.ifBlank { "Not recorded" }}\nTrust: ${fact.sourceTrust} · observed ${ownerTime(fact.observedAtMs)}", style = tokens.type.label, color = tokens.color.textTertiary)
        }
    }
}

@Composable
private fun ConflictCard(conflict: MemoryConflict, enabled: Boolean, onResolve: (MemoryConflictSide) -> Unit) {
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
                        Text("${side.sourceTrust} · ${ownerTime(side.observedAtMs)}\n${side.sourceRef.ifBlank { "Source not recorded" }}", style = tokens.type.label, color = tokens.color.textTertiary)
                    }
                    OutlinedButton(enabled = enabled, onClick = { onResolve(side) }) { Text("Use this", style = tokens.type.label) }
                }
            }
        }
    }
}

@Composable
private fun RememberDialog(
    working: Boolean,
    errorMessage: String?,
    onRetry: () -> Unit,
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
                errorMessage?.let { Text(it); OutlinedButton(onClick = onRetry, enabled = !working) { Text("Refresh memory") } }
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
                enabled = !working && errorMessage == null && (if (!structured) statement.isNotBlank() else predicate.isNotBlank() && value.isNotBlank()),
                onClick = {
                    if (!structured) onSubmitStatement(statement.trim()) else onSubmitStructured(predicate.trim(), value.trim())
                },
            ) { Text("Remember") }
        },
        dismissButton = { TextButton(enabled = !working, onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun CorrectDialog(fact: MemoryFact, working: Boolean, errorMessage: String?, onRetry: () -> Unit, onDismiss: () -> Unit, onSubmit: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    var value by remember { mutableStateOf(fact.value) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Correct \"${fact.predicate.replace('_', ' ')}\"") },
        text = {
            Column {
            errorMessage?.let { Text(it); OutlinedButton(onClick = onRetry, enabled = !working) { Text("Refresh memory") } }
            OutlinedTextField(
                value = value,
                enabled = !working,
                onValueChange = { value = it },
                label = { Text("New value", style = tokens.type.label) },
                modifier = Modifier.fillMaxWidth(),
            )
            }
        },
        confirmButton = {
            Button(enabled = !working && errorMessage == null && value.isNotBlank() && value != fact.value, onClick = { onSubmit(value.trim()) }) { Text(if (working) "Saving…" else "Save") }
        },
        dismissButton = { TextButton(enabled = !working, onClick = onDismiss) { Text("Cancel") } },
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
