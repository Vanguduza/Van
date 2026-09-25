package com.dial.van.command.dev

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import com.dial.van.VanApplication
import com.dial.van.command.nav.VanRoute
import com.dial.van.design.LocalVanTokens
import com.dial.van.design.components.EvidenceRow
import com.dial.van.design.components.FindingCard
import com.dial.van.design.components.SectionHeader
import com.dial.van.design.components.StatusChip
import com.dial.van.design.components.VanPanel
import com.dial.van.design.components.VanPressable
import com.dial.van.design.components.VanScreen
import com.dial.van.dialdev.DevCiRun
import com.dial.van.dialdev.DevFinding
import com.dial.van.dialdev.DevLabelled
import com.dial.van.dialdev.DevReview
import com.dial.van.dialdev.DialDevAdmission
import com.dial.van.dialdev.DialDevFabricParse
import com.dial.van.dialdev.DialDevFormat
import com.dial.van.dialdev.DialDevResult
import com.dial.van.dialdev.DialDevRoles
import com.dial.van.dialdev.DialDevSeverity
import com.dial.van.gateway.VanGatewayClient.HubSection

/**
 * `work/dev/reviews` (§6.7).
 *
 * @DataSource("GET /v1/dial-dev/reviews") — review jobs: checkpoint, author vs reviewer
 *   harness, blocking findings, claims verified/rejected, recommendation.
 *
 * The recommendation is labelled "does not advance the gate": a review recommends; only DIAL's
 * evidence admission moves a gate.
 */
@Composable
fun DevReviewsRoute(app: VanApplication, nav: DevNavigator) {
    val tokens = LocalVanTokens.current
    val reviews = rememberDevProjection(
        app = app, key = "reviews", sections = setOf("reviews"),
        emptySentence = "No review jobs are open.",
        isEmpty = { r: List<DevReview> -> r.isEmpty() },
        parse = { DialDevFabricParse.reviews(it.data) },
        fetch = { app.gatewayClient.dialDev.section(HubSection.REVIEWS) },
    )
    VanScreen(state = reviews.state, onRetry = reviews.reload) { list ->
        DevPage {
            item { SectionHeader("Reviews", detail = "${list.size} review jobs") }
            list.forEach { review ->
                item(key = review.reviewId) {
                    VanPanel {
                        Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                            Text(review.reviewId, style = tokens.type.headline, color = tokens.color.textPrimary)
                            DevField("Checkpoint", review.checkpoint)
                            DevField("Author", review.authorHarness)
                            DevField("Reviewer", review.reviewerHarness)
                            DevField("Claims verified", review.claimsVerified?.toString())
                            DevField("Claims rejected", review.claimsRejected?.toString())
                            DevField("Recommendation", review.recommendation?.let { "$it — does not advance the gate" })
                            review.blockingFindings.forEach { DevFindingCard(it) }
                        }
                    }
                }
            }
            item { DevRevisionFooter(reviews.envelope) }
        }
    }
}

/**
 * `work/dev/memory` — Memory / Handoffs (§6.8). Not VAN's personal Memory destination.
 *
 * @DataSource("GET /v1/dial-dev/memory") — shared-memory cursor, latest checkpoint, active
 *   handoff, OpenViking cursor and health, candidates awaiting admission, recent admissions,
 *   context freshness.
 *
 * Admission is not an owner tap here: DIAL admits. Owner decisions arrive through Attention.
 */
@Composable
fun DevMemoryRoute(app: VanApplication, nav: DevNavigator) {
    val memory = rememberDevProjection(
        app = app, key = "memory", sections = setOf("memory", "spmrf", "openviking"),
        emptySentence = "DIAL reports no shared memory yet.",
        parse = { DialDevFabricParse.memory(it.data) },
        fetch = { app.gatewayClient.dialDev.section(HubSection.MEMORY) },
    )
    VanScreen(state = memory.state, onRetry = memory.reload) { m ->
        DevPage {
            item { SectionHeader("Memory & handoffs", detail = "DIAL admits; VAN shows") }
            item {
                DevFieldGroup(
                    "Cursors",
                    listOf(
                        "Shared memory" to m.sharedMemoryCursor,
                        "Latest checkpoint" to m.latestCheckpoint,
                        "Active handoff" to m.activeHandoff,
                        "OpenViking cursor" to m.openVikingCursor,
                        "OpenViking health" to m.openVikingHealth,
                        "Context freshness" to m.contextFreshnessMs?.let { DialDevFormat.age(it) },
                    ),
                )
            }
            labelledSection("Awaiting admission", m.candidatesAwaitingAdmission, "Nothing is awaiting admission.")
            labelledSection("Recently admitted", m.recentAdmitted, "Nothing admitted recently.")
            item { DevRevisionFooter(memory.envelope) }
        }
    }
}

/**
 * `work/dev/research` — Research / VEKL (§6.9).
 *
 * @DataSource("GET /v1/dial-dev/research") — VEKL activations per task, forecast for the next
 *   packets, research jobs, Knowledge Resolution Trace refs.
 */
@Composable
fun DevResearchRoute(app: VanApplication, nav: DevNavigator) {
    val research = rememberDevProjection(
        app = app, key = "research", sections = setOf("research", "vekl"),
        emptySentence = "No research or knowledge activations reported.",
        parse = { DialDevFabricParse.research(it.data) },
        fetch = { app.gatewayClient.dialDev.section(HubSection.RESEARCH) },
    )
    VanScreen(state = research.state, onRetry = research.reload) { r ->
        DevPage {
            item { SectionHeader("Research / VEKL") }
            labelledSection("Activations", r.activations, "No VEKL activations reported.")
            labelledSection("Forecast", r.forecast, "No forecast for the next packets.")
            labelledSection("Research jobs", r.jobs, "No research jobs.")
            item { DevField("Trace refs", r.traceRefs.joinToString(", ").ifBlank { null }) }
            item { DevRevisionFooter(research.envelope) }
        }
    }
}

/**
 * `work/dev/design` — Frontend / Design (§6.9).
 *
 * @DataSource("GET /v1/dial-dev/design") — Screen Registry × Feature Graph coverage, FDEP/Stitch
 *   candidates, Visual/Experience Authority state, open design-change requests.
 */
@Composable
fun DevDesignRoute(app: VanApplication, nav: DevNavigator) {
    val design = rememberDevProjection(
        app = app, key = "design", sections = setOf("design"),
        emptySentence = "DIAL reports no design state yet.",
        parse = { DialDevFabricParse.design(it.data) },
        fetch = { app.gatewayClient.dialDev.section(HubSection.DESIGN) },
    )
    VanScreen(state = design.state, onRetry = design.reload) { d ->
        DevPage {
            item { SectionHeader("Frontend / Design") }
            item {
                DevFieldGroup(
                    "Authority",
                    listOf("Coverage" to d.coverage, "Visual authority" to d.visualAuthority, "Experience authority" to d.experienceAuthority),
                )
            }
            labelledSection("Candidates", d.candidates, "No FDEP/Stitch candidates.")
            labelledSection("Design-change requests", d.changeRequests, "No open design-change requests.")
            item { DevRevisionFooter(design.envelope) }
        }
    }
}

/**
 * `work/dev/ci` — Build / CI (§6.9).
 *
 * @DataSource("GET /v1/dial-dev/ci") — latest runs per branch/SHA with result and evidence link.
 */
@Composable
fun DevCiRoute(app: VanApplication, nav: DevNavigator) {
    val ci = rememberDevProjection(
        app = app, key = "ci", sections = setOf("ci"),
        emptySentence = "No CI runs reported.",
        isEmpty = { runs: List<DevCiRun> -> runs.isEmpty() },
        parse = { DialDevFabricParse.ci(it.data) },
        fetch = { app.gatewayClient.dialDev.section(HubSection.CI) },
    )
    VanScreen(state = ci.state, onRetry = ci.reload) { runs ->
        DevPage {
            item { SectionHeader("Build / CI", detail = "${runs.size} runs") }
            runs.forEachIndexed { index, run ->
                item(key = "run:$index") {
                    val ref = run.evidenceRef
                    EvidenceRow(
                        source = listOfNotNull(run.branch, DialDevFormat.shortSha(run.sha)).joinToString(" @ "),
                        trustTier = DialDevRoles.chipLabel(run.result),
                        trustRole = DialDevRoles.roleOrDisabled(DialDevResult.parse(run.result), DialDevRoles::result),
                        timeLabel = run.observedAt ?: "time not reported",
                        onOpen = ref?.let { r -> { nav.open(VanRoute.devEvidenceRoute(r)) } },
                    )
                }
            }
            item { DevRevisionFooter(ci.envelope) }
        }
    }
}

/**
 * `work/dev/security` — Security (§6.9).
 *
 * @DataSource("GET /v1/dial-dev/security") — open findings by severity, specialist review
 *   state, mutation-suite status.
 */
@Composable
fun DevSecurityRoute(app: VanApplication, nav: DevNavigator) {
    val security = rememberDevProjection(
        app = app, key = "security", sections = setOf("security"),
        emptySentence = "DIAL reports no security state yet.",
        parse = { DialDevFabricParse.security(it.data) },
        fetch = { app.gatewayClient.dialDev.section(HubSection.SECURITY) },
    )
    VanScreen(state = security.state, onRetry = security.reload) { s ->
        val ordered = s.findings.sortedBy { f -> DialDevSeverity.parse(f.severity)?.ordinal ?: DialDevSeverity.entries.size }
        DevPage {
            item { SectionHeader("Security", detail = "${s.findings.size} open findings") }
            item { DevFieldGroup("Reviews", listOf("Specialist review" to s.specialistReview, "Mutation suite" to s.mutationSuite)) }
            if (ordered.isEmpty()) item { DevNote("No open findings.") }
            ordered.forEachIndexed { index, finding -> item(key = "finding:$index") { DevFindingCard(finding) } }
            item { DevRevisionFooter(security.envelope) }
        }
    }
}

/**
 * `work/dev/evidence/{evidenceRef}` — one evidence record (§6.10). Raw payloads stay in DIAL.
 *
 * @DataSource("GET /v1/dial-dev/evidence/{ref}") — kind, checkpoint SHA, exact command, result,
 *   reproduced-by, admission state and authority.
 */
@Composable
fun DevEvidenceRoute(app: VanApplication, evidenceRef: String, nav: DevNavigator) {
    val tokens = LocalVanTokens.current
    val evidence = rememberDevProjection(
        app = app, key = "evidence:$evidenceRef", sections = setOf("evidence"),
        emptySentence = "DIAL has no evidence record $evidenceRef.",
        parse = { DialDevFabricParse.evidence(it.data) },
        fetch = { app.gatewayClient.dialDev.evidence(evidenceRef) },
    )
    VanScreen(state = evidence.state, onRetry = evidence.reload) { e ->
        DevPage {
            item { SectionHeader("Evidence", detail = e.ref) }
            item {
                EvidenceRow(
                    source = listOfNotNull(e.kind, e.ref).joinToString(" · "),
                    trustTier = DialDevRoles.chipLabel(e.admission),
                    trustRole = DialDevRoles.roleOrDisabled(DialDevAdmission.parse(e.admission), DialDevRoles::admission),
                    timeLabel = e.observedAt ?: "time not reported",
                )
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(tokens.space.space2)) {
                    StatusChip(label = DialDevRoles.chipLabel(e.result), role = DialDevRoles.roleOrDisabled(DialDevResult.parse(e.result), DialDevRoles::result))
                }
            }
            item {
                DevFieldGroup(
                    "Record",
                    listOf("Checkpoint" to e.checkpointSha, "Reproduced by" to e.reproducedBy, "Authority" to e.authority),
                )
            }
            item {
                VanPanel {
                    Column(verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
                        Text("Command", style = tokens.type.label, color = tokens.color.textTertiary)
                        Text(
                            e.command ?: "not reported",
                            style = tokens.type.data.copy(fontFamily = FontFamily.Monospace),
                            color = tokens.color.textPrimary,
                        )
                    }
                }
            }
            item { DevRevisionFooter(evidence.envelope) }
        }
    }
}

@Composable
fun DevFindingCard(finding: DevFinding) {
    FindingCard(
        title = finding.title,
        severityRole = DialDevRoles.roleOrDisabled(DialDevSeverity.parse(finding.severity), DialDevRoles::severity),
        detail = listOfNotNull(finding.severity?.let { "Severity $it" }, finding.state, finding.detail).joinToString(" · ").ifBlank { null },
    )
}

private fun androidx.compose.foundation.lazy.LazyListScope.labelledSection(title: String, rows: List<DevLabelled>, empty: String) {
    item(key = "section:$title") { SectionHeader(title, detail = if (rows.isEmpty()) empty else "${rows.size}") }
    rows.forEachIndexed { index, row ->
        item(key = "$title:$index") { DevLabelledRow(row) }
    }
}

@Composable
private fun DevLabelledRow(row: DevLabelled) {
    val tokens = LocalVanTokens.current
    VanPanel(dense = true) {
        Column(modifier = Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(tokens.space.space1)) {
            Text(row.title, style = tokens.type.body, color = tokens.color.textPrimary)
            row.state?.let { StatusChip(label = DialDevRoles.chipLabel(it), role = DialDevRoles.forAnyState(it)) }
            row.detail?.let { Text(it, style = tokens.type.label, color = tokens.color.textSecondary) }
        }
    }
}
