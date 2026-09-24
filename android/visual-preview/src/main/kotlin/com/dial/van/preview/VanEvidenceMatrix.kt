package com.dial.van.preview

import com.dial.van.overlay.OverlayTheme
import com.dial.van.visual.VanAuraSpecs
import com.dial.van.visual.VanAuthorityState
import com.dial.van.visual.VanDurableState
import com.dial.van.visual.VanEffectBudget
import com.dial.van.visual.VanEmbodimentProducers
import com.dial.van.visual.VanFiniteAction
import com.dial.van.visual.VanGlassTokens
import com.dial.van.visual.VanHealthState
import com.dial.van.visual.VanPresenceFrame
import com.dial.van.visual.VanPresentation
import com.dial.van.visual.VanScene
import com.dial.van.visual.VanSceneFrame
import com.dial.van.visual.VanSpeechState
import com.dial.van.visual.VanTradeSemantic
import com.dial.van.visual.VanTradeSemantics
import com.dial.van.visual.VanTurnPhase
import com.dial.van.visual.VanVisualState
import java.awt.Color
import java.awt.Font
import java.awt.GradientPaint
import java.awt.Graphics2D
import java.awt.geom.RoundRectangle2D
import java.awt.image.BufferedImage
import java.awt.image.ColorConvertOp
import java.io.File
import java.security.MessageDigest
import javax.imageio.ImageIO

/**
 * Named Rev 2.3 evidence matrix: per-scenario goldens, grayscale board, busy backdrops,
 * orthogonal activity/health combinations, and a checksum manifest.
 */
object VanEvidenceMatrix {

    const val AUTHORITY_REVISION = "2.3"
    const val EVIDENCE_DIR = "rev23"
    private const val PHASE = 0.18f

    data class Shot(
        val id: String,
        val state: VanDurableState,
        val mode: String,
        val budget: VanEffectBudget,
        val reducedMotion: Boolean,
        val action: String = "none",
        val blur: String = "optical-glass",
        /**
         * Motion-cycle phase this shot is rendered at. A finite-action shot renders at 0.5
         * (mid-cycle) rather than the ambient idle phase every other shot uses, so the
         * evidence does not always catch a gesture at its very first frame.
         */
        val phase: Float = PHASE,
    )

    private data class OrthogonalCase(
        val id: String,
        val frame: VanPresenceFrame,
    )

    private val orthogonalCases = listOf(
        OrthogonalCase(
            "LISTENING + DEGRADED",
            VanPresenceFrame(
                activity = VanDurableState.LISTENING,
                health = VanHealthState.DEGRADED,
                speech = VanSpeechState.LISTENING,
            ),
        ),
        OrthogonalCase(
            "THINKING + DEGRADED",
            VanPresenceFrame(
                activity = VanDurableState.THINKING,
                health = VanHealthState.DEGRADED,
                turn = VanTurnPhase.THINKING,
            ),
        ),
        OrthogonalCase(
            "SPEAKING + DEGRADED",
            VanPresenceFrame(
                activity = VanDurableState.THINKING,
                health = VanHealthState.DEGRADED,
                speech = VanSpeechState.SPEAKING,
                turn = VanTurnPhase.THINKING,
                mouthOpen = 0.62f,
                viseme = 4,
            ),
        ),
        OrthogonalCase(
            "WORKING + DEGRADED",
            VanPresenceFrame(
                activity = VanDurableState.WORKING,
                health = VanHealthState.DEGRADED,
            ),
        ),
        OrthogonalCase(
            "LISTENING + OFFLINE",
            VanPresenceFrame(
                activity = VanDurableState.LISTENING,
                health = VanHealthState.OFFLINE,
                speech = VanSpeechState.LISTENING,
            ),
        ),
        OrthogonalCase(
            "SPEAKING + OWNER WAIT",
            VanPresenceFrame(
                activity = VanDurableState.WORKING,
                authority = VanAuthorityState.WAITING_FOR_OWNER,
                speech = VanSpeechState.SPEAKING,
                mouthOpen = 0.55f,
                viseme = 3,
            ),
        ),
    )

    /**
     * DNA §2's four trade semantic tiers, each represented by the [VanTradeSemantic] whose
     * Zone C topology is that tier's clearest example. `VanTradeSemantic` itself has finer
     * gradations (WATCHING/SETUP/ENTRY on the way to favourable, RISK vs STOP on the way to
     * critical); this board is about proving the *tier* separation DNA names, not every
     * intermediate step — those already have their own coverage in `VanTradeSemanticTest`.
     */
    private data class SemanticTier(val label: String, val semantic: VanTradeSemantic)

    private val semanticTiers = listOf(
        SemanticTier("favourable", VanTradeSemantic.PROFIT),
        SemanticTier("deteriorating", VanTradeSemantic.RISK),
        SemanticTier("eventRisk", VanTradeSemantic.STOP),
        SemanticTier("critical", VanTradeSemantic.HALTED),
    )

    private val shots = listOf(
        Shot("floating-minimal-idle", VanDurableState.IDLE, "RESTING", VanEffectBudget.FULL, false),
        Shot("floating-minimal-listening", VanDurableState.LISTENING, "RESTING", VanEffectBudget.FULL, false),
        Shot("floating-working", VanDurableState.WORKING, "EXPANDED", VanEffectBudget.FULL, false),
        Shot("floating-waiting-for-owner", VanDurableState.WAITING_FOR_OWNER, "EXPANDED", VanEffectBudget.FULL, false),
        Shot("floating-warning", VanDurableState.WARNING, "COMPACT", VanEffectBudget.FULL, false),
        Shot("floating-urgent", VanDurableState.URGENT, "COMPACT", VanEffectBudget.FULL, false),
        Shot("floating-degraded", VanDurableState.DEGRADED, "RESTING", VanEffectBudget.FULL, false),
        Shot("floating-offline", VanDurableState.OFFLINE, "RESTING", VanEffectBudget.FULL, false),
        Shot("compact-actions", VanDurableState.IDLE, "COMPACT", VanEffectBudget.FULL, false),
        Shot("expanded-working", VanDurableState.WORKING, "EXPANDED", VanEffectBudget.FULL, false),
        Shot("approval-required", VanDurableState.WAITING_FOR_OWNER, "EXPANDED", VanEffectBudget.FULL, false),
        Shot("docked-idle", VanDurableState.IDLE, "DOCKED", VanEffectBudget.FULL, false),
        Shot("docked-degraded", VanDurableState.DEGRADED, "DOCKED", VanEffectBudget.FULL, false),
        Shot("reduced-motion-idle", VanDurableState.IDLE, "RESTING", VanEffectBudget.REDUCED_MOTION, true),
        Shot("reduced-motion-working", VanDurableState.WORKING, "EXPANDED", VanEffectBudget.REDUCED_MOTION, true),
        Shot("reduced-motion-urgent", VanDurableState.URGENT, "COMPACT", VanEffectBudget.REDUCED_MOTION, true),
        Shot("low-power-working", VanDurableState.WORKING, "EXPANDED", VanEffectBudget.LOW, false),
        Shot("static-working", VanDurableState.WORKING, "EXPANDED", VanEffectBudget.STATIC, true),
        Shot("glass-bench-idle-working-approval", VanDurableState.IDLE, "GLASS_BENCH", VanEffectBudget.FULL, false),
        Shot("command-centre-idle", VanDurableState.IDLE, "COMMAND_CENTRE", VanEffectBudget.FULL, false),
        Shot("command-centre-degraded", VanDurableState.DEGRADED, "COMMAND_CENTRE", VanEffectBudget.FULL, false),
    ) + VanFiniteAction.entries.map { action ->
        Shot(
            id = "action-${action.name.lowercase().replace('_', '-')}",
            state = when (action) {
                VanFiniteAction.CELEBRATE -> VanDurableState.SUCCESS
                VanFiniteAction.CAUTION -> VanDurableState.WARNING
                VanFiniteAction.CONFIRM -> VanDurableState.WAITING_FOR_OWNER
                else -> VanDurableState.IDLE
            },
            mode = "ACTION",
            budget = VanEffectBudget.FULL,
            reducedMotion = false,
            action = action.name,
            // GAP-F-012 — every finite-action frame is rendered mid-gesture (t=0.5) rather
            // than at frame zero, so the evidence shows the gesture actually playing.
            phase = 0.5f,
        )
    }

    /** GAP-F-012 — exposed for `VanEmbodimentCoverageTest`; production code has no need of it. */
    fun shotsForTest(): List<Shot> = shots

    fun writeAll(outputDir: File) {
        val dir = File(outputDir, EVIDENCE_DIR)
        dir.mkdirs()

        val orthogonalFile = File(dir, "orthogonal-presence.png")
        ImageIO.write(orthogonalPresenceBoard(), "png", orthogonalFile)

        // GAP-F-012 — every durable state against every trade semantic tier, one board.
        val semanticTierFile = File(dir, "state-by-semantic-tier.png")
        ImageIO.write(stateBySemanticTierBoard(), "png", semanticTierFile)

        val manifest = StringBuilder()
        manifest.appendLine("{")
        manifest.appendLine("  \"authority_revision\": \"$AUTHORITY_REVISION\",")
        manifest.appendLine("  \"device_profile\": \"preview-jvm-1.28x\",")
        manifest.appendLine("  \"shots\": [")
        shots.forEachIndexed { index, shot ->
            val image = renderShot(shot)
            val file = File(dir, "${shot.id}.png")
            ImageIO.write(image, "png", file)
            val sha = sha256(file)
            if (index > 0) manifest.appendLine(",")
            manifest.append(
                """    {"id":"${shot.id}","state":"${shot.state}","action":"${shot.action}","overlay_mode":"${shot.mode}","effect_budget":"${shot.budget}","reduced_motion":${shot.reducedMotion},"blur_capability":"${shot.blur}","authority_revision":"$AUTHORITY_REVISION","sha256":"$sha","bytes":${file.length()}}""",
            )
        }
        manifest.appendLine()
        manifest.appendLine("  ],")
        manifest.appendLine(
            """  "boards": [""" +
                """{"id":"orthogonal-presence","authority_revision":"$AUTHORITY_REVISION","sha256":"${sha256(orthogonalFile)}","bytes":${orthogonalFile.length()}},""" +
                """{"id":"state-by-semantic-tier","authority_revision":"$AUTHORITY_REVISION","sha256":"${sha256(semanticTierFile)}","bytes":${semanticTierFile.length()}}""" +
                """]""",
        )
        manifest.appendLine("}")
        File(dir, "manifest.json").writeText(manifest.toString())

        ImageIO.write(grayscaleBoard(), "png", File(dir, "grayscale-state-clarity.png"))
        ImageIO.write(busyBackdropBoard(), "png", File(dir, "busy-backdrop-resilience.png"))
        // P2-VIS-003's actual root cause used to be here: a third write of
        // `command-centre-degraded.png`, using the *default* (nominal) sheet, performed
        // after the manifest had already recorded that file's hash. So the degraded board
        // was overwritten with the idle one and the manifest described the file that no
        // longer existed — and `VanCommandCentreEvidence.reconcile` was then bolted on to
        // undo it. Both are gone. Every file this writer produces is written once, before
        // its hash is taken.
    }

    /**
     * Proves the runtime combinations Rev 2.3 was introduced for. Each cell is derived from a real
     * [VanPresenceFrame], then rendered with activity driving Zone A/B and semantic truth driving
     * Zone C through the same Java2D/Compose geometry engine.
     */
    fun orthogonalPresenceBoard(): BufferedImage {
        val cellW = 250
        val image = BufferedImage(40 + cellW * orthogonalCases.size, 390, BufferedImage.TYPE_INT_ARGB)
        val g = image.createGraphics()
        AwtVanRenderer.prepare(g)
        g.color = Color(0xFF0B1016.toInt())
        g.fillRect(0, 0, image.width, image.height)
        g.color = Color.WHITE
        g.font = Font("SansSerif", Font.BOLD, 20)
        g.drawString("VAN Rev 2.3 — orthogonal presence evidence", 24, 34)
        g.font = Font("SansSerif", Font.PLAIN, 12)
        g.color = Color(0xFF9AA7B6.toInt())
        g.drawString("Zone A/B = activity · Zone C = health/authority · OFFLINE/authority may take over pose", 24, 54)

        orthogonalCases.forEachIndexed { index, case ->
            val x = 20 + index * cellW
            val tile = orthogonalPresenceTile(case.frame, 210)
            g.drawImage(tile, x + 20, 72, 210, 210, null)
            val visual = case.frame.toVisualState()
            g.color = Color.WHITE
            g.font = Font("SansSerif", Font.BOLD, 12)
            g.drawString(case.id, x + 16, 306)
            g.color = Color(0xFFB6C2D0.toInt())
            g.font = Font("SansSerif", Font.PLAIN, 11)
            g.drawString("activity ${case.frame.activity}", x + 16, 326)
            g.drawString("pose ${visual.durableState}", x + 16, 344)
            g.drawString("zone C ${visual.resolvedSemanticState}", x + 16, 362)
        }
        g.dispose()
        return image
    }

    fun orthogonalPresenceTile(frame: VanPresenceFrame, size: Int = 200): BufferedImage {
        val image = BufferedImage(size, size, BufferedImage.TYPE_INT_ARGB)
        val g = image.createGraphics()
        AwtVanRenderer.prepare(g)
        g.color = Color(0xFF0B1016.toInt())
        g.fillRect(0, 0, size, size)
        val visual = frame.toVisualState()
        val activitySpec = VanAuraSpecs.forState(visual.durableState)
        val semanticSpec = VanAuraSpecs.forState(visual.resolvedSemanticState)
        val radius = size * 0.35f
        GlassPainter.drawAura(
            g = g,
            spec = activitySpec,
            cx = size * 0.5f,
            cy = size * 0.5f,
            radius = radius,
            budget = VanEffectBudget.FULL,
            phase = PHASE,
            semanticSpec = semanticSpec,
        )
        paintCharacter(
            g = g,
            state = visual.durableState,
            x = size * 0.10f,
            y = size * 0.05f,
            size = size * 0.80f,
            forceCanvas = true,
        )
        g.dispose()
        return image
    }

    /**
     * DNA §2 — every durable state against every trade semantic tier: Zone A/B (character +
     * activity field) come from [state], Zone C (the outer semantic envelope) comes from the
     * tier's representative [VanTradeSemantic], exactly as the running app composes them
     * (`VanPresenceFrame.semanticState`/`resolvedSemanticState` — never colour on the body).
     */
    fun stateBySemanticTierBoard(): BufferedImage {
        val states = VanDurableState.entries
        val cell = 132
        val labelW = 160
        val headerH = 74
        val image = BufferedImage(
            labelW + cell * semanticTiers.size,
            headerH + cell * states.size,
            BufferedImage.TYPE_INT_ARGB,
        )
        val g = image.createGraphics()
        AwtVanRenderer.prepare(g)
        g.color = Color(0xFF0B1016.toInt())
        g.fillRect(0, 0, image.width, image.height)
        g.color = Color.WHITE
        g.font = Font("SansSerif", Font.BOLD, 18)
        g.drawString("GAP-F-012 — every state × every trade semantic tier", 20, 30)
        g.font = Font("SansSerif", Font.PLAIN, 11)
        g.color = Color(0xFF9AA7B6.toInt())
        g.drawString("Zone A/B = state · Zone C = tier — colour never lands on VAN's body", 20, 50)

        semanticTiers.forEachIndexed { col, tier ->
            val x = labelW + col * cell
            g.color = Color.WHITE
            g.font = Font("SansSerif", Font.BOLD, 12)
            g.drawString(tier.label, x + 10, headerH - 8)
        }

        states.forEachIndexed { row, state ->
            val y = headerH + row * cell
            g.color = Color(0xFFB6C2D0.toInt())
            g.font = Font("SansSerif", Font.PLAIN, 11)
            g.drawString(state.name.lowercase().replace('_', ' '), 10, y + cell / 2)

            semanticTiers.forEachIndexed { col, tier ->
                val x = labelW + col * cell
                val tile = stateSemanticTierTile(state, tier.semantic, cell - 10)
                g.drawImage(tile, x + 5, y + 5, null)
            }
        }
        g.dispose()
        return image
    }

    fun stateSemanticTierTile(state: VanDurableState, semantic: VanTradeSemantic, size: Int = 120): BufferedImage {
        val image = BufferedImage(size, size, BufferedImage.TYPE_INT_ARGB)
        val g = image.createGraphics()
        AwtVanRenderer.prepare(g)
        g.color = Color(0xFF10161D.toInt())
        g.fillRect(0, 0, size, size)
        val activitySpec = VanAuraSpecs.forState(state)
        val semanticSpec = VanTradeSemantics.auraFor(semantic)
        GlassPainter.drawAura(
            g = g,
            spec = activitySpec,
            cx = size * 0.5f,
            cy = size * 0.5f,
            radius = size * 0.30f,
            budget = VanEffectBudget.FULL,
            phase = PHASE,
            semanticSpec = semanticSpec,
        )
        paintCharacter(g, state, size * 0.10f, size * 0.05f, size * 0.80f, forceCanvas = true)
        g.dispose()
        return image
    }

    fun grayscaleBoard(): BufferedImage {
        val states = listOf(
            VanDurableState.WAITING_FOR_OWNER,
            VanDurableState.WARNING,
            VanDurableState.ERROR,
            VanDurableState.SUCCESS,
            VanDurableState.URGENT,
        )
        val cell = 220
        val image = BufferedImage(80 + cell * states.size, 320, BufferedImage.TYPE_INT_ARGB)
        val g = image.createGraphics()
        AwtVanRenderer.prepare(g)
        g.color = Color(0xFF10141A.toInt())
        g.fillRect(0, 0, image.width, image.height)
        g.color = Color.WHITE
        g.font = Font("SansSerif", Font.BOLD, 18)
        g.drawString("Gate E — grayscale state clarity", 24, 36)
        states.forEachIndexed { i, state ->
            val tile = presenceTile(state, VanEffectBudget.FULL)
            val gray = grayscale(tile)
            g.drawImage(gray, 40 + i * cell, 60, cell - 24, cell - 24, null)
            g.color = Color.LIGHT_GRAY
            g.font = Font("SansSerif", Font.BOLD, 14)
            g.drawString(state.name.lowercase().replace('_', ' '), 48 + i * cell, 300)
        }
        g.dispose()
        return image
    }

    fun busyBackdropBoard(): BufferedImage {
        val w = 1400
        val h = 420
        val image = BufferedImage(w, h, BufferedImage.TYPE_INT_ARGB)
        val g = image.createGraphics()
        AwtVanRenderer.prepare(g)
        val labels = listOf("bright white", "dark app", "saturated", "dense text", "map-like")
        val tileW = 260
        labels.forEachIndexed { i, label ->
            val x = 20 + i * (tileW + 16)
            paintBackdrop(g, x, 40, tileW, 320, i)
            val spec = VanAuraSpecs.forState(VanDurableState.IDLE)
            GlassPainter.drawAura(g, spec, x + tileW / 2f, 180f, 70f)
            paintCharacter(g, VanDurableState.IDLE, x + 70f, 90f, 120f)
            g.color = Color(0xFF102030.toInt())
            g.font = Font("SansSerif", Font.BOLD, 14)
            g.drawString(label, x + 16, 380)
        }
        g.dispose()
        return image
    }

    private fun renderShot(shot: Shot): BufferedImage {
        if (shot.mode == "GLASS_BENCH") return VanPreviewSheets.glassTokenSheet()
        // P2-VIS-003 — the board is rendered for the health it claims to show, here, once.
        //
        // Both shots used to route through a renderer that took no arguments and hardcoded
        // one health snapshot, producing byte-identical files, and a `reconcile` pass then
        // overwrote the two PNGs afterwards from a *second* Command Centre renderer and
        // patched the manifest hashes with a regular expression. Writing the right file the
        // first time removes both the collapse and the second renderer.
        if (shot.mode == "COMMAND_CENTRE") {
            return VanCommandCentreEvidence.render(degraded = shot.state == VanDurableState.DEGRADED)
        }
        val image = BufferedImage(480, 640, BufferedImage.TYPE_INT_ARGB)
        val g = image.createGraphics()
        AwtVanRenderer.prepare(g)
        paintBackdrop(g, 0, 0, 480, 640, 1)
        val spec = VanAuraSpecs.forState(shot.state, shot.budget)
        when (shot.mode) {
            "DOCKED" -> {
                GlassPainter.drawCrescentAura(g, spec, 380f, 220f, OverlayTheme.DOCK_WIDTH_DP * 1.28f, OverlayTheme.DOCK_HIT_DP * 1.28f, shot.budget, PHASE)
                paintCharacter(g, shot.state, 390f, 210f, OverlayTheme.DOCK_CHARACTER_DP * 1.28f, shot.reducedMotion)
            }
            "COMPACT" -> {
                val style = VanGlassTokens.forState(shot.state, budget = shot.budget)
                val card = RoundRectangle2D.Float(
                    80f,
                    400f,
                    OverlayTheme.COMPACT_WIDTH_DP * 1.1f,
                    OverlayTheme.COMPACT_CAPSULE_HEIGHT_DP * 1.15f,
                    28f,
                    28f,
                )
                GlassPainter.fillGlass(g, style, card, 1.28f)
                GlassPainter.drawAura(g, spec, 150f, 280f, 80f, shot.budget, PHASE)
                paintCharacter(g, shot.state, 90f, 180f, 160f, shot.reducedMotion)
                g.font = Font("SansSerif", Font.BOLD, 13)
                OverlayTheme.COMPACT_ACTIONS.chunked(2).forEachIndexed { row, labels ->
                    var ax = 200f
                    labels.forEach { label ->
                        val tw = 18f + label.length * 7.2f
                        g.color = Color(0x3300DAFF, true)
                        g.fill(RoundRectangle2D.Float(ax, 432f + row * 32f, tw, 24f, 10f, 10f))
                        g.color = Color.WHITE
                        g.drawString(label, ax + 8f, 450f + row * 32f)
                        ax += tw + 8f
                    }
                }
            }
            "EXPANDED" -> {
                val style = VanGlassTokens.forState(shot.state, budget = shot.budget)
                val card = RoundRectangle2D.Float(80f, 340f, OverlayTheme.EXPANDED_WIDTH_DP * 1.1f, OverlayTheme.EXPANDED_HEIGHT_DP.toFloat(), 28f, 28f)
                GlassPainter.fillGlass(g, style, card, 1.28f)
                GlassPainter.drawAura(g, spec, 150f, 260f, 80f, shot.budget, PHASE)
                paintCharacter(g, shot.state, 90f, 160f, 160f, shot.reducedMotion)
                g.color = Color.WHITE
                g.font = Font("SansSerif", Font.BOLD, 16)
                g.drawString("Van", 200f, 380f)
                g.font = Font("SansSerif", Font.PLAIN, 13)
                g.drawString(shot.state.name.lowercase().replace('_', ' '), 200f, 400f)
            }
            "ACTION" -> {
                val actionCode = VanFiniteAction.entries.first { it.name == shot.action }.code
                // GAP-F-012 — rendered mid-gesture (shot.phase = 0.5), not at frame zero.
                GlassPainter.drawAura(g, spec, 240f, 300f, 90f, shot.budget, shot.phase)
                paintCharacter(g, shot.state, 150f, 180f, 180f, shot.reducedMotion, actionCode, phase = shot.phase)
            }
            else -> {
                GlassPainter.drawAura(g, spec, 240f, 300f, 90f, shot.budget, PHASE)
                paintCharacter(g, shot.state, 150f, 180f, 180f, shot.reducedMotion)
            }
        }
        g.color = Color.WHITE
        g.font = Font("SansSerif", Font.BOLD, 16)
        g.drawString(shot.id, 20, 30)
        g.font = Font("SansSerif", Font.PLAIN, 12)
        g.drawString("${shot.state} · ${shot.mode} · ${shot.budget}", 20, 50)
        g.dispose()
        return image
    }

    fun presenceTile(state: VanDurableState, budget: VanEffectBudget = VanEffectBudget.FULL): BufferedImage {
        val image = BufferedImage(200, 200, BufferedImage.TYPE_INT_ARGB)
        val g = image.createGraphics()
        AwtVanRenderer.prepare(g)
        g.color = Color(0xFF0B1016.toInt())
        g.fillRect(0, 0, 200, 200)
        val spec = VanAuraSpecs.forState(state, budget)
        GlassPainter.drawAura(g, spec, 100f, 100f, 70f, budget, PHASE)
        paintCharacter(g, state, 20f, 10f, 160f, forceCanvas = true)
        g.dispose()
        return image
    }

    private fun paintCharacter(
        g: Graphics2D,
        state: VanDurableState,
        x: Float,
        y: Float,
        size: Float,
        reducedMotion: Boolean = false,
        actionCode: Int = 0,
        forceCanvas: Boolean = false,
        phase: Float = PHASE,
    ) {
        AwtVanRenderer.paintVan(
            g,
            VanVisualState(durableState = state, actionCode = actionCode),
            VanSceneFrame(presentation = VanPresentation.COMPACT, phase = phase, reducedMotion = reducedMotion),
            x, y, size, size,
        )
    }

    private fun paintBackdrop(g: Graphics2D, x: Int, y: Int, w: Int, h: Int, kind: Int) {
        when (kind) {
            0 -> {
                g.color = Color.WHITE
                g.fillRect(x, y, w, h)
            }
            1 -> {
                g.paint = GradientPaint(x.toFloat(), y.toFloat(), Color(0xFF121820.toInt()), x.toFloat(), (y + h).toFloat(), Color(0xFF070A0E.toInt()))
                g.fillRect(x, y, w, h)
            }
            2 -> {
                g.color = Color(0xFFE11D48.toInt())
                g.fillRect(x, y, w, h)
                g.color = Color(0xFF22C55E.toInt())
                g.fillOval(x + 20, y + 40, w / 2, h / 2)
                g.color = Color(0xFF3B82F6.toInt())
                g.fillOval(x + w / 3, y + h / 3, w / 2, h / 2)
            }
            3 -> {
                g.color = Color(0xFFF8FAFC.toInt())
                g.fillRect(x, y, w, h)
                g.color = Color(0xFF0F172A.toInt())
                g.font = Font("SansSerif", Font.PLAIN, 10)
                repeat(18) { row ->
                    g.drawString("owner command queue hermes profile van mesh evidence ".repeat(2), x + 6, y + 18 + row * 16)
                }
            }
            else -> {
                g.color = Color(0xFFE2E8F0.toInt())
                g.fillRect(x, y, w, h)
                g.color = Color(0xFF94A3B8.toInt())
                for (gx in 0..w step 18) g.drawLine(x + gx, y, x + gx, y + h)
                for (gy in 0..h step 18) g.drawLine(x, y + gy, x + w, y + gy)
                g.color = Color(0xFF64748B.toInt())
                g.fillOval(x + w / 4, y + h / 4, w / 3, h / 5)
            }
        }
    }

    fun grayscale(src: BufferedImage): BufferedImage {
        val gray = BufferedImage(src.width, src.height, BufferedImage.TYPE_BYTE_GRAY)
        ColorConvertOp(null).filter(src, gray)
        return gray
    }

    fun meanAbsoluteDifference(a: BufferedImage, b: BufferedImage): Double {
        var total = 0L
        val w = minOf(a.width, b.width)
        val h = minOf(a.height, b.height)
        for (y in 0 until h) {
            for (x in 0 until w) {
                total += kotlin.math.abs((a.getRGB(x, y) and 0xFF) - (b.getRGB(x, y) and 0xFF))
            }
        }
        return total.toDouble() / (w * h)
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(file.readBytes())
        return digest.joinToString("") { "%02x".format(it) }
    }
}
