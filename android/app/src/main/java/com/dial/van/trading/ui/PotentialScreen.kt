package com.dial.van.trading.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import com.dial.van.design.components.EvidenceRow
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.trading.ConfidenceBand
import com.dial.van.trading.Loaded
import com.dial.van.trading.PotentialCandidate
import com.dial.van.trading.PotentialReadModel
import com.dial.van.trading.TradingFormat
import com.dial.van.trading.TradingRepository

/**
 * DNA §4 Trading destination 4, "Potential trades": candidate cards with thesis-shaped
 * evidence, confidence, invalidation and the risk this candidate would require.
 *
 * @DataSource("GET /v1/trading/potential")
 */
@Composable
fun PotentialScreen(repo: TradingRepository, nav: TradingNav) {
    val tokens = LocalVanTokens.current
    var tick by remember { mutableIntStateOf(0) }
    var potential: Loaded<PotentialReadModel> by remember { mutableStateOf(Loaded.Loading) }
    LaunchedEffect(tick) { potential = repo.potentialTrades() }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = tokens.space.pageGutter, vertical = tokens.space.space3),
        verticalArrangement = Arrangement.spacedBy(tokens.space.space3),
    ) {
        item {
            SectionHeader(
                title = "Potential trades",
                detail = (potential as? Loaded.Ready)?.value?.let { "${it.count} candidate(s)" },
                trailing = { TradingRefreshAction { tick += 1 } },
            )
        }
        val loaded = potential
        when (loaded) {
            Loaded.Loading -> item { Text("Reading the ledger…", style = tokens.type.body, color = tokens.color.textSecondary) }
            is Loaded.Unavailable -> item {
                Text(TradingFormat.unavailableState(loaded.reason), style = tokens.type.body, color = tokens.color.forStatusRole(StatusSemantics.ROLE_EVENT_RISK))
            }
            is Loaded.Ready -> {
                if (loaded.value.trades.isEmpty()) {
                    item { Text("No setups are waiting.", style = tokens.type.body, color = tokens.color.textSecondary) }
                } else {
                    items(loaded.value.trades, key = { "${it.symbol}:${it.assessedMs}" }) { candidate -> PotentialCard(candidate) }
                }
            }
        }
        item {
            TradingDisclosure(
                "Candidate pool from the VATI ledger. Confidence is an uncalibrated display " +
                    "signal, never a permission. Nothing here can place, size or reserve a trade.",
            )
        }
    }
}

@Composable
private fun PotentialCard(candidate: PotentialCandidate) {
    val tokens = LocalVanTokens.current
    val bandRole = when (candidate.confidence.band) {
        ConfidenceBand.HIGH -> StatusSemantics.ROLE_FAVOURABLE
        ConfidenceBand.MEDIUM -> StatusSemantics.ROLE_MONITOR
        ConfidenceBand.LOW -> StatusSemantics.ROLE_EVENT_RISK
        else -> StatusSemantics.ROLE_DISABLED
    }
    VanPanel {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                Text("${candidate.symbol} ${candidate.direction.orEmpty()}", style = tokens.type.headline, color = tokens.color.textPrimary, modifier = Modifier.weight(1f))
                StatusChip(label = "${candidate.confidence.percentLabel} ${candidate.confidence.band.label}", role = bandRole)
            }
            candidate.label?.let { Text(it, style = tokens.type.body, color = tokens.color.textSecondary) }
            if (candidate.reasons.isNotEmpty()) {
                Text(candidate.reasons.joinToString(" · "), style = tokens.type.label, color = tokens.color.textTertiary)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space4)) {
                LabeledLine("Entry", candidate.entry?.let { TradingFormat.price(it, TradingFormat.digitsFor(candidate.symbol)) } ?: "—")
                LabeledLine("Stop", candidate.stop?.let { TradingFormat.price(it, TradingFormat.digitsFor(candidate.symbol)) } ?: "—")
                candidate.costMultiple?.let { LabeledLine("Edge", "${TradingFormat.lots(it)}× cost") }
            }
            val invalidation = candidate.invalidation
            if (invalidation != null) {
                LabeledLine(
                    "Invalidates if",
                    listOfNotNull(
                        invalidation.stop?.let { "price crosses ${TradingFormat.price(it, TradingFormat.digitsFor(candidate.symbol))}" },
                        invalidation.expiresMs?.let { "by ${TradingFormat.dateShort(it)} ${TradingFormat.timeHm(it)}" },
                    ).joinToString(", ").ifBlank { "—" },
                    role = StatusSemantics.ROLE_CRITICAL,
                )
            }
            val requirement = candidate.riskRequirement
            if (requirement != null) {
                LabeledLine(
                    "Risk requirement",
                    requirement.capsuleRiskCeiling?.let { TradingFormat.percent(it * 100) } ?: "—",
                )
            }
            if (candidate.linkedEvents.isNotEmpty()) {
                Text("Linked events", style = tokens.type.label, color = tokens.color.textTertiary)
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                    candidate.linkedEvents.forEach { event ->
                        EvidenceRow(
                            source = event.concern ?: event.headlineId ?: "event",
                            trustTier = "materiality ${event.materiality?.let { TradingFormat.percent(it * 100, decimals = 0) } ?: "?"}",
                            trustRole = if ((event.materiality ?: 0.0) >= 0.75) StatusSemantics.ROLE_CRITICAL else StatusSemantics.ROLE_EVENT_RISK,
                            timeLabel = event.atMs?.let { TradingFormat.timeHm(it) } ?: "—",
                        )
                    }
                }
            }
            if (candidate.evidenceRefs.isNotEmpty()) {
                Text("${candidate.evidenceRefs.size} evidence reference(s)", style = tokens.type.label, color = tokens.color.textTertiary)
            }
        }
    }
}

@Composable
private fun LabeledLine(caption: String, value: String, role: String? = null) {
    val tokens = LocalVanTokens.current
    Column {
        Text(caption, style = tokens.type.label, color = tokens.color.textTertiary)
        Text(value, style = tokens.type.data, color = role?.let { tokens.color.forStatusRole(it) } ?: tokens.color.textPrimary)
    }
}
