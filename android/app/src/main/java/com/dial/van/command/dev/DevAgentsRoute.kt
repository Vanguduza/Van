package com.dial.van.command.dev

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.dial.van.VanApplication
import com.dial.van.command.nav.VanRoute
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.StatusSemantics
import com.dial.van.design.components.FindingCard
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.design.components.VanPressable
import com.dial.van.design.components.VanScreen
import com.dial.van.dialdev.DevAgents
import com.dial.van.dialdev.DialDevFabricParse
import com.dial.van.dialdev.DialDevFormat

/**
 * `work/dev/agents` — Active Agents (VAN-DEVCC-R1 §6.5, VAN-DEV-007): "everyone knows what
 * everyone is doing".
 *
 * @DataSource("GET /v1/dial-dev/agents") — the ActiveWorkGraph slice: actor, harness, model,
 *   host, objective, intent, owned paths, heartbeat, next action, blockers, overlap warnings.
 *
 * Overlap warnings are DIAL's when it sends them; otherwise they are derived from the declared
 * intents on screen and labelled as derived. Either way they are information — the lease system
 * is what prevents overlap, not this list.
 */
@Composable
fun DevAgentsRoute(app: VanApplication, nav: DevNavigator) {
    val tokens = LocalVanTokens.current
    val agents = rememberDevProjection(
        app = app,
        key = "agents",
        sections = setOf("agents"),
        emptySentence = "No DIAL agents are active right now.",
        isEmpty = { a: DevAgents -> a.agents.isEmpty() },
        parse = { DialDevFabricParse.agents(it.data, it.observedAt) },
        fetch = { app.gatewayClient.dialDev.agents() },
    )
    VanScreen(state = agents.state, onRetry = agents.reload) { data ->
        DevPage {
            item { SectionHeader("Active agents", detail = "${data.agents.size} active") }
            data.overlaps.forEachIndexed { index, overlap ->
                item(key = "overlap:$index") {
                    FindingCard(
                        title = "Intents approach each other: ${overlap.actors.joinToString(" and ")}",
                        severityRole = StatusSemantics.ROLE_EVENT_RISK,
                        detail = overlap.paths.joinToString(", ") +
                            if (overlap.derived) " — derived from declared intents; leases prevent real overlap." else " — reported by DIAL.",
                    )
                }
            }
            data.agents.forEach { agent ->
                item(key = agent.actorId) {
                    val open = agent.taskId?.let { id -> { nav.open(VanRoute.devTaskRoute(id)) } }
                    VanPressable(
                        onClick = { open?.invoke() },
                        enabled = open != null,
                        modifier = Modifier.fillMaxWidth(),
                        contentDescription = "${agent.actorId}. ${agent.objective ?: "Objective not reported"}.",
                    ) {
                        VanPanel {
                            Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                                Text(agent.actorId, style = tokens.type.headline, color = tokens.color.textPrimary)
                                StatusChip(
                                    label = listOfNotNull(agent.harness, agent.model).joinToString("/").ifBlank { "harness not reported" },
                                    role = StatusSemantics.ROLE_ENGAGED,
                                )
                                DevField("Objective", agent.objective)
                                DevField("Intent · paths", agent.intentPaths.joinToString(", ").ifBlank { null })
                                DevField("Intent · commands", agent.intentCommands.joinToString(", ").ifBlank { null })
                                DevField("Intent · tests", agent.intentTests.joinToString(", ").ifBlank { null })
                                DevField("Owned paths", agent.ownedPaths.joinToString(", ").ifBlank { null })
                                DevField("Next action", agent.nextAction)
                                DevField("Host", agent.host)
                                DevField("Heartbeat", agent.heartbeatAgeMs?.let { "${DialDevFormat.age(it)} ago" })
                                agent.blockers.forEach { DevNote(it, warning = true) }
                            }
                        }
                    }
                }
            }
            item { DevRevisionFooter(agents.envelope) }
        }
    }
}
