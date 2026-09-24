package com.dial.van.preview

import com.dial.van.visual.VanAuraDepth
import com.dial.van.visual.VanAuraSpec
import com.dial.van.visual.VanAuraSpecs
import com.dial.van.visual.VanDurableState
import com.dial.van.visual.VanEffectBudget
import com.dial.van.visual.VanGlassTokens
import com.dial.van.visual.VanPresentation
import com.dial.van.visual.VanSceneFrame
import com.dial.van.visual.VanTradeSemantic
import com.dial.van.visual.VanTradeSemantics
import com.dial.van.visual.VanVisualState
import java.awt.Color
import java.awt.Font
import java.awt.GradientPaint
import java.awt.image.BufferedImage
import java.io.File
import javax.imageio.IIOImage
import javax.imageio.ImageIO
import javax.imageio.ImageTypeSpecifier
import javax.imageio.metadata.IIOMetadataNode

/**
 * Aura Rev 2 evidence that stills cannot give: the trading field, and motion.
 *
 * * [tradeSheet] — every trade family on real Candidate B art, plus the closed-trade pulse.
 * * [writeMotionClips] — 8-second clips per key state, driven by the same two clocks as the
 *   app (the fast state loop and the 23.7 s slow clock), so a reviewer can check the fire
 *   neither loops visibly nor stutters. They are CI evidence (uploaded with the preview
 *   artifact) and are not committed.
 */
object VanAuraMotion {

    private const val PHASE = 0.18f
    private const val SLOW_PERIOD_S = 23.7f

    private fun paint(
        g: java.awt.Graphics2D, activity: VanAuraSpec, semantic: VanAuraSpec, state: VanDurableState,
        cx: Float, cy: Float, box: Float, phase: Float, slow: Float, pulse: Float = 0f,
    ) {
        val shape = AwtVanRenderer.interimSilhouette(VanPresentation.COMMAND_CENTRE)
        GlassPainter.drawAura(g, activity, cx, cy, box / 2f, VanEffectBudget.FULL, phase, semantic,
            silhouette = shape, slowPhase = slow, pulse = pulse)
        AwtVanRenderer.paintVan(
            g, VanVisualState(durableState = state),
            VanSceneFrame(presentation = VanPresentation.COMMAND_CENTRE, phase = phase),
            cx - box / 2f, cy - box / 2f, box, box,
        )
        GlassPainter.drawAura(g, activity, cx, cy, box / 2f, VanEffectBudget.FULL, phase, semantic,
            depth = VanAuraDepth.FRONT, silhouette = shape, slowPhase = slow, pulse = pulse)
    }

    fun tradeSheet(): BufferedImage {
        val families = VanTradeSemantic.entries
        val cols = 6
        val cell = 330
        val box = 240f
        val pad = 40
        val header = 150
        val rows = (families.size + 1 + cols - 1) / cols
        val w = pad * 2 + cols * cell
        val h = header + rows * (cell + 30) + 30
        val image = BufferedImage(w, h, BufferedImage.TYPE_INT_ARGB)
        val g = image.createGraphics()
        AwtVanRenderer.prepare(g)
        g.paint = GradientPaint(0f, 0f, Color(0xFF080C13.toInt()), 0f, h.toFloat(), Color(0xFF05080D.toInt()))
        g.fillRect(0, 0, w, h)
        g.color = Color(0xFFE8F4FA.toInt(), true)
        g.font = Font(Font.SANS_SERIF, Font.BOLD, 36)
        g.drawString("VAN trading aura — Rev 2", pad, 68)
        g.font = Font(Font.SANS_SERIF, Font.PLAIN, 17)
        g.color = Color(0xFF9FB3C0.toInt(), true)
        g.drawString("Each trade family sets colour and flame energy: calm coherent fire in a trade, turbulence under risk, a fragmented high-energy field on a stop.", pad, 100)
        g.drawString("Owner authority, alerts and offline truth outrank the market; the last panel is the brief white pulse when a position closes.", pad, 124)
        val idle = VanAuraSpecs.forState(VanDurableState.IDLE)
        val panels = families.map { it.name to VanTradeSemantics.auraFor(it) } + ("CLOSED (pulse)" to VanTradeSemantics.auraFor(VanTradeSemantic.FLAT))
        panels.forEachIndexed { i, (name, spec) ->
            val cx = pad + (i % cols) * cell + cell / 2f
            val cy = header + (i / cols) * (cell + 30) + cell / 2f
            val pulse = if (name.startsWith("CLOSED")) 0.8f else 0f
            paint(g, idle, spec, VanDurableState.IDLE, cx, cy, box, PHASE, 0.2f, pulse)
            g.color = Color(VanGlassTokens.EDGE_CYAN, true)
            g.font = Font(Font.SANS_SERIF, Font.BOLD, 17)
            val label = name.lowercase().replace('_', ' ')
            g.drawString(label, (cx - g.fontMetrics.stringWidth(label) / 2f), cy + box / 2f + 30f)
        }
        g.dispose()
        return image
    }

    /** Writes `motion/<state>.gif`: [seconds] s at [fps], 240 px, both clocks running. */
    fun writeMotionClips(outputDir: File, seconds: Int = 8, fps: Int = 10) {
        val dir = File(outputDir, "motion").apply { mkdirs() }
        val states = listOf(
            VanDurableState.IDLE, VanDurableState.THINKING, VanDurableState.WORKING, VanDurableState.WARNING,
            VanDurableState.URGENT, VanDurableState.SUCCESS, VanDurableState.ERROR, VanDurableState.OFFLINE,
        )
        for (state in states) {
            val spec = VanAuraSpecs.forState(state)
            // One fast loop per ~2.6 s, as the shipping clock runs a working VAN.
            val loopSeconds = 2.6f
            val frames = (0 until seconds * fps).map { f ->
                val t = f.toFloat() / fps
                val size = 240
                val img = BufferedImage(size, size, BufferedImage.TYPE_INT_RGB)
                val g = img.createGraphics()
                AwtVanRenderer.prepare(g)
                g.color = Color(0xFF080C13.toInt())
                g.fillRect(0, 0, size, size)
                paint(g, spec, spec, state, size / 2f, size / 2f + 8f, 150f, (t / loopSeconds) % 1f, (t / SLOW_PERIOD_S) % 1f)
                g.dispose()
                img
            }
            writeGif(File(dir, "${state.name.lowercase()}.gif"), frames, 1000 / fps)
        }
    }

    private fun writeGif(file: File, frames: List<BufferedImage>, delayMs: Int) {
        val writer = ImageIO.getImageWritersBySuffix("gif").next()
        ImageIO.createImageOutputStream(file).use { out ->
            writer.output = out
            writer.prepareWriteSequence(null)
            for (frame in frames) {
                val params = writer.defaultWriteParam
                val type = ImageTypeSpecifier.createFromRenderedImage(frame)
                val meta = writer.getDefaultImageMetadata(type, params)
                val format = meta.nativeMetadataFormatName
                val root = meta.getAsTree(format) as IIOMetadataNode
                val gce = child(root, "GraphicControlExtension")
                gce.setAttribute("disposalMethod", "none")
                gce.setAttribute("userInputFlag", "FALSE")
                gce.setAttribute("transparentColorFlag", "FALSE")
                gce.setAttribute("delayTime", (delayMs / 10).toString())
                gce.setAttribute("transparentColorIndex", "0")
                val apps = child(root, "ApplicationExtensions")
                val app = IIOMetadataNode("ApplicationExtension")
                app.setAttribute("applicationID", "NETSCAPE")
                app.setAttribute("authenticationCode", "2.0")
                app.userObject = byteArrayOf(1, 0, 0)
                apps.appendChild(app)
                meta.setFromTree(format, root)
                writer.writeToSequence(IIOImage(frame, null, meta), params)
            }
            writer.endWriteSequence()
        }
        writer.dispose()
    }

    private fun child(root: IIOMetadataNode, name: String): IIOMetadataNode {
        for (i in 0 until root.length) {
            val node = root.item(i)
            if (node.nodeName.equals(name, ignoreCase = true)) return node as IIOMetadataNode
        }
        return IIOMetadataNode(name).also { root.appendChild(it) }
    }
}
