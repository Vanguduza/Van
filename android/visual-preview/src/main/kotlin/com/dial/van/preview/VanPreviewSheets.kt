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
 * DIAL Glass shell (§3/§8), [VanAuraSpecs] for the electrical aura (§7), [OwnerArt] for the
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
    private const val SHELL_WIDTH_DP = 132
    private const val CAPSULE_HEIGHT_DP = 62
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
                x + pw - dp(18) - dp(CHARACTER_DP),
                y + (ph * 0.34f).toInt(),
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
    fun stateSheet(reducedMotion: Boolean = false): BufferedImage = stateSheet(
        budget = if (reducedMotion) VanEffectBudget.REDUCED_MOTION else VanEffectBudget.FULL,
        reducedMotion = reducedMotion,
    )

    fun stateSheet(budget: VanEffectBudget, reducedMotion: Boolean = !budget.allowMotion): BufferedImage {
        val states = VanDurableState.entries
        val cols = 6
        val rows = (states.size + cols - 1) / cols
        val cellW = 270
        val cellH = 300
        val padX = 64
        val headerH = 180
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
                    "Reduced motion holds a composed still field: filaments and broken arcs remain, pulse stops. Not the STATIC thermal floor."
                budget == VanEffectBudget.LOW ->
                    "LOW surrenders refraction and live blur; the deformable field and state copy stay fully readable."
                budget == VanEffectBudget.STATIC ->
                    "STATIC is the thermal floor: still field, one filament, state indicators never removed."
                else ->
                    "Frameless presence — no enclosing glass card. Aura intensity from VanAuraSpecs; each caption is shipped state copy."
            },
            padX,
            124,
        )
        g.drawString(
            "No state relies on colour alone: each cell carries a distinct field, a named caption, and the visor/orb treatment.",
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
                "field ${(spec.intensity * 100).toInt()}%  ·  filaments ${spec.filamentCount}  ·  glass ${(style.backgroundAlpha * 100).toInt()}%",
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
            drawPresenceTile(
                g = g,
                x = x + 16,
                y = y,
                size = cellW - 32,
                state = state,
                spec = spec,
                budget = VanEffectBudget.FULL,
                reducedMotion = false,
                condenseGlass = condenses,
                style = glass(state),
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
    fun commandCentreSheet(): BufferedImage {
        val w = 1180
        val h = 1420
        val image = BufferedImage(w, h, BufferedImage.TYPE_INT_ARGB)
        val g = image.createGraphics()
        AwtVanRenderer.prepare(g)

        g.paint = GradientPaint(
            0f,
            0f,
            Color(0xFF060A14.toInt()),
            0f,
            h.toFloat(),
            Color(0xFF04070F.toInt()),
        )
        g.fillRect(0, 0, w, h)
        // Faint field so the glass has something to sample, as it would over a real app.
        g.color = Color(0x140096FF, true)
        g.fill(Ellipse2D.Float(-160f, 120f, 900f, 900f))
        g.color = Color(0x1000E5FF, true)
        g.fill(Ellipse2D.Float(w - 520f, h - 760f, 820f, 820f))

        val margin = 56
        val cue = VanPresence.cue(DegradedMode.healthy())
        val style = glass(cue.durableState, panel = true, liveBlur = false)
        val palette = VanStatusPalette.forState(cue.durableState)

        g.color = Color(TEXT, true)
        g.font = font(34, bold = true)
        g.drawString("Van Command Centre", margin, 74)
        g.font = font(17)
        g.color = Color(TEXT_DIM, true)
        g.drawString(
            "Hero VAN, then state/mission, attention, decisions, tasks, projects, connections. Approvals are solid, never glass.",
            margin,
            104,
        )

        // Hero panel.
        val heroH = 240
        val hero = RoundRectangle2D.Float(
            margin.toFloat(),
            130f,
            (w - margin * 2).toFloat(),
            heroH.toFloat(),
            dpf(VanGlassTokens.CORNER_RADIUS_DP.toInt()),
            dpf(VanGlassTokens.CORNER_RADIUS_DP.toInt()),
        )
        GlassPainter.blurBehind(g, image, hero, (VanGlassTokens.BLUR_DP * DENSITY).toInt())
        GlassPainter.fillGlass(g, style, hero, DENSITY)

        val avatarBox = 186f
        val spec = VanAuraSpecs.forState(cue.durableState)
        GlassPainter.drawAura(
            g,
            spec,
            margin + 24 + avatarBox / 2f,
            130f + heroH / 2f,
            avatarBox * 0.44f,
            phase = PHASE,
        )
        drawCharacter(
            g,
            cue.durableState,
            margin + 24f,
            130f + (heroH - avatarBox) / 2f,
            avatarBox,
            avatarBox,
            VanPresentation.COMMAND_CENTRE,
        )

        val textX = margin + 24 + avatarBox.toInt() + 34
        g.color = Color(TEXT, true)
        g.font = font(30, bold = true)
        g.drawString("Van", textX, 196)
        g.color = Color(palette.accent, true)
        g.font = font(19, bold = true)
        g.drawString(cue.headline, textX, 228)
        g.color = Color(0xFFD5DEE8.toInt(), true)
        g.font = font(16)
        g.drawString(VanCaptions.forState(cue.durableState), textX, 256)
        g.color = Color(TEXT_DIM, true)
        g.font = font(14)
        g.drawString(cue.detail, textX, 286)
        g.drawString(VanPresence.meshCue(DegradedMode.healthy()), textX, 310)

        // Structured section panels.
        val live = DegradedMode.healthy()
        val attentionBody = if (live.active) live.reason else "Nothing waiting on you"
        val sections = listOf(
            Triple("State / Mission", VanCaptions.forState(cue.durableState), false),
            Triple("Attention", attentionBody, live.active),
            Triple("Decisions", "No pending decisions", false),
            Triple("Tasks", "0 queued commands", false),
            Triple("Projects", "Synced from registries/projects.json", false),
            Triple("Connections", "Hermes profile: van · " + VanPresence.meshCue(live), false),
        )
        val colW = (w - margin * 2 - 24) / 2
        var top = 130 + heroH + 26
        sections.forEachIndexed { index, (title, summary, alert) ->
            val col = index % 2
            val row = index / 2
            val px = margin + col * (colW + 24)
            val py = top + row * 172
            val panelStyle = if (alert) {
                style.copy(
                    borderColor = VanGlassTokens.ACCENT_AMBER,
                    borderAlpha = 0.42f,
                    backgroundAlpha = (style.backgroundAlpha + 0.06f).coerceAtMost(0.97f),
                )
            } else {
                style
            }
            val shape = RoundRectangle2D.Float(px.toFloat(), py.toFloat(), colW.toFloat(), 148f, 28f, 28f)
            GlassPainter.blurBehind(g, image, shape, (VanGlassTokens.BLUR_DP * DENSITY).toInt())
            GlassPainter.fillGlass(g, panelStyle, shape, DENSITY)

            g.color = Color(TEXT, true)
            g.font = font(20, bold = true)
            g.drawString(title, px + 22, py + 40)
            g.color = if (alert) Color(VanGlassTokens.ACCENT_AMBER, true) else Color(0xFFD5DEE8.toInt(), true)
            g.font = font(14)
            g.drawString(clip(summary, 52), px + 22, py + 78)
        }
        top += 3 * 172 + 8

        // Non-critical control: translucent glass.
        val soft = RoundRectangle2D.Float(margin.toFloat(), top.toFloat(), (w - margin * 2).toFloat(), 58f, 26f, 26f)
        g.color = GlassPainter.argb(CYAN, 0.18f)
        g.fill(soft)
        g.color = GlassPainter.argb(VanGlassTokens.EDGE_CYAN, 0.35f)
        g.stroke = BasicStroke(1.4f)
        g.draw(soft)
        g.color = Color(VanGlassTokens.EDGE_CYAN, true)
        g.font = font(18, bold = true)
        centerString(g, "Start floating Van", w / 2, top + 37)

        // §14 critical action: solid, not translucent.
        val solid = RoundRectangle2D.Float(margin.toFloat(), (top + 76).toFloat(), (w - margin * 2).toFloat(), 62f, 26f, 26f)
        g.color = Color(VanGlassTokens.ACCENT_AMBER, true)
        g.fill(solid)
        g.color = Color(0xFF10151F.toInt(), true)
        g.font = font(19, bold = true)
        centerString(g, "Approve A4 action (biometric)", w / 2, top + 116)

        g.color = Color(TEXT_DIM, true)
        g.font = font(15)
        g.drawString(
            "Critical actions switch from translucent to solid controls (§14) so an approval can never be mis-tapped through glass.",
            margin,
            top + 172,
        )
        g.color = Color(CYAN, true)
        g.font = font(15, bold = true)
        g.drawString(
            "Character is interim owner art / Canvas — authored .riv and owner visual sign-off remain EXTERNAL.",
            margin,
            top + 198,
        )

        g.dispose()
        return image
    }

    // ------------------------------------------------------------------ token reference

    /**
     * Token and fallback reference sheet: the §8 glass tokens, the §7 aura layers and the §11
     * battery/thermal ladder, rendered from the shipped constants so the numbers can be checked.
     */
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
        g.drawString("Values read directly from VanGlassTokens, VanAuraSpecs and VanEffectBudget — not transcribed.", margin, 104)

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

    // ------------------------------------------------------------------ shell composition

    /** Frameless rest: VAN and the living field, no glass. */
    private fun drawRestingShell(
        g: Graphics2D,
        x: Int,
        y: Int,
        state: VanDurableState,
        budget: VanEffectBudget = VanEffectBudget.FULL,
    ) {
        val spec = VanAuraSpecs.forState(state, budget)
        val charSize = dp(CHARACTER_DP)
        GlassPainter.drawAura(
            g,
            spec,
            (x + charSize / 2).toFloat(),
            y + charSize * 0.48f,
            charSize * 0.42f,
            budget,
            PHASE,
        )
        drawCharacter(
            g,
            state,
            x.toFloat(),
            y.toFloat(),
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

        // Status copy, then 1–3 quick actions (§5).
        g.color = Color(palette.accent, true)
        g.font = font(12, bold = true)
        centerString(g, clip(VanCaptions.forState(state), 22), x + shellW / 2, capsuleY + dp(20))

        val actionR = dp(15)
        val actions = listOf("mic", "chat", "grid")
        val totalW = actions.size * actionR * 2 + (actions.size - 1) * dp(10)
        actions.forEachIndexed { i, kind ->
            val ax = x + (shellW - totalW) / 2 + i * (actionR * 2 + dp(10))
            val ay = capsuleY + dp(28)
            g.color = GlassPainter.argb(palette.accent, if (i == 0) 0.26f else 0.12f)
            g.fill(RoundRectangle2D.Float(ax.toFloat(), ay.toFloat(), (actionR * 2).toFloat(), (actionR * 2).toFloat(), 10f, 10f))
            g.color = Color(if (i == 0) palette.accent else 0xFFE7ECF2.toInt(), true)
            g.stroke = BasicStroke(2.2f)
            drawGlyph(g, kind, ax + actionR, ay + actionR, actionR * 0.5f)
        }

        // Aura between glass and character (§2 hierarchy), then Van on top.
        GlassPainter.drawAura(
            g,
            spec,
            (x + shellW / 2).toFloat(),
            (y + charSize * 0.48f),
            charSize * 0.40f,
            budget,
            PHASE,
        )
        drawCharacter(
            g,
            state,
            (x + (shellW - charSize) / 2).toFloat(),
            y.toFloat(),
            charSize.toFloat(),
            charSize.toFloat(),
            VanPresentation.COMPACT,
            !budget.allowMotion,
        )
    }

    /** Expanded glass card plus the owner design sheet's right-edge action rail. */
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
        }

        // Aura, then Van breaking the card's left edge and rising above its top.
        GlassPainter.drawAura(
            g,
            spec,
            (charX + charSize / 2).toFloat(),
            (y + charSize * 0.48f),
            charSize * 0.40f,
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

        // Action rail.
        val railX = x + cardW + dp(8)
        val railW = dp(48)
        val railH = dp(4) + 4 * dp(38)
        val rail = RoundRectangle2D.Float(
            railX.toFloat(),
            cardY.toFloat(),
            railW.toFloat(),
            railH.toFloat(),
            dpf(VanGlassTokens.CORNER_RADIUS_DP.toInt()),
            dpf(VanGlassTokens.CORNER_RADIUS_DP.toInt()),
        )
        if (style.blurDp > 0f) {
            GlassPainter.blurBehind(g, canvas, rail, (style.blurDp * DENSITY).toInt())
        }
        GlassPainter.fillGlass(g, style, rail, DENSITY)
        listOf("chat", "grid", "mic", "close").forEachIndexed { i, kind ->
            val r = dp(14)
            val ax = railX + (railW - r * 2) / 2
            val ay = cardY + dp(6) + i * dp(38)
            g.color = GlassPainter.argb(palette.accent, if (i == 0) 0.26f else 0.12f)
            g.fill(RoundRectangle2D.Float(ax.toFloat(), ay.toFloat(), (r * 2).toFloat(), (r * 2).toFloat(), 9f, 9f))
            g.color = Color(if (i == 0) palette.accent else 0xFFE7ECF2.toInt(), true)
            g.stroke = BasicStroke(2.1f)
            drawGlyph(g, kind, ax + r, ay + r, r * 0.5f)
        }
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
        val sliceW = dp(52)
        val boxX = screenRight - sliceW
        val boxY = y + (dp(CHARACTER_DP) - hit) / 2

        val previous = g.clip
        val crescent = java.awt.geom.RoundRectangle2D.Float(
            boxX.toFloat(),
            boxY.toFloat(),
            sliceW.toFloat(),
            hit.toFloat(),
            sliceW * 0.9f,
            sliceW * 0.9f,
        )
        g.clip = crescent
        GlassPainter.drawAura(
            g,
            spec,
            boxX + charSize * 0.28f,
            boxY + hit * 0.48f,
            charSize * 0.42f,
            phase = PHASE,
        )
        drawCharacter(
            g,
            state,
            (boxX - dp(18)).toFloat(),
            (boxY + (hit - charSize) / 2).toFloat(),
            charSize.toFloat(),
            charSize.toFloat(),
            VanPresentation.COMPACT,
        )
        g.clip = previous
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
            val chipH = size * 0.28f
            val chipY = y + size - chipH * 0.55f
            val chip = RoundRectangle2D.Float(
                x + size * 0.08f,
                chipY,
                size * 0.84f,
                chipH,
                size * 0.12f,
                size * 0.12f,
            )
            GlassPainter.dropShadow(g, chip, style, DENSITY)
            GlassPainter.fillGlass(g, style, chip, DENSITY)
        }
        GlassPainter.drawAura(
            g,
            spec,
            x + size / 2f,
            y + size * 0.48f,
            size * 0.38f,
            budget,
            PHASE,
        )
        val inset = size * 0.06f
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
     * Draws Van himself: owner art when the pose is packaged, otherwise the [VanScene] Canvas
     * character. Both paths are what the app does, in the app's own order of preference.
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
    ) {
        if (OwnerArt.paint(g, state, x, y, w, h)) return
        AwtVanRenderer.paint(
            g,
            VanScene.build(
                VanVisualState(
                    durableState = state,
                    listening = state == VanDurableState.LISTENING,
                    speaking = state == VanDurableState.SPEAKING,
                ),
                frame(presentation, reducedMotion),
            ),
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
