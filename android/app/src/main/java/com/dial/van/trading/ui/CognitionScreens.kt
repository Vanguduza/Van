package com.dial.van.trading.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.MetricTile
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.trading.CognitionSnapshot
import com.dial.van.trading.Loaded
import com.dial.van.trading.TradingFormat
import com.dial.van.trading.TradingRepository

/**
 * Rev 5.1 owner cognition surface (TRD-REV51-130), migrated onto the design system. A
 * dedicated page, not another vertically-stacked dashboard module: it renders the gateway's
 * ledger projection and has no mutation controls. Reachable from Overview's "Cognition &
 * research →" link — not one of DNA §4's seven named Trading destinations, kept because it is
 * real functionality this worker migrates rather than discards.
 *
 * @DataSource("GET /v1/trading/cognition")
 */
@Composable
fun CognitionScreen(repo: TradingRepository) {
    val tokens = LocalVanTokens.current
    var tick by remember { mutableIntStateOf(0) }
    var selected by remember { mutableStateOf("OVERVIEW") }
    var snapshot: Loaded<CognitionSnapshot> by remember { mutableStateOf(Loaded.Loading) }

    LaunchedEffect(tick) {
        snapshot = Loaded.Loading
        snapshot = repo.cognition()
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = tokens.space.pageGutter, vertical = tokens.space.space3),
        verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
    ) {
        item {
            SectionHeader(
                title = "Trading Cognition",
                detail = "Fable-led shadow cognition, research and evolution evidence. No control on this page can place or resize a trade.",
                trailing = { TradingRefreshAction { tick += 1 } },
            )
        }
        item { TradingTabs(listOf("OVERVIEW", "MODELS", "RESEARCH", "EVOLUTION"), selected) { selected = it } }

        val loaded = snapshot
        when (loaded) {
            Loaded.Loading -> item { Text("Reading the ledger…", style = tokens.type.body, color = tokens.color.textSecondary) }
            is Loaded.Unavailable -> item {
                Text(TradingFormat.unavailableState(loaded.reason), style = tokens.type.body, color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK))
            }
            is Loaded.Ready -> {
                item { AuthorityHeader(loaded.value) }
                when (selected) {
                    "MODELS" -> item { ModelsPanel(loaded.value) }
                    "RESEARCH" -> item { ResearchPanel(loaded.value) }
                    "EVOLUTION" -> item { EvolutionPanel(loaded.value) }
                    else -> item { CognitionOverview(loaded.value) }
                }
            }
        }
    }
}

@Composable
private fun AuthorityHeader(model: CognitionSnapshot) {
    val tokens = LocalVanTokens.current
    VanPanel(dense = true) {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                StatusChip(label = model.cognitionMode, role = StatusSemantics.ROLE_MONITOR)
                StatusChip(label = "LIVE ADVISORY ${model.liveAdvisory}", role = StatusSemantics.ROLE_EVENT_RISK)
                StatusChip(label = "LIVE ${model.liveStatus}", role = StatusSemantics.ROLE_DISABLED)
            }
            Text(
                if (model.ledgerAvailable) "Ledger evidence connected" else "Trading cognition ledger unavailable",
                style = tokens.type.body,
                color = if (model.ledgerAvailable) tokens.color.textSecondary else tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK),
            )
        }
    }
}

@Composable
private fun CognitionOverview(model: CognitionSnapshot) {
    val tokens = LocalVanTokens.current
    VanPanel {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Text("Evidence summary", style = tokens.type.headline, color = tokens.color.textPrimary)
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                MetricTile("Assessments", (model.summary["assessments"] ?: 0).toString(), Modifier.weight(1f))
                MetricTile("Shadow decisions", (model.summary["shadow_decisions"] ?: 0).toString(), Modifier.weight(1f))
                MetricTile("Handoffs", (model.summary["handoffs"] ?: 0).toString(), Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                MetricTile("Research missions", (model.summary["research_missions"] ?: 0).toString(), Modifier.weight(1f))
                MetricTile("Proposals", (model.summary["improvement_proposals"] ?: 0).toString(), Modifier.weight(1f))
                MetricTile("Admissions", (model.summary["proposal_admissions"] ?: 0).toString(), Modifier.weight(1f))
            }
            Text(
                if (model.expansionModes.isEmpty()) "Expansion: no evidence yet"
                else "Expansion evidence: " + model.expansionModes.entries.joinToString { it.key + "=" + it.value },
                style = tokens.type.body, color = tokens.color.textSecondary,
            )
            if (model.rejectionCategories.isNotEmpty()) {
                Text(
                    "Rejection categories: " + model.rejectionCategories.entries.sortedByDescending { it.value }.take(4).joinToString { it.key + " " + it.value },
                    style = tokens.type.label, color = tokens.color.textTertiary,
                )
            }
        }
    }
}

@Composable
private fun ModelsPanel(model: CognitionSnapshot) {
    val tokens = LocalVanTokens.current
    VanPanel {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Text("Model hierarchy & measured contribution", style = tokens.type.headline, color = tokens.color.textPrimary)
            model.models.forEachIndexed { index, row ->
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        Text("${index + 1}. ${row.modelId}", style = tokens.type.body, color = tokens.color.textPrimary, modifier = Modifier.weight(1f))
                        StatusChip(
                            label = when (row.qualified) { true -> "MEASURED"; false -> "NOT QUALIFIED"; null -> "NO PERFORMANCE" },
                            role = if (row.qualified == true) StatusSemantics.ROLE_FAVOURABLE else StatusSemantics.ROLE_DISABLED,
                        )
                    }
                    val confidence = row.confidence?.let { String.format(java.util.Locale.ROOT, "%.2f", it) } ?: "—"
                    Text("${row.assessments} assessment(s) · latest ${row.verdict ?: "—"} · confidence $confidence", style = tokens.type.label, color = tokens.color.textTertiary)
                }
            }
        }
    }
}

@Composable
private fun ResearchPanel(model: CognitionSnapshot) {
    val tokens = LocalVanTokens.current
    VanPanel {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Text("Research missions", style = tokens.type.headline, color = tokens.color.textPrimary)
            if (model.missions.isEmpty()) {
                Text("No research missions in the ledger yet.", style = tokens.type.body, color = tokens.color.textSecondary)
            } else {
                model.missions.forEach { mission ->
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            Text(mission.missionId, style = tokens.type.label, color = tokens.color.accentCyan, modifier = Modifier.weight(1f))
                            StatusChip(label = mission.state, role = if (mission.state == "COMPLETE") StatusSemantics.ROLE_FAVOURABLE else StatusSemantics.ROLE_EVENT_RISK)
                        }
                        Text(mission.hypothesis.ifBlank { "No hypothesis text" }, style = tokens.type.body, color = tokens.color.textPrimary)
                    }
                }
            }
        }
    }
}

@Composable
private fun EvolutionPanel(model: CognitionSnapshot) {
    val tokens = LocalVanTokens.current
    VanPanel {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Text("Evolution proposals", style = tokens.type.headline, color = tokens.color.textPrimary)
            if (model.proposals.isEmpty()) {
                Text("No improvement proposals have been admitted into the evolution ledger.", style = tokens.type.body, color = tokens.color.textSecondary)
            } else {
                model.proposals.forEach { proposal ->
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            Text(proposal.title, style = tokens.type.body, color = tokens.color.textPrimary, modifier = Modifier.weight(1f))
                            if (proposal.liveAffecting) StatusChip(label = "LIVE-AFFECTING", role = StatusSemantics.ROLE_EVENT_RISK)
                        }
                        Text(proposal.proposalId, style = tokens.type.label, color = tokens.color.textTertiary)
                        Text("Admission: ${proposal.admission ?: "NOT EVALUATED"}", style = tokens.type.label, color = tokens.color.textSecondary)
                    }
                }
            }
            TradingDisclosure(
                "A proposal, model qualification or research result never grants trading authority. " +
                    "Live-affecting changes still require engineering gates and owner authority.",
            )
        }
    }
}
