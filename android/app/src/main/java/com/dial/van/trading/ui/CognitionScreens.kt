package com.dial.van.trading.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.trading.CognitionSnapshot
import com.dial.van.trading.Loaded

/**
 * Rev 5.1 owner cognition surface (TRD-REV51-130).
 *
 * This is a dedicated page, not another vertically-stacked dashboard module. It renders
 * the gateway's ledger projection and has no mutation controls. Research/evolution state
 * is deliberately separate from strategy promotion: a proposal is evidence, not authority.
 */
@Composable
fun CognitionScreen(env: ScreenEnv, padding: PaddingValues) {
    var tick by remember { mutableIntStateOf(0) }
    var selected by remember { mutableStateOf("OVERVIEW") }
    var snapshot: Loaded<CognitionSnapshot> by remember { mutableStateOf(Loaded.Loading) }

    LaunchedEffect(tick) {
        snapshot = Loaded.Loading
        snapshot = env.repo.cognition()
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        contentPadding = PaddingValues(vertical = 10.dp),
    ) {
        item {
            Row {
                Column(modifier = Modifier.weight(1f)) {
                    Text("Trading Cognition", color = Color.White, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    Text(
                        "Fable-led shadow cognition, research and evolution evidence. No control on this page can place or resize a trade.",
                        color = TradingColors.muted,
                        fontSize = 10.sp,
                    )
                }
                Text(
                    "Refresh",
                    color = TradingColors.accent,
                    fontSize = 11.sp,
                    modifier = Modifier.clickable { tick += 1 }.padding(8.dp),
                )
            }
            TabRowChips(listOf("OVERVIEW", "MODELS", "RESEARCH", "EVOLUTION"), selected) {
                selected = it
            }
        }

        item {
            LoadedBox(snapshot, empty = "No cognition evidence has been recorded yet.") { model ->
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    AuthorityHeader(model)
                    when (selected) {
                        "MODELS" -> ModelsPanel(env, model)
                        "RESEARCH" -> ResearchPanel(env, model)
                        "EVOLUTION" -> EvolutionPanel(env, model)
                        else -> CognitionOverview(env, model)
                    }
                }
            }
        }
    }
}

@Composable
private fun AuthorityHeader(model: CognitionSnapshot) {
    Column(
        modifier = Modifier.fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(Color.White.copy(alpha = 0.05f))
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Chip(model.cognitionMode, 0xFF00E5FFL)
            Chip("LIVE ADVISORY " + model.liveAdvisory, 0xFFFFB300L)
            Chip("LIVE " + model.liveStatus, 0xFF78909CL)
        }
        Text(
            if (model.ledgerAvailable) "Ledger evidence connected" else "Trading cognition ledger unavailable",
            color = if (model.ledgerAvailable) TradingColors.text else TradingColors.warning,
            fontSize = 10.sp,
        )
    }
}

@Composable
private fun CognitionOverview(env: ScreenEnv, model: CognitionSnapshot) {
    SectionPanel(title = "Evidence summary", glass = env.glass) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MetricTile("Assessments", (model.summary["assessments"] ?: 0).toString(), Modifier.weight(1f))
            MetricTile("Shadow decisions", (model.summary["shadow_decisions"] ?: 0).toString(), Modifier.weight(1f))
            MetricTile("Handoffs", (model.summary["handoffs"] ?: 0).toString(), Modifier.weight(1f))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MetricTile("Research missions", (model.summary["research_missions"] ?: 0).toString(), Modifier.weight(1f))
            MetricTile("Proposals", (model.summary["improvement_proposals"] ?: 0).toString(), Modifier.weight(1f))
            MetricTile("Admissions", (model.summary["proposal_admissions"] ?: 0).toString(), Modifier.weight(1f))
        }
        Text(
            if (model.expansionModes.isEmpty()) "Expansion: no evidence yet"
            else "Expansion evidence: " + model.expansionModes.entries.joinToString { it.key + "=" + it.value },
            color = TradingColors.text,
            fontSize = 10.sp,
        )
        if (model.rejectionCategories.isNotEmpty()) {
            Text(
                "Rejection categories: " + model.rejectionCategories.entries
                    .sortedByDescending { it.value }.take(4)
                    .joinToString { it.key + " " + it.value },
                color = TradingColors.muted,
                fontSize = 10.sp,
            )
        }
    }
}

@Composable
private fun ModelsPanel(env: ScreenEnv, model: CognitionSnapshot) {
    SectionPanel(title = "Model hierarchy & measured contribution", glass = env.glass) {
        model.models.forEachIndexed { index, row ->
            Column(
                modifier = Modifier.fillMaxWidth()
                    .clip(RoundedCornerShape(10.dp))
                    .background(Color.White.copy(alpha = 0.035f))
                    .padding(10.dp),
            ) {
                Row {
                    Text(
                        (index + 1).toString() + ". " + row.modelId,
                        color = Color.White,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.weight(1f),
                    )
                    Chip(
                        when (row.qualified) {
                            true -> "MEASURED"
                            false -> "NOT QUALIFIED"
                            null -> "NO PERFORMANCE"
                        },
                        if (row.qualified == true) 0xFF69F0AEL else 0xFF78909CL,
                    )
                }
                val confidence = row.confidence?.let {
                    String.format(java.util.Locale.ROOT, "%.2f", it)
                } ?: "—"
                Text(
                    row.assessments.toString() + " assessment(s) · latest " +
                        (row.verdict ?: "—") + " · confidence " + confidence,
                    color = TradingColors.muted,
                    fontSize = 10.sp,
                )
            }
        }
    }
}

@Composable
private fun ResearchPanel(env: ScreenEnv, model: CognitionSnapshot) {
    SectionPanel(title = "Research missions", glass = env.glass) {
        if (model.missions.isEmpty()) {
            EmptyState("No research missions in the ledger yet.")
        } else {
            model.missions.forEach { mission ->
                Column(
                    modifier = Modifier.fillMaxWidth()
                        .clip(RoundedCornerShape(10.dp))
                        .background(Color.White.copy(alpha = 0.035f))
                        .padding(10.dp),
                ) {
                    Row {
                        Text(mission.missionId, color = TradingColors.accent, fontFamily = FontFamily.Monospace, fontSize = 10.sp, modifier = Modifier.weight(1f))
                        Chip(mission.state, if (mission.state == "COMPLETE") 0xFF69F0AEL else 0xFFFFB300L)
                    }
                    Text(mission.hypothesis.ifBlank { "No hypothesis text" }, color = TradingColors.text, fontSize = 11.sp)
                }
            }
        }
    }
}

@Composable
private fun EvolutionPanel(env: ScreenEnv, model: CognitionSnapshot) {
    SectionPanel(title = "Evolution proposals", glass = env.glass) {
        if (model.proposals.isEmpty()) {
            EmptyState("No improvement proposals have been admitted into the evolution ledger.")
        } else {
            model.proposals.forEach { proposal ->
                Column(
                    modifier = Modifier.fillMaxWidth()
                        .clip(RoundedCornerShape(10.dp))
                        .background(Color.White.copy(alpha = 0.035f))
                        .padding(10.dp),
                ) {
                    Row {
                        Text(proposal.title, color = Color.White, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                        if (proposal.liveAffecting) Chip("LIVE-AFFECTING", 0xFFFFB300L)
                    }
                    Text(proposal.proposalId, color = TradingColors.muted, fontFamily = FontFamily.Monospace, fontSize = 9.sp)
                    Text(
                        "Admission: " + (proposal.admission ?: "NOT EVALUATED"),
                        color = TradingColors.text,
                        fontSize = 10.sp,
                    )
                }
            }
        }
        Text(
            "A proposal, model qualification or research result never grants trading authority. Live-affecting changes still require engineering gates and owner authority.",
            color = TradingColors.muted,
            fontSize = 9.sp,
        )
    }
}
