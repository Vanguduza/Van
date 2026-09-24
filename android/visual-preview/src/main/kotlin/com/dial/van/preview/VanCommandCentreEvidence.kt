package com.dial.van.preview

import com.dial.van.degraded.DegradedMode
import com.dial.van.degraded.SubsystemStatus
import com.dial.van.visual.VanAuraSpecs
import com.dial.van.visual.VanCaptions
import com.dial.van.visual.VanDurableState
import com.dial.van.visual.VanEffectBudget
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
import java.awt.geom.Ellipse2D
import java.awt.geom.RoundRectangle2D
import java.awt.image.BufferedImage
import java.io.File
import java.security.MessageDigest
import javax.imageio.ImageIO

/**
 * Produces state-truthful Command Centre evidence without weakening VAN's fail-closed runtime.
 *
 * [DegradedMode.healthy] deliberately remains degraded while Google mesh evidence is absent. The
 * IDLE image here is therefore an explicitly labelled nominal *evidence scenario*, not a claim
 * that the live Google integration is READY. The degraded image uses the real current fail-closed
 * subsystem truth.
 *
 * P2-VIS-003 — Rev 2.3 routed both named Command Centre shots through a renderer that took no
 * arguments, so they produced byte-identical files, and a `reconcile` pass then overwrote the two
 * PNGs afterwards from here and patched the manifest hashes with a regular expression. That pass
 * is gone: `VanEvidenceMatrix.renderShot` calls [render] directly, so the right file is written
 * the first time and there is nothing left to reconcile. A build step whose job is to correct an
 * earlier build step is a bug with a schedule.
 */
object VanCommandCentreEvidence {

    private const val PHASE = 0.18f
    private const val TEXT = 0xFFE7ECF2.toInt()
    private const val TEXT_DIM = 0xFF8A97A6.toInt()
    private const val CYAN = VanGlassTokens.ACCENT_CYAN

    fun render(degraded: Boolean): BufferedImage {
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
        g.color = Color(0x140096FF, true)
        g.fill(Ellipse2D.Float(-160f, 120f, 900f, 900f))
        g.color = Color(0x1000E5FF, true)
        g.fill(Ellipse2D.Float(w - 520f, h - 760f, 820f, 820f))

        val live = if (degraded) DegradedMode.healthy() else nominalEvidenceMode()
        val cue = VanPresence.cue(live)
        val style = VanGlassTokens.forState(
            cue.durableState,
            panel = true,
            liveBlurAvailable = false,
            budget = VanEffectBudget.FULL,
        )
        val palette = VanStatusPalette.forState(cue.durableState)
        val margin = 56

        g.color = Color(TEXT, true)
        g.font = font(34, bold = true)
        g.drawString("Van Command Centre", margin, 74)
        g.font = font(17)
        g.color = Color(TEXT_DIM, true)
        g.drawString(
            if (degraded) {
                "Live fail-closed evidence — unresolved subsystem truth remains visible and actionable."
            } else {
                "Nominal-state evidence scenario — visual reference only; this is not a live Google readiness claim."
            },
            margin,
            104,
        )

        val heroH = 240
        val hero = RoundRectangle2D.Float(
            margin.toFloat(),
            130f,
            (w - margin * 2).toFloat(),
            heroH.toFloat(),
            28f,
            28f,
        )
        GlassPainter.blurBehind(g, image, hero, VanGlassTokens.BLUR_DP.toInt())
        GlassPainter.fillGlass(g, style, hero, 1f)

        val avatarBox = 186f
        val spec = VanAuraSpecs.forState(cue.durableState)
        GlassPainter.drawAura(
            g,
            spec,
            margin + 24 + avatarBox / 2f,
            130f + heroH / 2f,
            avatarBox * 0.44f,
            VanEffectBudget.FULL,
            PHASE,
        )
        paintCharacter(
            g,
            cue.durableState,
            margin + 24f,
            130f + (heroH - avatarBox) / 2f,
            avatarBox,
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
        g.drawString(clip(cue.detail, 78), textX, 286)
        g.drawString(
            if (degraded) VanPresence.meshCue(live) else "Google mesh: nominal evidence scenario only",
            textX,
            310,
        )

        val attentionBody = if (live.active) live.reason else "Nothing waiting on you"
        val connectionBody = if (degraded) {
            "Hermes profile: van · ${VanPresence.meshCue(live)}"
        } else {
            "Hermes profile: van · nominal evidence scenario"
        }
        val sections = listOf(
            Triple("State / Mission", VanCaptions.forState(cue.durableState), false),
            Triple("Attention", attentionBody, live.active),
            Triple("Decisions", "No pending decisions", false),
            Triple("Tasks", "0 queued commands", false),
            Triple("Projects", "van · dial · dde · gtr · goat · aeci", false),
            Triple("Connections", connectionBody, false),
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
            GlassPainter.blurBehind(g, image, shape, VanGlassTokens.BLUR_DP.toInt())
            GlassPainter.fillGlass(g, panelStyle, shape, 1f)

            g.color = Color(TEXT, true)
            g.font = font(20, bold = true)
            g.drawString(title, px + 22, py + 40)
            g.color = if (alert) Color(VanGlassTokens.ACCENT_AMBER, true) else Color(0xFFD5DEE8.toInt(), true)
            g.font = font(14)
            g.drawString(clip(summary, 58), px + 22, py + 78)
        }
        top += 3 * 172 + 8

        val soft = RoundRectangle2D.Float(margin.toFloat(), top.toFloat(), (w - margin * 2).toFloat(), 58f, 26f, 26f)
        g.color = GlassPainter.argb(CYAN, 0.18f)
        g.fill(soft)
        g.color = GlassPainter.argb(VanGlassTokens.EDGE_CYAN, 0.35f)
        g.stroke = BasicStroke(1.4f)
        g.draw(soft)
        g.color = Color(VanGlassTokens.EDGE_CYAN, true)
        g.font = font(18, bold = true)
        centerString(g, "Start floating Van", w / 2, top + 37)

        val solid = RoundRectangle2D.Float(margin.toFloat(), (top + 76).toFloat(), (w - margin * 2).toFloat(), 62f, 26f, 26f)
        g.color = Color(VanGlassTokens.ACCENT_AMBER, true)
        g.fill(solid)
        g.color = Color(0xFF10151F.toInt(), true)
        g.font = font(19, bold = true)
        centerString(g, "Approve A4 action (biometric)", w / 2, top + 116)

        g.color = Color(TEXT_DIM, true)
        g.font = font(15)
        g.drawString(
            "Critical actions are solid so an approval can never be mis-tapped through glass.",
            margin,
            top + 172,
        )
        g.color = Color(CYAN, true)
        g.font = font(15, bold = true)
        g.drawString(
            if (degraded) {
                "This frame reflects current fail-closed preview truth; unresolved Google readiness is not hidden."
            } else {
                "Nominal evidence frame only — external authentication/readiness gates are deliberately not asserted here."
            },
            margin,
            top + 198,
        )

        g.dispose()
        return image
    }

    private fun nominalEvidenceMode(): DegradedMode = DegradedMode(
        active = false,
        reason = "Nominal evidence scenario — not live readiness",
        subsystems = DegradedMode.defaultSubsystems().map { subsystem ->
            subsystem.copy(
                status = SubsystemStatus.WORKING,
                detail = if (subsystem.id == "google") {
                    "Nominal evidence scenario only; live gateway readiness remains external"
                } else {
                    subsystem.detail
                },
            )
        },
        updatedAtEpochMs = 0L,
    )

    private fun paintCharacter(g: Graphics2D, state: VanDurableState, x: Float, y: Float, size: Float) {
        AwtVanRenderer.paint(
            g,
            VanScene.build(
                VanVisualState(durableState = state),
                VanSceneFrame(presentation = VanPresentation.COMMAND_CENTRE, phase = PHASE),
            ),
            x,
            y,
            size,
            size,
        )
    }

    private fun font(size: Int, bold: Boolean = false) = Font(
        Font.SANS_SERIF,
        if (bold) Font.BOLD else Font.PLAIN,
        size,
    )

    private fun centerString(g: Graphics2D, text: String, centerX: Int, baselineY: Int) {
        g.drawString(text, centerX - g.fontMetrics.stringWidth(text) / 2f, baselineY.toFloat())
    }

    private fun clip(text: String, max: Int): String =
        if (text.length <= max) text else text.take(max - 1) + "…"

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(file.readBytes())
        return digest.joinToString("") { "%02x".format(it) }
    }

    private data class EvidenceFile(val file: File, val sha256: String)
}
