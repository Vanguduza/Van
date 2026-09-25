package com.dial.van.preview

import com.dial.van.command.nav.VanRoute
import com.dial.van.design.LiveBadgeFormat
import com.dial.van.design.ScreenState
import com.dial.van.design.StatusSemantics
import com.dial.van.dialdev.DialDevEnvelope
import com.dial.van.dialdev.DialDevFabricParse
import com.dial.van.dialdev.DialDevFetch
import com.dial.van.dialdev.DialDevFormat
import com.dial.van.dialdev.DialDevFreshness
import com.dial.van.dialdev.DialDevParse
import com.dial.van.dialdev.DialDevRoles
import com.dial.van.dialdev.DialDevScreenReducer
import com.dial.van.dialdev.DialDevSemantics
import com.dial.van.visual.VanPalette
import java.awt.BasicStroke
import java.awt.Color
import java.awt.Font
import java.awt.Graphics2D
import java.awt.geom.Ellipse2D
import java.awt.geom.RoundRectangle2D
import java.awt.image.BufferedImage
import java.io.File
import javax.imageio.ImageIO

/**
 * VAN-DEV-011 / DNA V6 — every Development Control Centre route rendered in all seven
 * screen states (VAN-DEVCC-R1 §8: "all seven states rendered per route in visual-preview").
 *
 * The state in each tile is not drawn from a label: it is what the shipping reducer
 * (`DialDevScreenReducer`) returns for a fixture projection, parsed by the shipping parser for
 * that route. The fixtures below live here and only here (DNA §5: "Preview fixtures live only
 * in visual-preview") — nothing in `app/src/main` can reach them.
 *
 * Colours are the palette's own role colours (`VanPalette.DARK.statusRoles`), by role name,
 * the same names the app's `StatusChip` resolves; no colour is chosen here.
 */
object VanDevControlCentreStates {

    const val DIR = "dev-control-centre"

    /** DNA §5's seven, in the order a sheet shows them. */
    enum class Seven { LOADING, CONTENT, EMPTY, ERROR, DEGRADED, OFFLINE, STALE }

    data class PreviewRow(val title: String, val caption: String, val role: String)

    data class Tile(val template: String, val expected: Seven, val state: ScreenState<List<PreviewRow>>)

    private class RouteFixture(
        val data: String,
        val staleMs: Long = DialDevFreshness.DEFAULT_STALE_MS,
        val rows: (DialDevEnvelope) -> List<PreviewRow>,
    )

    private fun task(id: String, state: String, extra: String = "") =
        """{"task_id":"$id","title":"$id","du":"$id","stage":"STG-07","state":"$state","harness":"claude-code","model":"opus"$extra}"""

    private val tasksJson = listOf(
        task("HOT-DU-021", "RUNNING"),
        task("HOT-DU-022", "VERIFYING", ""","completion_candidate":true"""),
        task("HOT-DU-023", "BLOCKED", ""","blockers":["lease L-207"]"""),
        task("HOT-DU-024", "WAITING_OWNER"),
        task("HOT-DU-025", "PASS"),
    ).joinToString(",")

    private fun taskRows(env: DialDevEnvelope) = DialDevParse.tasks(env.data, env.observedAt).map {
        val p = it.presentation
        PreviewRow(it.title, p.caption, p.role)
    }

    private fun stateRow(title: String, raw: String?) = PreviewRow(title, DialDevRoles.chipLabel(raw), DialDevRoles.forAnyState(raw))

    /** One fixture per §2.1 route, keyed by its `VanRoute` template. */
    private val fixtures: Map<String, RouteFixture> = mapOf(
        VanRoute.WORK_DEV to RouteFixture(
            """{"readiness":{"forensic_build_ready":true,"oracle_gate":"HEALTHY"},"counts":{"ready":4,"running":2,"blocked":1,"needs_you":1,"in_review":1},"now":[$tasksJson]}""",
        ) { env ->
            val home = DialDevParse.home(env.data, env.observedAt)
            home.now.map { PreviewRow(it.title, it.presentation.caption, it.presentation.role) }.let { now ->
                if (now.isEmpty()) now
                else listOf(PreviewRow("Running", DialDevFormat.count(home.counts["running"]), StatusSemantics.ROLE_MONITOR)) + now
            }
        },
        VanRoute.WORK_DEV_PLAN to RouteFixture(
            """{"stages":[{"stage_id":"STG-00","state":"PASS"},{"stage_id":"STG-07","state":"RUNNING"},{"stage_id":"STG-12","state":"WAITING_EXTERNAL","external_blockers":["Netcup DNS"]},{"stage_id":"STG-21","state":"NOT_APPLICABLE","applicable":false}],"plan_fingerprint":"fp-1"}""",
        ) { env ->
            DialDevParse.stagePlan(env.data, env.sources).stages.map { s ->
                val p = DialDevSemantics.presentRaw(s.rawState)
                PreviewRow(s.stageId, p.caption, p.role)
            }
        },
        VanRoute.WORK_DEV_TASKS to RouteFixture("""{"tasks":[$tasksJson]}""", rows = ::taskRows),
        VanRoute.WORK_DEV_GRAPH to RouteFixture(
            """{"nodes":[{"task_id":"HOT-DU-021","state":"RUNNING","critical":true},{"task_id":"HOT-DU-023","state":"BLOCKED"}],"edges":[{"from":"HOT-DU-021","to":"HOT-DU-023"}]}""",
        ) { env ->
            val g = DialDevParse.graph(env.data)
            g.accessibleOrder().map { n ->
                val p = DialDevSemantics.presentRaw(n.rawState)
                PreviewRow(n.taskId + if (n.critical) " · critical path" else "", p.caption + " · unblocks ${g.dependentsOf(n.taskId).size}", p.role)
            }
        },
        VanRoute.WORK_DEV_TASK to RouteFixture("""{"task":${task("HOT-DU-022", "VERIFYING", ""","completion_candidate":true,"lease":"L-207"""")}}""") { env ->
            listOfNotNull(DialDevParse.taskDetail(env.data, env.observedAt)).flatMap { t ->
                listOf(
                    PreviewRow(t.row.title, t.row.presentation.caption, t.row.presentation.role),
                    PreviewRow("Lease", t.leaseId ?: "not reported", StatusSemantics.ROLE_MONITOR),
                )
            }
        },
        VanRoute.WORK_DEV_AGENTS to RouteFixture(
            """{"agents":[{"actor_id":"claude-w5","harness":"claude-code","intent":{"paths":["android/"]}},{"actor_id":"codex-w6","harness":"codex","intent":{"paths":["android/app"]}}]}""",
        ) { env ->
            val a = DialDevFabricParse.agents(env.data, env.observedAt)
            a.agents.map { PreviewRow(it.actorId, it.harness ?: "harness not reported", StatusSemantics.ROLE_ENGAGED) } +
                a.overlaps.map { PreviewRow("Overlap", it.paths.joinToString(), StatusSemantics.ROLE_EVENT_RISK) }
        },
        VanRoute.WORK_DEV_WORKSPACES to RouteFixture(
            """{"workspaces":[{"workspace_id":"ws-7","status":"HEALTHY","test_state":"PASS"},{"workspace_id":"ws-8","status":"DEGRADED","test_state":"FAIL"}]}""",
            staleMs = DialDevFreshness.WORKSPACES_STALE_MS,
        ) { env -> DialDevFabricParse.workspaces(env.data).map { stateRow(it.workspaceId, it.status) } },
        VanRoute.WORK_DEV_WORKSPACE to RouteFixture(
            """{"workspace":{"workspace_id":"ws-7","status":"HEALTHY","test_state":"RUNNING","lease":"L-207"}}""",
            staleMs = DialDevFreshness.WORKSPACES_STALE_MS,
        ) { env -> listOfNotNull(DialDevFabricParse.workspace(env.data)).flatMap { listOf(stateRow(it.workspaceId, it.status), stateRow("Tests", it.testState)) } },
        VanRoute.WORK_DEV_RESEARCH to RouteFixture("""{"activations":[{"task_id":"HOT-DU-021","state":"ADMITTED"}],"jobs":[{"title":"Orca drift","state":"RUNNING"}]}""") { env ->
            val r = DialDevFabricParse.research(env.data)
            (r.activations + r.jobs).map { stateRow(it.title, it.state) }
        },
        VanRoute.WORK_DEV_DESIGN to RouteFixture("""{"candidates":[{"id":"FDEP-3","state":"CANDIDATE"}],"change_requests":[{"title":"Home density","state":"PENDING"}]}""") { env ->
            val d = DialDevFabricParse.design(env.data)
            (d.candidates + d.changeRequests).map { stateRow(it.title, it.state) }
        },
        VanRoute.WORK_DEV_CI to RouteFixture("""{"runs":[{"branch":"main","sha":"be49e8e7","result":"PASS"},{"branch":"hot-du-021","sha":"abc12345","result":"FAIL"}]}""") { env ->
            DialDevFabricParse.ci(env.data).map { stateRow("${it.branch} @ ${it.sha}", it.result) }
        },
        VanRoute.WORK_DEV_SECURITY to RouteFixture("""{"findings":[{"title":"Token in log","severity":"HIGH"}],"mutation_suite":"PASS"}""") { env ->
            DialDevFabricParse.security(env.data).findings.map { f ->
                PreviewRow(f.title, f.severity ?: "UNKNOWN", DialDevRoles.roleOrDisabled(com.dial.van.dialdev.DialDevSeverity.parse(f.severity), DialDevRoles::severity))
            }
        },
        VanRoute.WORK_DEV_REVIEWS to RouteFixture("""{"reviews":[{"review_id":"RV-1","recommendation":"merge","blocking_findings":[{"title":"missing test","severity":"MEDIUM"}]}]}""") { env ->
            DialDevFabricParse.reviews(env.data).flatMap { r ->
                listOf(PreviewRow(r.reviewId, "${r.recommendation} — does not advance the gate", StatusSemantics.ROLE_COGNITION)) +
                    r.blockingFindings.map { PreviewRow(it.title, it.severity ?: "UNKNOWN", StatusSemantics.ROLE_EVENT_RISK) }
            }
        },
        VanRoute.WORK_DEV_MEMORY to RouteFixture("""{"shared_memory_cursor":"c-481","candidates_awaiting_admission":[{"title":"lease lesson","state":"CANDIDATE"}]}""") { env ->
            val m = DialDevFabricParse.memory(env.data)
            listOfNotNull(m.sharedMemoryCursor?.let { PreviewRow("Shared memory", it, StatusSemantics.ROLE_MONITOR) }) +
                m.candidatesAwaitingAdmission.map { stateRow(it.title, it.state) }
        },
        VanRoute.WORK_DEV_EVIDENCE to RouteFixture("""{"evidence":{"ref":"EV-42","kind":"test","command":"npm run verify","result":"PASS","admission_state":"ADMITTED"}}""") { env ->
            listOfNotNull(DialDevFabricParse.evidence(env.data)).flatMap { listOf(stateRow(it.ref, it.admission), stateRow(it.command ?: "command", it.result)) }
        },
    )

    fun templates(): List<String> = fixtures.keys.toList()

    private fun envelope(data: String, freshnessMs: Long, degraded: String = "[]"): DialDevEnvelope =
        DialDevEnvelope.parse(
            """{"projection_revision":"sha256:preview","observed_at":"2026-09-23T16:40:00Z","freshness_ms":$freshnessMs,"degraded":$degraded,"data":$data}""",
        ) ?: error("preview fixture is not an envelope")

    /** The seven tiles for one route, each the shipping reducer's answer to a fixture input. */
    fun tilesFor(template: String): List<Tile> {
        val fx = fixtures[template] ?: error("no preview fixture for $template")
        val now = 1_000_000L
        fun reduce(fetch: DialDevFetch) = DialDevScreenReducer.reduce(
            fetch, null, now, fx.staleMs, fx.rows, { it.isEmpty() }, "Nothing here yet.",
        )
        fun loaded(env: DialDevEnvelope) = DialDevFetch.Loaded(env, now)
        val degraded = """[{"subsystem":"openviking","effect":"semantic recall unavailable","still_works":["tasks","workspaces","evidence"]}]"""
        return listOf(
            Tile(template, Seven.LOADING, reduce(DialDevFetch.Loading)),
            Tile(template, Seven.CONTENT, reduce(loaded(envelope(fx.data, 1_200)))),
            Tile(template, Seven.EMPTY, reduce(loaded(envelope("{}", 1_200)))),
            Tile(template, Seven.ERROR, reduce(DialDevFetch.Failed(503, """{"detail":{"error":"dial_dev_unavailable"}}""", null))),
            Tile(template, Seven.DEGRADED, reduce(loaded(envelope(fx.data, 1_200, degraded)))),
            Tile(template, Seven.OFFLINE, reduce(DialDevFetch.Offline)),
            Tile(template, Seven.STALE, reduce(loaded(envelope(fx.data, 184_000)))),
        )
    }

    /** Which of the seven a reduced state is — exhaustive over the sealed class. */
    fun classify(state: ScreenState<*>): Seven = when (state) {
        is ScreenState.Loading -> Seven.LOADING
        is ScreenState.Content -> Seven.CONTENT
        is ScreenState.Empty -> Seven.EMPTY
        is ScreenState.Error -> Seven.ERROR
        is ScreenState.Degraded -> Seven.DEGRADED
        is ScreenState.Offline -> Seven.OFFLINE
        is ScreenState.Stale -> Seven.STALE
    }

    fun slug(template: String): String =
        template.replace(Regex("[{}?=]"), "").replace('/', '_').replace("__", "_").trim('_')

    fun writeAll(outputDir: File): List<File> {
        val dir = File(outputDir, DIR).apply { mkdirs() }
        return templates().map { template ->
            File(dir, "${slug(template)}_seven_states.png").also { ImageIO.write(sheetFor(template), "png", it) }
        }
    }

    // ---- Rendering ---------------------------------------------------------------------

    private val scheme = VanPalette.DARK
    private const val TILE_W = 380
    private const val TILE_H = 320
    private const val GAP = 16
    private const val HEADER = 70

    private fun role(name: String) = Color(scheme.statusRoles[name] ?: scheme.statusRoles.getValue(StatusSemantics.ROLE_DISABLED), true)
    private fun font(size: Int, bold: Boolean = false) = Font(Font.SANS_SERIF, if (bold) Font.BOLD else Font.PLAIN, size)

    fun sheetFor(template: String): BufferedImage {
        val tiles = tilesFor(template)
        val cols = 4
        val rows = (tiles.size + cols - 1) / cols
        val w = GAP + cols * (TILE_W + GAP)
        val h = HEADER + rows * (TILE_H + GAP) + GAP
        val image = BufferedImage(w, h, BufferedImage.TYPE_INT_ARGB)
        val g = image.createGraphics()
        AwtVanRenderer.prepare(g)
        g.color = Color(scheme.background, true)
        g.fillRect(0, 0, w, h)
        g.color = Color(scheme.onBackground, true)
        g.font = font(22, bold = true)
        g.drawString(template, GAP, 34)
        g.font = font(14)
        g.color = Color(scheme.onSurfaceVariant, true)
        g.drawString("Seven screen states, each the shipping reducer's output for a preview fixture (visual-preview only).", GAP, 56)
        tiles.forEachIndexed { index, tile ->
            val x = GAP + (index % cols) * (TILE_W + GAP)
            val y = HEADER + (index / cols) * (TILE_H + GAP)
            drawTile(g, tile, x, y)
        }
        g.dispose()
        return image
    }

    private fun drawTile(g: Graphics2D, tile: Tile, x: Int, y: Int) {
        g.color = Color(scheme.surfaceVariant, true)
        g.fill(RoundRectangle2D.Float(x.toFloat(), y.toFloat(), TILE_W.toFloat(), TILE_H.toFloat(), 28f, 28f))
        g.color = Color(scheme.onSurface and 0x14FFFFFF, true)
        g.stroke = BasicStroke(1f)
        g.draw(RoundRectangle2D.Float(x.toFloat(), y.toFloat(), TILE_W.toFloat(), TILE_H.toFloat(), 28f, 28f))
        g.color = Color(scheme.textTertiary, true)
        g.font = font(13, bold = true)
        g.drawString(tile.expected.name, x + 16, y + 26)
        var cy = y + 50
        val state = tile.state
        when (state) {
            is ScreenState.Loading -> repeat(3) {
                g.color = Color(scheme.surface, true)
                g.fill(RoundRectangle2D.Float((x + 16).toFloat(), cy.toFloat(), (TILE_W - 32).toFloat(), 60f, 20f, 20f))
                cy += 72
            }
            is ScreenState.Content -> drawRows(g, state.data, x, cy, y + TILE_H)
            is ScreenState.Empty -> sentence(g, state.sentence, x, cy + 60, Color(scheme.onSurfaceVariant, true))
            is ScreenState.Error -> {
                sentence(g, state.message, x, cy + 30, role(StatusSemantics.ROLE_CRITICAL))
                if (state.canRetry) chip(g, "Retry", StatusSemantics.ROLE_ENGAGED, x + 16, cy + 150)
            }
            is ScreenState.Degraded -> {
                chip(g, "DEGRADED", StatusSemantics.ROLE_EVENT_RISK, x + 16, cy)
                cy += 34
                state.rows.forEach { row -> cy = sentence(g, row.sentence, x, cy + 16, Color(scheme.onSurfaceVariant, true)) }
                state.data?.let { drawRows(g, it, x, cy + 8, y + TILE_H) }
            }
            is ScreenState.Offline -> {
                chip(g, "OFFLINE", StatusSemantics.ROLE_DISABLED, x + 16, cy)
                sentence(g, if (state.queuedCount > 0) "Offline — ${state.queuedCount} queued." else "Offline — I'll catch up. Owner actions are never queued.", x, cy + 60, Color(scheme.onSurfaceVariant, true))
            }
            is ScreenState.Stale -> {
                chip(g, "STALE ${LiveBadgeFormat.hhmm(state.ageMs)}", StatusSemantics.ROLE_EVENT_RISK, x + 16, cy)
                drawRows(g, state.content, x, cy + 40, y + TILE_H)
            }
        }
    }

    private fun drawRows(g: Graphics2D, rows: List<PreviewRow>, x: Int, top: Int, bottom: Int) {
        var cy = top
        rows.forEach { row ->
            if (cy + 46 <= bottom) {
                g.color = Color(scheme.onBackground, true)
                g.font = font(14)
                g.drawString(clip(row.title, 40), x + 16, cy + 14)
                chip(g, clip(row.caption, 36), row.role, x + 16, cy + 22)
                cy += 50
            }
        }
    }

    private fun chip(g: Graphics2D, label: String, roleName: String, x: Int, y: Int) {
        val c = role(roleName)
        g.font = font(12, bold = true)
        val width = g.fontMetrics.stringWidth(label) + 34
        g.color = Color(c.red, c.green, c.blue, 41)
        g.fill(RoundRectangle2D.Float(x.toFloat(), y.toFloat(), width.toFloat(), 22f, 16f, 16f))
        g.color = c
        g.fill(Ellipse2D.Float((x + 10).toFloat(), (y + 8).toFloat(), 6f, 6f))
        g.drawString(label, x + 22, y + 16)
    }

    private fun sentence(g: Graphics2D, text: String, x: Int, y: Int, color: Color): Int {
        g.color = color
        g.font = font(13)
        var cy = y
        text.split(' ').fold(StringBuilder()) { line, word ->
            if (g.fontMetrics.stringWidth("$line $word") > TILE_W - 32) {
                g.drawString(line.toString(), x + 16, cy)
                cy += 18
                StringBuilder(word)
            } else {
                if (line.isNotEmpty()) line.append(' ')
                line.append(word)
            }
        }.let { if (it.isNotEmpty()) g.drawString(it.toString(), x + 16, cy) }
        return cy + 18
    }

    private fun clip(text: String, max: Int) = if (text.length <= max) text else text.take(max - 1) + "…"
}
