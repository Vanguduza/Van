package com.dial.van.command.jev

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import com.dial.van.command.AdminCard
import com.dial.van.design.LocalVanTokens
import com.dial.van.visual.VanGlassStyle

/**
 * Browser & Automation's view of the one interaction router: which lanes are wired. It reads
 * the router's read-only lane status and never drives the browser.
 */
@Composable
internal fun JevBrowserLaneCard(lane: JevBrowserLane, glass: VanGlassStyle) {
    val tokens = LocalVanTokens.current
    fun wired(on: Boolean) = if (on) "wired" else "not wired"
    AdminCard(glass) {
        Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Text("Interaction lanes", style = tokens.type.title, color = tokens.color.textPrimary)
            Text(lane.summary, style = tokens.type.body, color = tokens.color.textSecondary)
            Text(
                "Deterministic ${wired(lane.deterministicExecutor)} • Stagehand ${wired(lane.stagehandFallback)} • verifier ${wired(lane.independentVerifier)}",
                style = tokens.type.label,
                color = tokens.color.accentCyan,
            )
        }
    }
}
