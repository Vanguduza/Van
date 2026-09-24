package com.dial.van.preview

import com.dial.van.degraded.DegradedMode
import com.dial.van.overlay.OverlayTheme
import com.dial.van.visual.VanAuraSpec
import com.dial.van.visual.VanAuraSpecs
import com.dial.van.visual.VanCaptions
import com.dial.van.visual.VanDurableState
import com.dial.van.visual.VanEffectBudget
import com.dial.van.visual.VanFiniteAction
import com.dial.van.visual.VanGlassStyle
import com.dial.van.visual.VanGlassTokens
import com.dial.van.visual.VanPresence
import com.dial.van.visual.VanPresentation
import com.dial.van.visual.VanScene
import com.dial.van.visual.VanSceneFrame
import com.dial.van.visual.VanStatusPalette
import com.dial.van.visual.VanVisualState
import java.awt.BasicStroke
import java.awt.Color
import java.awt.Font
import java.awt.GradientPaint
import java.awt.Graphics2D
import java.awt.GraphicsEnvironment
import java.awt.geom.Ellipse2D
import java.awt.geom.Line2D
import java.awt.geom.RoundRectangle2D
import java.awt.image.BufferedImage

/**
 * Composes the owner-facing preview sheets.
 *
 * Every value that decides how this looks comes from shipping code: [VanGlassTokens] for the
 * DIAL Glass shell (§3/§8), [VanAuraSpecs] for the electrical aura (§7), the retired owner-art rung no longer participates in
 * character bitmaps, [VanScene] when owner art is absent, and [VanStatusPalette]/[VanPresence]
 * for wording. Nothing here is hand-tuned for the screenshot.
 *
 * Section references are to `docs/VAN_VISUAL_PRODUCTION_SYSTEM_REV_2_1_MASTER_BLUEPRINT.md`.
 */
object VanPreviewSheets {

    private const val BACKDROP = 0xFF070A0E.toInt()
    private const val PANEL = 0xFF0E141B.toInt()
    private const val TEXT = 0xFFE7ECF2.toInt()
    private const val TEXT_DIM = 0xFF8A97A6.toInt()
    private const val CYAN = VanGlassTokens.ACCENT_CYAN

    /** Preview pixels per dp, so overlay chrome keeps its real on-device proportions. */
    private const val DENSITY = 1.28f

    /** A representative phone viewport in dp (roughly a Galaxy S-class screen). */
    private const val SCREEN_W_DP = 392
    private const val SCREEN_H_DP = 812

    // Overlay geometry mirrored from OverlayTheme / FloatingOverlayService.
    private const val CHARACTER_DP = OverlayTheme.RESTING_AVATAR_DP
    private const val SHELL_WIDTH_DP = OverlayTheme.COMPACT_WIDTH_DP
    private const val CAPSULE_HEIGHT_DP = OverlayTheme.COMPACT_CAPSULE_HEIGHT_DP
    private const val EXPANDED_WIDTH_DP = OverlayTheme.EXPANDED_WIDTH_DP
    private const val OVERLAP_DP = OverlayTheme.VAN_GLASS_OVERLAP_DP

    /** Deterministic mid-cycle phase so regenerated previews stay comparable. */
    private const val PHASE = 0.18f

    private val fontFamily: String by lazy {
        val available = GraphicsEnvironment.getLocalGraphicsEnvironment().availableFontFamilyNames.toSet()
        listOf("Segoe UI", "Inter", "Helvetica Neue", "Arial").firstOrNull { it in available } ?: Font.SANS_SERIF
    }

    private fun font(size: Int, bold: Boolean = false) =
        Font(fontFamily, if (bold) Font.BOLD else Font.PLAIN, size)

    private fun dp(value: Int): Int = (value * DENSITY).toInt()

    private fun dpf(value: Int): Float = value * DENSITY

    private fun frame(presentation: VanPresentation, reducedMotion: Boolean = false) =
        VanSceneFrame(presentation = presentation, phase = PHASE, blink = 0f, reducedMotion = reducedMotion)

    private fun glass(
        state: VanDurableState,
        panel: Boolean = false,
        liveBlur: Boolean = true,
        budget: VanEffectBudget = VanEffectBudget.FULL,
    ) = VanGlassTokens.forState(state, panel, liveBlur, budget)

    // ------------------------------------------------------------------ floating overlay

    /**
     * Van floating over a host app: frameless rest, condensed compact glass, expanded working
     * surface, and an intentional crescent dock.
     */
    fun floatingOverlaySheet(): BufferedImage {
        val phoneW = dp(SCREEN_W_DP)
        val phoneH = dp(SCREEN_H_DP)
        val gap = 60
        val margin = 68
        val phoneY = 250
        val w = margin * 2 + phoneW * 4 + gap * 3
        val h = phoneY + phoneH + 130
        val image = BufferedImage(w, h, BufferedImage.TYPE_INT_ARGB)
        val g = image.createGraphics()
        AwtVanRenderer.prepare(g)

        g.color = Color(BACKDROP, true)
        g.fillRect(0, 0, w, h)

        g.color = Color(TEXT, true)
        g.font = font(44, bold = true)
        g.drawString("VAN — living aura that condenses into glass", margin, 92)
        g.font = font(20)
        g.color = Color(TEXT_DIM, true)
        listOf(
            "Rest is frameless VAN + refractive field. Glass forms only when interaction is needed, overlapping VAN by ${OVERLAP_DP}dp.",
            "Aura from VanAuraSpecs (no ring). Optical glass from VanGlassTokens (no stroked card). Character from the owner art pack.",
            "The authored van.riv artboard remains EXTERNAL — no state below claims Rive READY.",
        ).forEachIndexed { i, line ->
            g.drawString(line, margin, 134 + i * 30)
        }

        val liveTruth = DegradedMode.healthy()
        val liveCue = VanPresence.cue(liveTruth)

        drawPhone(g, image, margin, phoneY, phoneW, phoneH, "Resting — VAN + aura only") { gg, x, y, pw, ph ->
            drawRestingShell(
                gg,
                x + pw - dp(18) - dp(OverlayTheme.RESTING_HIT_DP),
                y + (ph * 0.32f).toInt(),
                VanDurableState.IDLE,
            )
        }

        drawPhone(g, image, margin + phoneW + gap, phoneY, phoneW, phoneH, "Compact — glass condenses from VAN") { gg, x, y, pw, ph ->
            drawCompactShell(
                gg,
                image,
                x + pw - dp(14) - dp(SHELL_WIDTH_DP),
                y + (ph * 0.34f).toInt(),
                VanDurableState.LISTENING,
            )
        }

        drawPhone(g, image, margin + (phoneW + gap) * 2, phoneY, phoneW, phoneH, "Expanded — working surface from VAN") { gg, x, y, pw, ph ->
            drawExpandedShell(
                gg,
                image,
                x + pw - dp(12) - dp(EXPANDED_WIDTH_DP) - dp(56),
                y + (ph * 0.32f).toInt(),
                VanDurableState.WORKING,
                "Working",
                VanPresence.meshCue(liveTruth),
            )
        }

        drawPhone(g, image, margin + (phoneW + gap) * 3, phoneY, phoneW, phoneH, "Docked — crescent edge slice") { gg, x, y, pw, ph ->
            drawDockedShell(gg, x + pw, y + (ph * 0.34f).toInt(), liveCue.durableState)
        }

        g.color = Color(TEXT_DIM, true)
        g.font = font(18)
        g.drawString(
            "Dock is an 88dp hit / 76dp character edge slice with a crescent field — not a cyan bar, not accidental clipping. " +
                "Degraded truth stays fail-closed until the gateway reports evidence.",
            margin,
            h - 44,
        )

        g.dispose()
        return image
    }

    // ------------------------------------------------------------------ state matrix

    /** All 18 durable states: frameless VAN + field, named in words as well as accent. */
    /**
     * CF-D-06 evidence: every durable state with the flame envelope around the full figure,
     * plus a strip of WORKING across the loop so the rising motion can be judged from stills.
     */
    fun flameAuraSheet(): BufferedImage {
        val states = VanDurableState.entries
        val cols = 6
        val cell = 330
        val box = 250f
        val padX = 40
        val headerH = 150
        val rows = (states.size + cols - 1) / cols
        val stripH = 360
        val w = padX * 2 + cell * cols
        val h = headerH + rows * (cell + 40) + stripH + 40
        val image = BufferedImage(w, h, BufferedImage.TYPE_INT_ARGB)
        val g = image.createGraphics()
        AwtVanRenderer.prepare(g)
        g.paint = GradientPaint(0f, 0f, Color(0xFF080C13.toInt()), 0f, h.toFloat(), Color(0xFF05080D.toInt()))
        g.fillRect(0, 0, w, h)
        g.color = Color(TEXT, true)
        g.font = font(38, bold = true)
        g.drawString("VAN flame aura — CF-D-06 (Goku / Naruto read)", padX, 70)
        g.color = Color(TEXT_DIM, true)
        g.font = font(18)
        g.drawString("Tongues wrap Candidate B's silhouette and rise off it; state colour on the outer flame, white-hot rim, rising embers. Android-native, behind the opaque body.", padX, 104)

        fun paintVan(state: VanDurableState, cx: Float, cy: Float, phase: Float) {
            val spec = VanAuraSpecs.forState(state)
            GlassPainter.drawAura(g, spec, cx, cy, box / 2f, VanEffectBudget.FULL, phase)
            AwtVanRenderer.paintVan(
                g,
                VanVisualState(
                    durableState = state,
                    listening = state == VanDurableState.LISTENING,
                    speaking = state == VanDurableState.SPEAKING,
                    urgency = if (state == VanDurableState.URGENT) 1f else 0f,
                ),
                VanSceneFrame(presentation = VanPresentation.COMMAND_CENTRE, phase = phase),
                cx - box / 2f, cy - box / 2f, box, box,
            )
        }

        states.forEachIndexed { i, state ->
            val cx = padX + (i % cols) * cell + cell / 2f
            val cy = headerH + (i / cols) * (cell + 40) + cell / 2f
            paintVan(state, cx, cy, PHASE)
            g.color = Color(VanGlassTokens.EDGE_CYAN, true)
            g.font = font(18, bold = true)
            centerString(g, state.name.lowercase().replace('_', ' '), cx, cy + box / 2f + 34f)
        }
        val stripY = headerH + rows * (cell + 40) + 20
        g.color = Color(TEXT_DIM, true)
        g.font = font(18)
        g.drawString("WORKING across one loop (phase 0.0 → 0.83)", padX, stripY)
        repeat(6) { k ->
            val cx = padX + k * cell + cell / 2f
            paintVan(VanDurableState.WORKING, cx, stripY + stripH / 2f + 10f, k / 6f)
        }
        g.dispose()
        return image
    }

    fun stateSheet(reducedMotion: Boolean = false): BufferedImage = stateSheet(
        budget = if (reducedMotion) VanEffectBudget.REDUCED_MOTION else VanEffectBudget.FULL,
        reducedMotion = reducedMotion,
    )

    fun stateSheet(budget: VanEffectBudget, reducedMotion: Boolean = !budget.allowMotion): BufferedImage {
        val states = VanDurableState.entries
        val cols = 6
        val rows = (states.size + cols - 1) / cols
        val cellW = 340
        val cellH = 400
        val padX = 56
        val headerH = 190
        val w = padX * 2 + cellW * cols
        val h = headerH + rows * (cellH + 66) + 56

        val image = BufferedImage(w, h, BufferedImage.TYPE_INT_ARGB)
        val g = image.createGraphics()
        AwtVanRenderer.prepare(g)
        g.paint = GradientPaint(0f, 0f, Color(0xFF080C13.toInt()), 0f, h.toFloat(), Color(0xFF05080D.toInt()))
        g.fillRect(0, 0, w, h)

        g.color = Color(TEXT, true)
        g.font = font(40, bold = true)
        val title = when {
            reducedMotion -> "VAN state matrix — reduced motion (designed stillness)"
            budget == VanEffectBudget.LOW -> "VAN state matrix — LOW effect budget"
            budget == VanEffectBudget.STATIC -> "VAN state matrix — STATIC effect budget"
            else -> "VAN state matrix — 18 durable states"
        }
        g.drawString(title, padX, 84)
        g.font = font(19)
        g.color = Color(TEXT_DIM, true)
        g.drawString(
            when {
                reducedMotion ->
                    "Reduced motion holds Zone C still: outer semantic fragments remain, pulse stops. Not the STATIC thermal floor."
                budget == VanEffectBudget.LOW ->
                    "LOW keeps at least one Zone C fragment. Filaments and live blur drop; identity/semantic separation stays."
                budget == VanEffectBudget.STATIC ->
                    "STATIC keeps inner presence plus one or more semantic envelope fragments. State remains readable."
                else ->
                    "Three-zone aura: inner identity, mid interaction, outer semantic envelope. Zone C carries state colour, not the body."
            },
            padX,
            124,
        )
        g.drawString(
            "Each cell has a unique Zone C topology. Warning/error/urgent/approval live in the outer envelope, not as body recolour.",
            padX,
            154,
        )

        states.forEachIndexed { index, state ->
            val col = index % cols
            val row = index / cols
            val x = padX + col * cellW
            val y = headerH + row * (cellH + 66)
            val spec = VanAuraSpecs.forState(state, budget)
            val style = glass(state, budget = budget)

            drawPresenceTile(
                g = g,
                x = x + 24,
                y = y,
                size = cellW - 48,
                state = state,
                spec = spec,
                budget = budget,
                reducedMotion = reducedMotion,
                condenseGlass = style.requiresSolidControls,
                style = style,
            )

            val palette = VanStatusPalette.forState(state)
            val cx = x + cellW / 2
            g.font = font(20, bold = true)
            g.color = Color(palette.accent, true)
            centerString(g, state.name.lowercase().replace('_', ' '), cx, y + cellH - 28)
            g.font = font(13)
            g.color = Color(TEXT_DIM, true)
            centerString(g, clip(VanCaptions.forState(state), 28), cx, y + cellH - 8)
            centerString(
                g,
                "field ${(spec.intensity * 100).toInt()}%  ·  Zone C ${spec.segmentsForBudget(budget).size}  ·  scale ${"%.2f".format(spec.envelopeRadiusScale)}",
                cx,
                y + cellH + 14,
            )
            if (style.requiresSolidControls) {
                g.color = Color(palette.accent, true)
                g.font = font(12, bold = true)
                centerString(g, "SOLID CONTROLS", cx, y + cellH + 32)
            }
        }

        g.dispose()
        return image
    }

    /**
     * 14 finite actions from the Rive contract. Poses stay identity-locked; the action name
     * is the evidence that the contract is complete. Authored action artboards remain EXTERNAL.
     */
    fun actionSheet(): BufferedImage {
        val actions = VanFiniteAction.entries
        val cols = 7
        val rows = (actions.size + cols - 1) / cols
        val cellW = 220
        val cellH = 260
        val padX = 56
        val headerH = 150
        val w = padX * 2 + cellW * cols
        val h = headerH + rows * (cellH + 48) + 48
        val image = BufferedImage(w, h, BufferedImage.TYPE_INT_ARGB)
        val g = image.createGraphics()
        AwtVanRenderer.prepare(g)
        g.paint = GradientPaint(0f, 0f, Color(0xFF080C13.toInt()), 0f, h.toFloat(), Color(0xFF05080D.toInt()))
        g.fillRect(0, 0, w, h)
        g.color = Color(TEXT, true)
        g.font = font(36, bold = true)
        g.drawString("VAN finite actions — contract board", padX, 74)
        g.font = font(18)
        g.color = Color(TEXT_DIM, true)
        g.drawString(
            "Codes 1–14 from RiveContract. OPEN_PANEL / CLOSE_PANEL / PRESENT_CARD condense glass; others remain frameless. .riv action artboards are EXTERNAL.",
            padX,
            110,
        )
        actions.forEachIndexed { index, action ->
            val col = index % cols
            val row = index / cols
            val x = padX + col * cellW
            val y = headerH + row * (cellH + 48)
            val condenses = action == VanFiniteAction.OPEN_PANEL ||
                action == VanFiniteAction.PRESENT_CARD ||
                action == VanFiniteAction.CLOSE_PANEL
            val state = when (action) {
                VanFiniteAction.CELEBRATE -> VanDurableState.SUCCESS
                VanFiniteAction.CAUTION -> VanDurableState.WARNING
                VanFiniteAction.CONFIRM -> VanDurableState.WAITING_FOR_OWNER
                else -> VanDurableState.IDLE
            }
            val spec = VanAuraSpecs.forState(state)
            if (condenses) {
                val chip = RoundRectangle2D.Float((x + 24).toFloat(), (y + cellH - 90).toFloat(), (cellW - 48).toFloat(), 48f, 18f, 18f)
                GlassPainter.fillGlass(g, glass(state), chip, DENSITY)
            }
            GlassPainter.drawAura(g, spec, x + cellW / 2f, y + 110f, 70f, VanEffectBudget.FULL, PHASE)
            drawCharacter(
                g,
                state,
                (x + 30).toFloat(),
                (y + 8).toFloat(),
                (cellW - 60).toFloat(),
                180f,
                VanPresentation.COMMAND_CENTRE,
                reducedMotion = false,
                actionCode = action.code,
            )
            g.color = Color(VanGlassTokens.EDGE_CYAN, true)
            g.font = font(16, bold = true)
            centerString(g, action.name.lowercase().replace('_', ' '), x + cellW / 2, y + cellH - 8)
            g.color = Color(TEXT_DIM, true)
            g.font = font(13)
            centerString(g, "code ${action.code}", x + cellW / 2, y + cellH + 14)
        }
        g.dispose()
        return image
    }

    // ------------------------------------------------------------------ command centre

    /** §14: glass as the top-level material language, panels more opaque, solid critical action. */
    /**
     * P1-VIS-001 / P2-VIS-003 — the Command Centre board, rendered in one place.
     *
     * This used to be a second, older implementation of the board that took no arguments
     * and hardcoded one health snapshot. Both named evidence shots routed through it, so
     * they produced byte-identical files, and a `reconcile` pass then overwrote them
     * afterwards from [VanCommandCentreEvidence] — two renderers for one board, with the
     * second silently correcting the first. It now delegates, so there is one.
     */
    fun commandCentreSheet(degraded: Boolean = false): BufferedImage =
        VanCommandCentreEvidence.render(degraded = degraded)

    fun glassTokenSheet(): BufferedImage {
        val w = 1180
        // Tall enough to clear the five-line budget captions under the §11 ladder tiles.
        val h = 1100
        val image = BufferedImage(w, h, BufferedImage.TYPE_INT_ARGB)
        val g = image.createGraphics()
        AwtVanRenderer.prepare(g)
        g.paint = GradientPaint(0f, 0f, Color(0xFF070B12.toInt()), 0f, h.toFloat(), Color(0xFF04070C.toInt()))
        g.fillRect(0, 0, w, h)

        val margin = 56
        g.color = Color(TEXT, true)
        g.font = font(34, bold = true)
        g.drawString("DIAL Glass tokens & effect ladder", margin, 74)
        g.font = font(17)
        g.color = Color(TEXT_DIM, true)
        g.drawString("Values read directly from VanGlassTokens, VanAuraSpecs and VanEffectBudget — not transcribed. Pair with the aura topology board for Zone C.", margin, 104)

        // §8 tokens.
        g.color = Color(TEXT, true)
        g.font = font(21, bold = true)
        g.drawString("§8 Glass surface tokens", margin, 164)
        g.font = font(16)
        listOf(
            "backgroundAlpha" to VanGlassTokens.BACKGROUND_ALPHA.toString(),
            "blur" to "${VanGlassTokens.BLUR_DP.toInt()}dp",
            "structuralEdge" to VanGlassTokens.STRUCTURAL_EDGE_ALPHA.toString(),
            "specular" to VanGlassTokens.SPECULAR_ALPHA.toString(),
            "grain" to VanGlassTokens.GRAIN_ALPHA.toString(),
            "contamination" to VanGlassTokens.CONTAMINATION_ALPHA.toString(),
            "innerHighlight" to VanGlassTokens.INNER_HIGHLIGHT_ALPHA.toString(),
            "shadowElevation" to "${VanGlassTokens.SHADOW_ELEVATION_DP.toInt()}dp",
        ).forEachIndexed { i, (key, value) ->
            g.color = Color(TEXT_DIM, true)
            g.drawString(key, margin, 200 + i * 28)
            g.color = Color(VanGlassTokens.EDGE_CYAN, true)
            g.drawString(value, margin + 240, 200 + i * 28)
        }

        // Live glass swatches over a busy backdrop, proving §12's opacity rule.
        val swatchX = margin + 420
        g.color = Color(TEXT, true)
        g.font = font(21, bold = true)
        g.drawString("Glass over a noisy backdrop (§12)", swatchX, 164)
        repeat(9) { i ->
            g.color = Color(if (i % 2 == 0) 0xFF1D2B3C.toInt() else 0xFF2A4058.toInt(), true)
            g.fill(RoundRectangle2D.Float((swatchX + i * 74).toFloat(), 188f, 62f, 220f, 12f, 12f))
        }
        listOf(
            VanDurableState.IDLE to "idle",
            VanDurableState.WORKING to "working",
            VanDurableState.WAITING_FOR_OWNER to "approval",
        ).forEachIndexed { i, (state, label) ->
            val style = glass(state)
            val shape = RoundRectangle2D.Float((swatchX + i * 224).toFloat(), 210f, 200f, 176f, 26f, 26f)
            GlassPainter.blurBehind(g, image, shape, (VanGlassTokens.BLUR_DP * DENSITY).toInt())
            GlassPainter.fillGlass(g, style, shape, DENSITY)
            g.color = Color(TEXT, true)
            g.font = font(17, bold = true)
            g.drawString(label, swatchX + i * 224 + 18, 248)
            g.color = Color(TEXT_DIM, true)
            g.font = font(14)
            g.drawString("bg ${(style.backgroundAlpha * 100).toInt()}%", swatchX + i * 224 + 18, 276)
            g.drawString("edge ${(style.structuralEdgeAlpha * 100).toInt()}%", swatchX + i * 224 + 18, 300)
            g.drawString("specular ${(style.specularAlpha * 100).toInt()}%", swatchX + i * 224 + 18, 324)
            if (style.requiresSolidControls) {
                g.color = Color(style.borderColor, true)
                g.font = font(13, bold = true)
                g.drawString("SOLID CONTROLS", swatchX + i * 224 + 18, 356)
            }
        }

        // §11 ladder.
        g.color = Color(TEXT, true)
        g.font = font(21, bold = true)
        g.drawString("§11 Battery / thermal fallback ladder", margin, 480)
        g.font = font(15)
        g.color = Color(TEXT_DIM, true)
        g.drawString(
            "Decoration is surrendered in a fixed order — filaments, bloom, refraction, live blur. Reduced motion is designed stillness, not STATIC.",
            margin,
            508,
        )

        VanEffectBudget.entries.forEachIndexed { i, budget ->
            val x = margin + i * 220
            val y = 540
            val size = 168
            val spec = VanAuraSpecs.forState(VanDurableState.WORKING, budget)
            drawPresenceTile(
                g = g,
                x = x,
                y = y,
                size = size,
                state = VanDurableState.WORKING,
                spec = spec,
                budget = budget,
                reducedMotion = !budget.allowMotion,
                condenseGlass = false,
                style = glass(VanDurableState.WORKING, budget = budget, liveBlur = budget.allowLiveBlur),
            )
            g.color = Color(VanGlassTokens.EDGE_CYAN, true)
            g.font = font(18, bold = true)
            g.drawString(budget.name, x, y + size + 34)
            g.color = Color(TEXT_DIM, true)
            g.font = font(13)
            listOf(
                "filaments ${(budget.filamentScale * 100).toInt()}%",
                "bloom ${(budget.bloomScale * 100).toInt()}%",
                "refraction ${if (budget.allowRefraction) "on" else "off"}",
                "live blur ${if (budget.allowLiveBlur) "on" else "off"}",
                "motion ${if (budget.allowMotion) "on" else "static"}",
            ).forEachIndexed { line, text ->
                g.drawString(text, x, y + size + 58 + line * 22)
            }
        }

        g.color = Color(CYAN, true)
        g.font = font(15, bold = true)
        g.drawString(
            "Critical state indicators are never removed at any budget level (§11) — only decoration is traded away.",
            margin,
            h - 36,
        )

        g.dispose()
        return image
    }

    /**
     * Rev 2.2 authority board: Zone A / B / C labelled, budget ladder, semantic and trade-ready examples.
     */
    fun auraTopologySheet(): BufferedImage {
        val w = 1680
        val h = 1180
        val image = BufferedImage(w, h, BufferedImage.TYPE_INT_ARGB)
        val g = image.createGraphics()
        AwtVanRenderer.prepare(g)
        g.paint = GradientPaint(0f, 0f, Color(0xFF080C13.toInt()), 0f, h.toFloat(), Color(0xFF05080D.toInt()))
        g.fillRect(0, 0, w, h)

        val margin = 56
        g.color = Color(TEXT, true)
        g.font = font(36, bold = true)
        g.drawString("VAN aura topology & semantic ladder", margin, 70)
        g.font = font(17)
        g.color = Color(TEXT_DIM, true)
        g.drawString(
            "Zone A identity cyan stays on the body. Zone B carries activity. Zone C is the outer semantic envelope — sparse, broken, never a ring.",
            margin,
            104,
        )

        val heroX = margin
        val heroY = 140
        val heroSize = 420
        val working = VanAuraSpecs.forState(VanDurableState.WORKING)
        GlassPainter.drawAura(g, working, heroX + heroSize / 2f, heroY + heroSize * 0.48f, heroSize * 0.28f, VanEffectBudget.FULL, PHASE)
        drawCharacter(
            g,
            VanDurableState.WORKING,
            heroX + heroSize * 0.22f,
            heroY + heroSize * 0.18f,
            heroSize * 0.56f,
            heroSize * 0.56f,
            VanPresentation.COMPACT,
        )
        g.color = Color(VanGlassTokens.ACCENT_CYAN, true)
        g.font = font(16, bold = true)
        g.drawString("A  inner presence", heroX + 24, heroY + 36)
        g.drawString("B  mid interaction", heroX + 24, heroY + 62)
        g.color = Color(VanGlassTokens.ACCENT_AMBER, true)
        g.drawString("C  outer semantic envelope", heroX + 24, heroY + 88)
        g.color = Color(TEXT_DIM, true)
        g.font = font(14)
        g.drawString("Working · Zone C at ${"%.2f".format(working.envelopeRadiusScale)}× mid radius", heroX + 24, heroY + heroSize - 12)

        val budgets = listOf(
            VanEffectBudget.FULL to "FULL",
            VanEffectBudget.REDUCED to "REDUCED",
            VanEffectBudget.REDUCED_MOTION to "REDUCED_MOTION",
            VanEffectBudget.LOW to "LOW",
            VanEffectBudget.STATIC to "STATIC",
        )
        budgets.forEachIndexed { i, (budget, label) ->
            val x = heroX + heroSize + 48 + i * 210
            val spec = VanAuraSpecs.forState(VanDurableState.WARNING, budget)
            GlassPainter.drawAura(g, spec, x + 90f, 280f, 62f, budget, PHASE)
            drawCharacter(g, VanDurableState.WARNING, x + 30f, 190f, 120f, 120f, VanPresentation.COMPACT, !budget.allowMotion)
            g.color = Color(TEXT, true)
            g.font = font(16, bold = true)
            centerString(g, label, x + 90, 430)
            g.color = Color(TEXT_DIM, true)
            g.font = font(13)
            centerString(g, "C×${spec.segmentsForBudget(budget).size}", x + 90, 452)
        }

        g.color = Color(TEXT, true)
        g.font = font(20, bold = true)
        g.drawString("Semantic examples — colour lives in Zone C", margin, 520)
        val semanticStates = listOf(
            VanDurableState.WAITING_FOR_OWNER,
            VanDurableState.WARNING,
            VanDurableState.ERROR,
            VanDurableState.URGENT,
            VanDurableState.SUCCESS,
        )
        semanticStates.forEachIndexed { i, state ->
            val x = margin + i * 310
            val spec = VanAuraSpecs.forState(state)
            GlassPainter.drawAura(g, spec, x + 120f, 690f, 78f, VanEffectBudget.FULL, PHASE)
            drawCharacter(g, state, x + 40f, 560f, 160f, 160f, VanPresentation.COMPACT)
            g.color = Color(spec.semanticColor ?: VanGlassTokens.ACCENT_CYAN, true)
            g.font = font(15, bold = true)
            centerString(g, state.name.lowercase().replace('_', ' '), x + 120, 790)
        }

        g.color = Color(TEXT, true)
        g.font = font(20, bold = true)
        g.drawString("Trade-state capability — architecture reserved in Zone C, not a live trading product", margin, 840)
        val trades = listOf(
            "watching" to "watching",
            "setup" to "setup forming",
            "entry" to "entry",
            "in_trade" to "in trade",
            "profit" to "profit",
            "risk" to "risk rising",
            "stop" to "stop / invalid",
            "urgent" to "intervention",
        )
        trades.forEachIndexed { i, (kind, label) ->
            val x = margin + i * 196
            val spec = VanAuraSpecs.tradePreview(kind)
            GlassPainter.drawAura(g, spec, x + 80f, 1000f, 54f, VanEffectBudget.FULL, PHASE)
            drawCharacter(g, VanDurableState.IDLE, x + 20f, 900f, 120f, 120f, VanPresentation.COMPACT)
            g.color = Color(spec.semanticColor ?: VanGlassTokens.ACCENT_CYAN, true)
            g.font = font(13, bold = true)
            centerString(g, label, x + 80, 1128)
        }

        g.dispose()
        return image
    }

    // ------------------------------------------------------------------ shell composition

    /** Frameless rest: VAN and the living field, no glass. Zone C is sized to the hit, not the body. */
    private fun drawRestingShell(
        g: Graphics2D,
        x: Int,
        y: Int,
        state: VanDurableState,
        budget: VanEffectBudget = VanEffectBudget.FULL,
    ) {
        val spec = VanAuraSpecs.forState(state, budget)
        val hit = dp(OverlayTheme.RESTING_HIT_DP)
        val charSize = dp(CHARACTER_DP)
        val charX = x + (hit - charSize) / 2f
        val charY = y + (hit - charSize) / 2f
        GlassPainter.drawAura(
            g,
            spec,
            x + hit / 2f,
            y + hit * 0.48f,
            charSize * 0.50f,
            budget,
            PHASE,
        )
        drawCharacter(
            g,
            state,
            charX,
            charY,
            charSize.toFloat(),
            charSize.toFloat(),
            VanPresentation.COMPACT,
            !budget.allowMotion,
        )
    }

    /**
     * Compact interaction: glass condenses from the aura. VAN overlaps the panel.
     */
    private fun drawCompactShell(
        g: Graphics2D,
        canvas: BufferedImage,
        x: Int,
        y: Int,
        state: VanDurableState,
        budget: VanEffectBudget = VanEffectBudget.FULL,
    ) {
        val style = glass(state, budget = budget)
        val spec = VanAuraSpecs.forState(state, budget)
        val palette = VanStatusPalette.forState(state)
        val shellW = dp(SHELL_WIDTH_DP)
        val capsuleH = dp(CAPSULE_HEIGHT_DP)
        val charSize = dp(CHARACTER_DP)
        // Van's boots break the capsule's top edge; the copy below stays clear of the overlap.
        val capsuleY = y + charSize - dp(OVERLAP_DP)
        val charX = x + dp(4)

        val capsule = RoundRectangle2D.Float(
            x.toFloat(),
            capsuleY.toFloat(),
            shellW.toFloat(),
            capsuleH.toFloat(),
            dpf(VanGlassTokens.CORNER_RADIUS_DP.toInt()),
            dpf(VanGlassTokens.CORNER_RADIUS_DP.toInt()),
        )
        GlassPainter.dropShadow(g, capsule, style, DENSITY)
        if (style.blurDp > 0f) {
            GlassPainter.blurBehind(g, canvas, capsule, (style.blurDp * DENSITY).toInt())
        }
        GlassPainter.fillGlass(g, style, capsule, DENSITY)

        g.color = Color(palette.accent, true)
        g.font = font(12, bold = true)
        g.drawString(clip(VanCaptions.forState(state), 32), x + dp(88), capsuleY + dp(18))

        val actions = OverlayTheme.COMPACT_ACTIONS.chunked(2)
        g.font = font(11, bold = true)
        actions.forEachIndexed { row, labels ->
            var ax = x + dp(88)
            labels.forEach { label ->
                val tw = g.fontMetrics.stringWidth(label) + dp(14)
                g.color = GlassPainter.argb(palette.accent, if (row == 0 && label == labels.first()) 0.26f else 0.14f)
                g.fill(
                    RoundRectangle2D.Float(
                        ax.toFloat(),
                        (capsuleY + dp(32) + row * dp(28)).toFloat(),
                        tw.toFloat(),
                        dp(24).toFloat(),
                        10f,
                        10f,
                    ),
                )
                g.color = Color(0xFFE7ECF2.toInt(), true)
                g.drawString(label, ax + dp(7), capsuleY + dp(49) + row * dp(28))
                ax += tw + dp(6)
            }
        }

        GlassPainter.drawAura(
            g,
            spec,
            charX + charSize * 0.48f,
            y + charSize * 0.48f,
            charSize * 0.48f,
            budget,
            PHASE,
        )
        drawCharacter(
            g,
            state,
            charX.toFloat(),
            y.toFloat(),
            charSize.toFloat(),
            charSize.toFloat(),
            VanPresentation.COMPACT,
            !budget.allowMotion,
        )
    }

    /** Expanded glass grown from VAN; actions live inside the same field, not a separate rail. */
    private fun drawExpandedShell(
        g: Graphics2D,
        canvas: BufferedImage,
        x: Int,
        y: Int,
        state: VanDurableState,
        headline: String,
        detail: String,
    ) {
        val style = glass(state)
        val spec = VanAuraSpecs.forState(state)
        val palette = VanStatusPalette.forState(state)
        val cardW = dp(EXPANDED_WIDTH_DP)
        val charSize = dp(CHARACTER_DP)
        val cardY = y + dp(26)
        val cardH = dp(102)

        val card = RoundRectangle2D.Float(
            x.toFloat(),
            cardY.toFloat(),
            cardW.toFloat(),
            cardH.toFloat(),
            dpf(VanGlassTokens.CORNER_RADIUS_DP.toInt()),
            dpf(VanGlassTokens.CORNER_RADIUS_DP.toInt()),
        )
        GlassPainter.dropShadow(g, card, style, DENSITY)
        if (style.blurDp > 0f) {
            GlassPainter.blurBehind(g, canvas, card, (style.blurDp * DENSITY).toInt())
        }
        GlassPainter.fillGlass(g, style, card, DENSITY)

        // Van hangs off the card's left edge, so the copy only has to clear his overlap.
        val charX = x - (charSize * 0.44f).toInt()
        val textX = x + dp(60)
        g.color = Color(TEXT, true)
        g.font = font(19, bold = true)
        g.drawString("Van", textX, cardY + dp(22))
        g.color = Color(palette.accent, true)
        g.font = font(14, bold = true)
        g.drawString(headline, textX, cardY + dp(41))
        g.color = Color(0xFFB6C2D0.toInt(), true)
        g.font = font(11)
        g.drawString(clip(VanCaptions.forState(state), 28), textX, cardY + dp(58))
        g.color = Color(TEXT_DIM, true)
        g.font = font(11)
        g.drawString(clip(detail, 30), textX, cardY + dp(74))

        // §14/§6: an approval-class state gets a solid control, not a translucent one.
        if (style.requiresSolidControls) {
            val btn = RoundRectangle2D.Float(
                textX.toFloat(),
                (cardY + dp(80)).toFloat(),
                dp(84).toFloat(),
                dp(22).toFloat(),
                dpf(9),
                dpf(9),
            )
            g.color = Color(style.borderColor, true)
            g.fill(btn)
            g.color = Color(0xFF10151F.toInt(), true)
            g.font = font(12, bold = true)
            centerString(g, "Approve", textX + dp(42), cardY + dp(95))
        } else {
            g.font = font(11, bold = true)
            var ax = textX
            OverlayTheme.COMPACT_ACTIONS.forEach { label ->
                val tw = g.fontMetrics.stringWidth(label) + dp(12)
                g.color = GlassPainter.argb(palette.accent, 0.16f)
                g.fill(RoundRectangle2D.Float(ax.toFloat(), (cardY + dp(82)).toFloat(), tw.toFloat(), dp(18).toFloat(), 8f, 8f))
                g.color = Color(0xFFE7ECF2.toInt(), true)
                g.drawString(label, ax + dp(6), cardY + dp(95))
                ax += tw + dp(5)
            }
        }

        GlassPainter.drawAura(
            g,
            spec,
            (charX + charSize / 2).toFloat(),
            (y + charSize * 0.48f),
            charSize * 0.48f,
            phase = PHASE,
        )
        drawCharacter(
            g,
            state,
            charX.toFloat(),
            y.toFloat(),
            charSize.toFloat(),
            charSize.toFloat(),
            VanPresentation.EXPANDED,
        )
    }

    /**
     * Intentional edge dock: 88dp hit, 76dp character as a crescent/edge slice.
     * Face and visor stay on-screen; the field compresses into a crescent, not a cyan bar.
     */
    private fun drawDockedShell(
        g: Graphics2D,
        screenRight: Int,
        y: Int,
        state: VanDurableState,
    ) {
        val spec = VanAuraSpecs.forState(state)
        val hit = dp(OverlayTheme.DOCK_HIT_DP)
        val charSize = dp(OverlayTheme.DOCK_CHARACTER_DP)
        val sliceW = dp(OverlayTheme.DOCK_WIDTH_DP)
        val boxX = screenRight - sliceW
        val boxY = y

        GlassPainter.drawCrescentAura(
            g,
            spec,
            boxX.toFloat(),
            boxY.toFloat(),
            sliceW.toFloat(),
            hit.toFloat(),
        )
        drawCharacter(
            g,
            state,
            (boxX + (sliceW - charSize) / 2).toFloat(),
            (boxY - dp(4)).toFloat(),
            charSize.toFloat(),
            charSize.toFloat(),
            VanPresentation.COMPACT,
        )
    }

    /** Frameless VAN + field. Approval-class states optionally condense a small glass chip. */
    private fun drawPresenceTile(
        g: Graphics2D,
        x: Int,
        y: Int,
        size: Int,
        state: VanDurableState,
        spec: VanAuraSpec,
        budget: VanEffectBudget,
        reducedMotion: Boolean,
        condenseGlass: Boolean,
        style: VanGlassStyle,
    ) {
        if (condenseGlass) {
            val chipH = size * 0.16f
            val chipY = y + size - chipH * 0.42f
            val chip = RoundRectangle2D.Float(
                x + size * 0.18f,
                chipY,
                size * 0.64f,
                chipH,
                size * 0.10f,
                size * 0.10f,
            )
            GlassPainter.dropShadow(g, chip, style, DENSITY)
            GlassPainter.fillGlass(g, style, chip, DENSITY)
        }
        GlassPainter.drawAura(
            g,
            spec,
            x + size / 2f,
            y + size * 0.48f,
            size * 0.34f,
            budget,
            PHASE,
        )
        val inset = size * 0.18f
        drawCharacter(
            g,
            state,
            x + inset,
            y + inset,
            size - inset * 2,
            size - inset * 2,
            VanPresentation.COMPACT,
            reducedMotion,
        )
    }

    /**
     * Draws the fail-closed interim [VanScene] Canvas character.
     * Rejected owner-art bitmap poses are retired and are never selected by the app or evidence renderer.
     */
    private fun drawCharacter(
        g: Graphics2D,
        state: VanDurableState,
        x: Float,
        y: Float,
        w: Float,
        h: Float,
        presentation: VanPresentation,
        reducedMotion: Boolean = false,
        actionCode: Int = 0,
    ) {
        AwtVanRenderer.paintVan(
            g,
            VanVisualState(
                durableState = state,
                listening = state == VanDurableState.LISTENING,
                speaking = state == VanDurableState.SPEAKING,
                actionCode = actionCode,
                urgency = if (state == VanDurableState.URGENT) 1f else 0f,
            ),
            frame(presentation, reducedMotion),
            x,
            y,
            w,
            h,
        )
    }

    // ------------------------------------------------------------------ chrome helpers

    private fun drawGlyph(g: Graphics2D, kind: String, cx: Int, cy: Int, r: Float) {
        when (kind) {
            "mic" -> {
                g.fill(RoundRectangle2D.Float(cx - r * 0.42f, cy - r, r * 0.84f, r * 1.3f, r * 0.8f, r * 0.8f))
                g.draw(Line2D.Float(cx.toFloat(), cy + r * 0.45f, cx.toFloat(), cy + r))
                g.draw(Line2D.Float(cx - r * 0.6f, cy + r, cx + r * 0.6f, cy + r))
            }
            "grid" -> {
                val s = r * 0.7f
                listOf(-1 to -1, 1 to -1, -1 to 1, 1 to 1).forEach { (sx, sy) ->
                    g.fill(
                        RoundRectangle2D.Float(
                            cx + sx * s - s * 0.44f,
                            cy + sy * s - s * 0.44f,
                            s * 0.88f,
                            s * 0.88f,
                            2f,
                            2f,
                        ),
                    )
                }
            }
            "close" -> {
                g.draw(Line2D.Float(cx - r * 0.7f, cy - r * 0.7f, cx + r * 0.7f, cy + r * 0.7f))
                g.draw(Line2D.Float(cx + r * 0.7f, cy - r * 0.7f, cx - r * 0.7f, cy + r * 0.7f))
            }
            else -> {
                g.draw(RoundRectangle2D.Float(cx - r, cy - r * 0.85f, r * 2f, r * 1.45f, r * 0.7f, r * 0.7f))
                g.draw(Line2D.Float(cx - r * 0.3f, cy + r * 0.6f, cx - r * 0.75f, cy + r * 1.15f))
            }
        }
    }

    /** Mock host app behind the overlay, so "floating above other apps" is visible, not implied. */
    private fun drawPhone(
        g: Graphics2D,
        canvas: BufferedImage,
        x: Int,
        y: Int,
        w: Int,
        h: Int,
        caption: String,
        overlay: (Graphics2D, Int, Int, Int, Int) -> Unit,
    ) {
        val body = RoundRectangle2D.Float(x.toFloat(), y.toFloat(), w.toFloat(), h.toFloat(), 46f, 46f)
        g.color = Color(0xFF1B2129.toInt(), true)
        g.fill(RoundRectangle2D.Float(x - 8f, y - 8f, w + 16f, h + 16f, 54f, 54f))
        g.paint = GradientPaint(
            x.toFloat(),
            y.toFloat(),
            Color(0xFF16212B.toInt(), true),
            x.toFloat(),
            (y + h).toFloat(),
            Color(0xFF0B1016.toInt(), true),
        )
        g.fill(body)

        val previousClip = g.clip
        g.clip(body)

        g.color = Color(0xFF9FB0C0.toInt(), true)
        g.font = font(15, bold = true)
        g.drawString("9:41", x + 26, y + 36)
        g.fill(RoundRectangle2D.Float(x + w - 62f, y + 22f, 24f, 12f, 3f, 3f))
        g.fill(Ellipse2D.Float(x + w - 92f, y + 22f, 12f, 12f))

        g.color = Color(PANEL, true)
        g.fill(RoundRectangle2D.Float(x + 22f, y + 62f, w - 44f, 96f, 18f, 18f))
        g.color = Color(0xFF29394A.toInt(), true)
        g.fill(RoundRectangle2D.Float(x + 40f, y + 86f, w * 0.42f, 14f, 7f, 7f))
        g.fill(RoundRectangle2D.Float(x + 40f, y + 112f, w * 0.62f, 12f, 6f, 6f))
        repeat(4) { row ->
            repeat(4) { col ->
                g.color = Color(0xFF1A2431.toInt(), true)
                g.fill(
                    RoundRectangle2D.Float(
                        x + 34f + col * ((w - 68f) / 4f),
                        y + 208f + row * 112f,
                        (w - 68f) / 4f - 22f,
                        64f,
                        16f,
                        16f,
                    ),
                )
            }
        }
        g.color = Color(PANEL, true)
        g.fill(RoundRectangle2D.Float(x + 22f, y + h - 96f, w - 44f, 74f, 22f, 22f))

        // Unclip before the overlay: the glass blur samples the canvas, which needs the app
        // pixels already committed, and the shell may legitimately overhang the screen edge.
        g.clip = previousClip
        val bodyClip = g.clip
        g.clip(body)
        overlay(g, x, y, w, h)
        g.clip = bodyClip

        g.color = GlassPainter.argb(CYAN, 0.20f)
        g.stroke = BasicStroke(2f)
        g.draw(body)

        g.color = Color(TEXT, true)
        g.font = font(21, bold = true)
        centerString(g, caption, x + w / 2, y + h + 52)
    }

    private fun centerString(g: Graphics2D, text: String, cx: Int, baselineY: Int) {
        g.drawString(text, cx - g.fontMetrics.stringWidth(text) / 2, baselineY)
    }

    private fun centerString(g: Graphics2D, text: String, cx: Float, baselineY: Float) {
        g.drawString(text, cx - g.fontMetrics.stringWidth(text) / 2f, baselineY)
    }

    private fun clip(text: String, max: Int): String =
        if (text.length <= max) text else text.take(max - 1) + "…"
}
