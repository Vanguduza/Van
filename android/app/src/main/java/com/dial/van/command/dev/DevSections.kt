package com.dial.van.command.dev

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import com.dial.van.VanApplication
import com.dial.van.command.nav.VanRoute
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.design.components.VanScreen
import com.dial.van.dialdev.DevInfrastructure
import com.dial.van.dialdev.DevProject
import com.dial.van.dialdev.DialDevFabricParse
import com.dial.van.dialdev.DialDevHealth
import com.dial.van.dialdev.DialDevLadder
import com.dial.van.dialdev.DialDevParse
import com.dial.van.dialdev.DialDevRoles

/**
 * VAN-DEV-010 (Android) — Connected's "DIAL development fabric" section (VAN-DEVCC-R1 §6.11).
 *
 * @DataSource("GET /v1/dial-dev/infrastructure") — per capability its ladder state
 *   (INSTALLED → AUTHENTICATED → LIVE_QUALIFIED → ORCHESTRATED → INTEGRATED), version/pin and
 *   last probe; Orca version, drift, daemon scope and bind; each manager slot's qualification;
 *   the Oracle gate's state and failed checks; Hermes/SPMRF/OpenViking/VEKL/ARTEMIS health.
 *
 * A section of the existing Connected destination, rendered through its own `VanScreen` so it
 * shows all seven states independently of VAN's own connection health above it.
 */
@Composable
fun DevFabricSection(app: VanApplication) {
    val tokens = LocalVanTokens.current
    val infra = rememberDevProjection(
        app = app,
        key = "infrastructure",
        sections = setOf("infrastructure"),
        emptySentence = "DIAL reports no development fabric yet.",
        isEmpty = { i: DevInfrastructure -> i.capabilities.isEmpty() && i.oracleGate == null && i.health.isEmpty() },
        parse = { DialDevFabricParse.infrastructure(it.data) },
        fetch = { app.gatewayClient.dialDev.infrastructure() },
    )
    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
        SectionHeader("DIAL development fabric", detail = "What DIAL builds with, and how far each piece is qualified")
        VanScreen(state = infra.state, onRetry = infra.reload) { data ->
            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                VanPanel {
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                        Text("Oracle gate", style = tokens.type.headline, color = tokens.color.textPrimary)
                        StatusChip(label = DialDevRoles.chipLabel(data.oracleGate), role = DialDevRoles.roleOrDisabled(DialDevHealth.parse(data.oracleGate), DialDevRoles::health))
                        data.oracleFailedChecks.forEach { DevNote(it, warning = true) }
                    }
                }
                if (data.health.isNotEmpty()) {
                    LazyRow(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                        items(data.health, key = { it.subsystem }) { DevHealthChip(it) }
                    }
                }
                data.capabilities.forEach { capability ->
                    VanPanel(dense = true) {
                        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                            Text(capability.name, style = tokens.type.body, color = tokens.color.textPrimary)
                            StatusChip(
                                label = DialDevRoles.chipLabel(capability.ladder),
                                role = DialDevRoles.roleOrDisabled(DialDevLadder.parse(capability.ladder), DialDevRoles::ladder),
                            )
                            Text(
                                listOfNotNull(capability.version?.let { "v$it" }, capability.pin?.let { "pin $it" }, capability.lastProbe?.let { "probed $it" })
                                    .joinToString(" · ").ifBlank { "version, pin and probe not reported" },
                                style = tokens.type.label,
                                color = tokens.color.textTertiary,
                            )
                        }
                    }
                }
                DevFieldGroup(
                    "Orca",
                    listOf("Version" to data.orcaVersion, "Drift" to data.orcaDrift, "Daemon scope" to data.orcaDaemonScope, "Bind" to data.orcaBind),
                )
                VanPanel {
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                        Text("Manager chain", style = tokens.type.headline, color = tokens.color.textPrimary)
                        if (data.managerSlots.isEmpty()) DevNote("DIAL reported no manager slots.")
                        data.managerSlots.forEach { slot ->
                            Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                                Text(slot.title, style = tokens.type.body, color = tokens.color.textPrimary)
                                StatusChip(label = DialDevRoles.chipLabel(slot.state), role = DialDevRoles.forAnyState(slot.state))
                            }
                        }
                    }
                }
                DevRevisionFooter(infra.envelope)
            }
        }
    }
}

/**
 * The "Development" section of `projects/{projectId}` (VAN-DEVCC-R1 §2.1): whether this project
 * is an admitted DIAL project, its build-readiness and stage, and a way into its hub.
 *
 * @DataSource("GET /v1/dial-dev/projects") — admitted DIAL projects; this project's row, if any.
 */
@Composable
fun DevProjectSection(app: VanApplication, projectId: String, onOpenDevelopment: (String) -> Unit) {
    val tokens = LocalVanTokens.current
    val projects = rememberDevProjection(
        app = app,
        key = "projects",
        sections = setOf("projects"),
        emptySentence = "DIAL has no admitted development projects.",
        isEmpty = { list: List<DevProject> -> list.isEmpty() },
        parse = { DialDevParse.projects(it.data) },
        fetch = { app.gatewayClient.dialDev.projects() },
    )
    VanPanel {
        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
            Text("Development", style = tokens.type.headline, color = tokens.color.textPrimary)
            VanScreen(state = projects.state, onRetry = projects.reload) { list ->
                val mine = list.firstOrNull { it.projectId == projectId }
                Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                    if (mine == null) {
                        DevNote("This is not an admitted DIAL development project.")
                    } else {
                        StatusChip(
                            label = "FORENSIC BUILD ${DialDevRoles.chipLabel(mine.forensicBuildReady)}",
                            role = DialDevRoles.roleOrDisabled(DialDevHealth.parse(mine.forensicBuildReady), DialDevRoles::health),
                        )
                        DevField("Classification", mine.classification)
                        DevField("Current stage", mine.currentStage)
                        OutlinedButton(onClick = { onOpenDevelopment(VanRoute.devHomeRoute(projectId)) }) {
                            Text("Open development", style = tokens.type.label)
                        }
                    }
                }
            }
        }
    }
}
