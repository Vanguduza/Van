package com.dial.van.preview

import java.awt.image.BufferedImage
import java.io.File
import java.util.ArrayDeque
import javax.imageio.ImageIO
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * Cuts individual character assets out of the owner-supplied design boards.
 *
 * The boards in `visual-authority/assets/pack/` are the authority artwork, but they are
 * composite sheets. This tool is the reproducible bridge to shippable Android drawables:
 *
 *  1. crop a region expressed as *fractions* of the board, so the recipe survives a board
 *     being re-exported at a different resolution;
 *  2. key out the flat panel background by flooding inward from the crop border, which keeps
 *     Van's black jacket intact because his cyan rim light encloses it;
 *  3. trim to the remaining content and write a premultiplied-safe ARGB PNG.
 *
 * Nothing is repainted or restyled — the owner's pixels are preserved.
 */
object OwnerArtExtractor {

    /** A crop recipe in board fractions (0..1), origin top-left. */
    data class Crop(
        val name: String,
        val board: String,
        val left: Float,
        val top: Float,
        val right: Float,
        val bottom: Float,
        /** How aggressively to key the flat background away. */
        val keyTolerance: Int = 44,
        val key: Boolean = true,
        /** Longest edge of the written asset; null keeps the native crop size. */
        val maxEdge: Int? = null,
    )

    private const val FUTURISTIC = "owner_board_futuristic_interface.png"
    private const val HERMES = "owner_board_dial_hermes_showcase.png"
    private const val AUTHORITY = "owner_board_visual_authority.png"
    private const val ANDROID_UI = "owner_board_android_ui_showcase.png"

    /**
     * State poses come from the 4x2 card grid on the "Futuristic" board, which carries the
     * largest per-state renders in the pack (~180x200px). Crop bounds deliberately sit inside
     * each card's title and caption so the keyed result is Van and his props alone.
     *
     * The authority board's "platform export" tiles are *thumbnails* (~54px on a 1536px
     * board), not real exports, so they are not harvested here — shipping those would be
     * worse than the vector icons already in the app.
     */
    val crops: List<Crop> = listOf(
        // Row 1
        Crop("van_state_idle", FUTURISTIC, 0.398f, 0.128f, 0.552f, 0.272f),
        Crop("van_state_listening", FUTURISTIC, 0.548f, 0.128f, 0.702f, 0.272f),
        Crop("van_state_thinking", FUTURISTIC, 0.698f, 0.128f, 0.852f, 0.272f),
        Crop("van_state_working", FUTURISTIC, 0.848f, 0.128f, 1.000f, 0.272f),
        // Row 2
        Crop("van_state_notifications", FUTURISTIC, 0.398f, 0.352f, 0.552f, 0.490f),
        Crop("van_state_success", FUTURISTIC, 0.548f, 0.352f, 0.702f, 0.490f),
        Crop("van_state_warning", FUTURISTIC, 0.698f, 0.352f, 0.852f, 0.490f),
        // The DRAG & DOCK head close-up is not harvested: the source card has the UI rail
        // drawn over the avatar's right side, so no crop yields an unoccluded head. The
        // compact overlay uses the full-body idle pose, matching the sheet's floating widget.
        // Searching only exists on the Hermes showcase states strip.
        Crop("van_state_searching", HERMES, 0.848f, 0.780f, 0.975f, 0.868f),
    )

    fun run(repoRoot: File): List<File> {
        val packDir = File(repoRoot, "visual-authority/assets/pack")
        val derivedDir = File(repoRoot, "visual-authority/assets/derived").apply { mkdirs() }
        val drawableDir = File(repoRoot, "android/app/src/main/res/drawable-nodpi").apply { mkdirs() }

        val boards = mutableMapOf<String, BufferedImage>()
        val written = mutableListOf<File>()

        crops.forEach { crop ->
            val board = boards.getOrPut(crop.board) {
                val file = File(packDir, crop.board)
                require(file.exists()) { "Owner board missing: $file" }
                ImageIO.read(file)
            }

            var cut = cutRegion(board, crop)
            if (crop.key) {
                cut = keyBackground(cut, crop.keyTolerance)
                cut = dropSmallComponents(cut)
                cut = trimTransparent(cut) ?: cut
            }
            crop.maxEdge?.let { cut = downscaleTo(cut, it) }

            val derived = File(derivedDir, "${crop.name}.png")
            ImageIO.write(cut, "png", derived)
            written += derived

            val drawable = File(drawableDir, "${crop.name}.png")
            ImageIO.write(cut, "png", drawable)
            written += drawable
        }

        ImageIO.write(contactSheet(derivedDir), "png", File(derivedDir, "_contact_sheet.png"))
        return written
    }

    private fun cutRegion(board: BufferedImage, crop: Crop): BufferedImage {
        val x0 = (crop.left * board.width).roundToInt().coerceIn(0, board.width - 2)
        val y0 = (crop.top * board.height).roundToInt().coerceIn(0, board.height - 2)
        val x1 = (crop.right * board.width).roundToInt().coerceIn(x0 + 1, board.width)
        val y1 = (crop.bottom * board.height).roundToInt().coerceIn(y0 + 1, board.height)
        val out = BufferedImage(x1 - x0, y1 - y0, BufferedImage.TYPE_INT_ARGB)
        val g = out.createGraphics()
        g.drawImage(board, 0, 0, out.width, out.height, x0, y0, x1, y1, null)
        g.dispose()
        return out
    }

    /**
     * Flood fills transparency inward from the border while the colour stays close to the
     * sampled panel background. Interior darks are preserved because the flood cannot reach
     * them through Van's lit outline.
     */
    private fun keyBackground(source: BufferedImage, tolerance: Int): BufferedImage {
        val w = source.width
        val h = source.height
        val out = BufferedImage(w, h, BufferedImage.TYPE_INT_ARGB)
        out.createGraphics().apply { drawImage(source, 0, 0, null); dispose() }

        val background = medianBorderColor(source)
        val visited = BooleanArray(w * h)
        val queue = ArrayDeque<Int>()

        fun consider(x: Int, y: Int) {
            if (x < 0 || y < 0 || x >= w || y >= h) return
            val index = y * w + x
            if (visited[index]) return
            visited[index] = true
            if (colorDistance(source.getRGB(x, y), background) <= tolerance) {
                out.setRGB(x, y, 0)
                queue.add(index)
            }
        }

        for (x in 0 until w) {
            consider(x, 0)
            consider(x, h - 1)
        }
        for (y in 0 until h) {
            consider(0, y)
            consider(w - 1, y)
        }

        while (queue.isNotEmpty()) {
            val index = queue.poll()
            val x = index % w
            val y = index / w
            consider(x - 1, y)
            consider(x + 1, y)
            consider(x, y - 1)
            consider(x, y + 1)
        }

        return featherEdges(out)
    }

    /**
     * Removes stray opaque islands left behind by keying — panel label text, tile borders,
     * dust. Van's body is the largest component; his props (waveform, envelope, tick, warning
     * triangle, holo panel, orb) are comfortably above the threshold, while glyphs are not.
     */
    private fun dropSmallComponents(image: BufferedImage, keepRatio: Float = 0.06f): BufferedImage {
        val w = image.width
        val h = image.height
        val label = IntArray(w * h) { -1 }
        val areas = mutableListOf<Int>()

        fun opaque(index: Int) = ((image.getRGB(index % w, index / w) ushr 24) and 0xFF) > 12

        for (start in 0 until w * h) {
            if (label[start] != -1 || !opaque(start)) continue
            val id = areas.size
            var area = 0
            val queue = ArrayDeque<Int>()
            queue.add(start)
            label[start] = id
            while (queue.isNotEmpty()) {
                val index = queue.poll()
                area++
                val x = index % w
                val y = index / w
                for ((dx, dy) in NEIGHBOURS) {
                    val nx = x + dx
                    val ny = y + dy
                    if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue
                    val next = ny * w + nx
                    if (label[next] != -1 || !opaque(next)) continue
                    label[next] = id
                    queue.add(next)
                }
            }
            areas += area
        }

        if (areas.isEmpty()) return image
        val threshold = (areas.max() * keepRatio).toInt()
        val out = BufferedImage(w, h, BufferedImage.TYPE_INT_ARGB)
        for (y in 0 until h) {
            for (x in 0 until w) {
                val id = label[y * w + x]
                val keep = id >= 0 && areas[id] >= threshold
                out.setRGB(x, y, if (keep) image.getRGB(x, y) else 0)
            }
        }
        return out
    }

    private val NEIGHBOURS = listOf(
        -1 to 0, 1 to 0, 0 to -1, 0 to 1,
        -1 to -1, 1 to -1, -1 to 1, 1 to 1,
    )

    /** One-pixel alpha feather so keyed edges do not look cut out with scissors. */
    private fun featherEdges(image: BufferedImage): BufferedImage {
        val w = image.width
        val h = image.height
        val out = BufferedImage(w, h, BufferedImage.TYPE_INT_ARGB)
        for (y in 0 until h) {
            for (x in 0 until w) {
                val argb = image.getRGB(x, y)
                val alpha = (argb ushr 24) and 0xFF
                if (alpha == 0) {
                    out.setRGB(x, y, 0)
                    continue
                }
                var transparentNeighbours = 0
                for (dy in -1..1) {
                    for (dx in -1..1) {
                        val nx = x + dx
                        val ny = y + dy
                        if (nx in 0 until w && ny in 0 until h) {
                            if (((image.getRGB(nx, ny) ushr 24) and 0xFF) == 0) transparentNeighbours++
                        }
                    }
                }
                val scaled = if (transparentNeighbours >= 3) (alpha * 0.55f).toInt() else alpha
                out.setRGB(x, y, (scaled shl 24) or (argb and 0x00FFFFFF))
            }
        }
        return out
    }

    private fun medianBorderColor(image: BufferedImage): Int {
        val samples = mutableListOf<Int>()
        val stepX = max(1, image.width / 64)
        val stepY = max(1, image.height / 64)
        var x = 0
        while (x < image.width) {
            samples += image.getRGB(x, 0)
            samples += image.getRGB(x, image.height - 1)
            x += stepX
        }
        var y = 0
        while (y < image.height) {
            samples += image.getRGB(0, y)
            samples += image.getRGB(image.width - 1, y)
            y += stepY
        }
        val r = samples.map { (it ushr 16) and 0xFF }.sorted()[samples.size / 2]
        val g = samples.map { (it ushr 8) and 0xFF }.sorted()[samples.size / 2]
        val b = samples.map { it and 0xFF }.sorted()[samples.size / 2]
        return (0xFF shl 24) or (r shl 16) or (g shl 8) or b
    }

    private fun colorDistance(a: Int, b: Int): Int =
        abs(((a ushr 16) and 0xFF) - ((b ushr 16) and 0xFF)) +
            abs(((a ushr 8) and 0xFF) - ((b ushr 8) and 0xFF)) +
            abs((a and 0xFF) - (b and 0xFF))

    private fun trimTransparent(image: BufferedImage, padding: Int = 2): BufferedImage? {
        var minX = image.width
        var minY = image.height
        var maxX = -1
        var maxY = -1
        for (y in 0 until image.height) {
            for (x in 0 until image.width) {
                if (((image.getRGB(x, y) ushr 24) and 0xFF) > 12) {
                    if (x < minX) minX = x
                    if (y < minY) minY = y
                    if (x > maxX) maxX = x
                    if (y > maxY) maxY = y
                }
            }
        }
        if (maxX < minX || maxY < minY) return null
        minX = (minX - padding).coerceAtLeast(0)
        minY = (minY - padding).coerceAtLeast(0)
        maxX = (maxX + padding).coerceAtMost(image.width - 1)
        maxY = (maxY + padding).coerceAtMost(image.height - 1)
        return image.getSubimage(minX, minY, maxX - minX + 1, maxY - minY + 1)
    }

    private fun downscaleTo(image: BufferedImage, maxEdge: Int): BufferedImage {
        val longest = max(image.width, image.height)
        if (longest <= maxEdge) return image
        val scale = maxEdge.toFloat() / longest
        val w = (image.width * scale).roundToInt().coerceAtLeast(1)
        val h = (image.height * scale).roundToInt().coerceAtLeast(1)
        val out = BufferedImage(w, h, BufferedImage.TYPE_INT_ARGB)
        val g = out.createGraphics()
        AwtVanRenderer.prepare(g)
        g.setRenderingHint(
            java.awt.RenderingHints.KEY_INTERPOLATION,
            java.awt.RenderingHints.VALUE_INTERPOLATION_BICUBIC,
        )
        g.drawImage(image, 0, 0, w, h, null)
        g.dispose()
        return out
    }

    /** Checkerboard contact sheet so keyed alpha can be eyeballed before wiring. */
    private fun contactSheet(derivedDir: File): BufferedImage {
        val files = derivedDir.listFiles { f: File -> f.extension == "png" && !f.name.startsWith("_") }
            ?.sortedBy { it.name }
            ?: emptyList()
        val cell = 240
        val cols = 6
        val rows = (files.size + cols - 1) / cols
        val sheet = BufferedImage(cols * cell, max(1, rows) * (cell + 26), BufferedImage.TYPE_INT_ARGB)
        val g = sheet.createGraphics()
        AwtVanRenderer.prepare(g)
        for (y in 0 until sheet.height step 16) {
            for (x in 0 until sheet.width step 16) {
                val dark = ((x / 16) + (y / 16)) % 2 == 0
                g.color = if (dark) java.awt.Color(0xFF303030.toInt()) else java.awt.Color(0xFF505050.toInt())
                g.fillRect(x, y, 16, 16)
            }
        }
        g.font = java.awt.Font(java.awt.Font.SANS_SERIF, java.awt.Font.BOLD, 13)
        files.forEachIndexed { index, file ->
            val image = ImageIO.read(file)
            val col = index % cols
            val row = index / cols
            val boxX = col * cell
            val boxY = row * (cell + 26)
            val scale = minOf((cell - 16f) / image.width, (cell - 16f) / image.height)
            val dw = (image.width * scale).roundToInt()
            val dh = (image.height * scale).roundToInt()
            g.drawImage(image, boxX + (cell - dw) / 2, boxY + (cell - dh) / 2, dw, dh, null)
            g.color = java.awt.Color.WHITE
            g.drawString("${file.nameWithoutExtension} ${image.width}x${image.height}", boxX + 6, boxY + cell + 16)
        }
        g.dispose()
        return sheet
    }
}
