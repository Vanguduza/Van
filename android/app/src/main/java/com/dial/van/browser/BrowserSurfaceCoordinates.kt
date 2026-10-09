package com.dial.van.browser

import kotlin.math.roundToInt

/** Matches SCALE_ASPECT_FIT: black bars are not page pixels. Existing drags may end outside the image. */
object BrowserSurfaceCoordinates {
    fun map(x: Float, y: Float, viewWidth: Int, viewHeight: Int, frameWidth: Int, frameHeight: Int,
        clamp: Boolean = false): Pair<Int, Int>? {
        if (!x.isFinite() || !y.isFinite() || minOf(viewWidth, viewHeight, frameWidth, frameHeight) <= 0) return null
        val scale = minOf(viewWidth.toFloat() / frameWidth, viewHeight.toFloat() / frameHeight)
        val width = (frameWidth * scale).roundToInt().coerceAtLeast(1)
        val height = (frameHeight * scale).roundToInt().coerceAtLeast(1)
        val left = (viewWidth - width) / 2f
        val top = (viewHeight - height) / 2f
        if (!clamp && (x < left || y < top || x > left + width - 1 || y > top + height - 1)) return null
        return BrowserInputProtocol.normalize(x - left, width) to BrowserInputProtocol.normalize(y - top, height)
    }
}
