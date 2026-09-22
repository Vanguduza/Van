package com.dial.van.design.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.dial.van.design.LocalVanTokens

/**
 * A minimal trend line — no axes, no gridlines, no interaction. `MetricTile`'s companion, not
 * a chart: for anything an owner pans, zooms or inspects a crosshair on, that is
 * `CandlestickChart` (trading's own, drawn with `design/charts/ChartAxes`'s tick math).
 *
 * `values.size <= 1` draws nothing rather than a degenerate flat line, since there is no trend
 * to show yet — the caller (`MetricTile`) still reserves the space so the tile's geometry does
 * not jump when the second data point arrives.
 */
@Composable
fun Sparkline(
    values: List<Float>,
    modifier: Modifier = Modifier,
    lineColor: Color? = null,
    strokeWidthDp: Float = 1.6f,
) {
    val tokens = LocalVanTokens.current
    val color = lineColor ?: tokens.color.accentCyanSoft
    Canvas(
        modifier = modifier
            .fillMaxWidth()
            .height(28.dp)
            .semantics { contentDescription = "Trend" },
    ) {
        if (values.size <= 1) return@Canvas
        val minValue = values.min()
        val maxValue = values.max()
        val range = (maxValue - minValue).takeIf { it > 0f } ?: 1f
        val stepX = size.width / (values.size - 1).coerceAtLeast(1)
        val path = androidx.compose.ui.graphics.Path()
        values.forEachIndexed { index, value ->
            val x = stepX * index
            val normalized = (value - minValue) / range
            val y = size.height - (normalized * size.height)
            if (index == 0) path.moveTo(x, y) else path.lineTo(x, y)
        }
        drawPath(path = path, color = color, style = Stroke(width = strokeWidthDp.dp.toPx()))
        val lastX = stepX * (values.size - 1)
        val lastNormalized = (values.last() - minValue) / range
        val lastY = size.height - (lastNormalized * size.height)
        drawCircle(color = color, radius = strokeWidthDp.dp.toPx() * 1.4f, center = Offset(lastX, lastY))
    }
}
