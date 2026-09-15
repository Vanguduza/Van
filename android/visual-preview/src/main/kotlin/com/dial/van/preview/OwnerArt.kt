package com.dial.van.preview

import com.dial.van.visual.VanArtPose
import com.dial.van.visual.VanArtPoses
import com.dial.van.visual.VanDurableState
import com.dial.van.visual.VanStatusPalette
import java.awt.Graphics2D
import java.awt.RenderingHints
import java.awt.image.BufferedImage
import java.io.File
import javax.imageio.ImageIO

/**
 * Loads the owner-supplied character poses for the preview sheets.
 *
 * These are the *same* PNGs that ship in `android/app/src/main/res/drawable-nodpi/`, cut from
 * the owner design boards by `:visual-preview:extractOwnerArt`. Reading the shipped bitmaps
 * (rather than redrawing them) is what makes these sheets evidence instead of illustration.
 */
object OwnerArt {

    private val cache = mutableMapOf<VanArtPose, BufferedImage?>()

    private fun directory(): File =
        File(AwtVanRenderer.repoRoot(), "android/app/src/main/res/drawable-nodpi")

    fun load(pose: VanArtPose): BufferedImage? = cache.getOrPut(pose) {
        val file = File(directory(), "${pose.assetName}.png")
        if (file.isFile) runCatching { ImageIO.read(file) }.getOrNull() else null
    }

    fun available(): Boolean = VanArtPose.entries.all { load(it) != null }

    fun forState(state: VanDurableState): BufferedImage? = load(VanArtPoses.forState(state))

    /**
     * Draws the pose fitted into the box, bottom-aligned so Van stands on the glass rather than
     * floating in the middle of it.
     *
     * §6's OFFLINE/DEGRADED muting is applied here with the same [VanStatusPalette] values the
     * app uses, so a dimmed Van in a preview means a dimmed Van on device.
     */
    fun paint(
        g: Graphics2D,
        state: VanDurableState,
        x: Float,
        y: Float,
        w: Float,
        h: Float,
    ): Boolean {
        val source = forState(state) ?: return false
        val palette = VanStatusPalette.forState(state)
        val image = mute(source, palette.desaturation, palette.dim)

        val scale = minOf(w / image.width, h / image.height)
        val dw = image.width * scale
        val dh = image.height * scale
        val dx = x + (w - dw) / 2f
        val dy = y + (h - dh)

        val previous = g.getRenderingHint(RenderingHints.KEY_INTERPOLATION)
        g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BICUBIC)
        g.drawImage(image, dx.toInt(), dy.toInt(), dw.toInt(), dh.toInt(), null)
        if (previous != null) g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, previous)
        return true
    }

    private fun mute(source: BufferedImage, desaturation: Float, dim: Float): BufferedImage {
        if (desaturation <= 0.01f && dim >= 0.99f) return source
        val out = BufferedImage(source.width, source.height, BufferedImage.TYPE_INT_ARGB)
        for (y in 0 until source.height) {
            for (x in 0 until source.width) {
                val p = source.getRGB(x, y)
                val a = (p ushr 24) and 0xFF
                if (a == 0) continue
                var r = (p ushr 16) and 0xFF
                var gg = (p ushr 8) and 0xFF
                var b = p and 0xFF
                if (desaturation > 0.01f) {
                    val luma = (0.299 * r + 0.587 * gg + 0.114 * b).toInt()
                    r = (r + (luma - r) * desaturation).toInt()
                    gg = (gg + (luma - gg) * desaturation).toInt()
                    b = (b + (luma - b) * desaturation).toInt()
                }
                val alpha = (a * dim).toInt().coerceIn(0, 255)
                out.setRGB(x, y, (alpha shl 24) or (r shl 16) or (gg shl 8) or b)
            }
        }
        return out
    }
}
