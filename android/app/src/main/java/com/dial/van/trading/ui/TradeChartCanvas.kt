package com.dial.van.trading.ui

import android.graphics.Paint
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.unit.dp
import com.dial.van.trading.BarPoint
import com.dial.van.trading.ChartGeometry
import com.dial.van.trading.ChartLayout
import com.dial.van.trading.ChartLevel
import com.dial.van.trading.ChartMarker
import com.dial.van.trading.ChartOp
import com.dial.van.trading.TradingFormat

/**
 * Candlestick chart with levels, zones and trade markers, drawn from [ChartGeometry] ops
 * (blueprint §10). Everything numeric is decided off the UI thread by the pure geometry;
 * this composable only paints. No decorative animation: motion must never interfere with
 * chart interpretation (§43).
 */
@Composable
fun TradeChartCanvas(
    bars: List<BarPoint>,
    modifier: Modifier = Modifier,
    levels: List<ChartLevel> = emptyList(),
    markers: List<ChartMarker> = emptyList(),
    digits: Int = 5,
    heightDp: Int = 220,
    maxVisible: Int = 120,
) {
    val labelPaint = remember { Paint().apply { color = 0xFF9AA7B6.toInt(); textSize = 26f; isAntiAlias = true } }
    val levelPaint = remember { Paint().apply { textSize = 24f; isAntiAlias = true } }
    Canvas(modifier = modifier.fillMaxWidth().height(heightDp.dp)) {
        val layout = ChartLayout(width = size.width, height = size.height)
        val scene = ChartGeometry.build(bars, layout, levels, markers, maxVisible)
        if (scene.visible == 0) {
            drawContext.canvas.nativeCanvas.drawText("No bars available", 16f, size.height / 2f, labelPaint)
            return@Canvas
        }
        val grid = Color(0xFF1B2636)
        scene.ops.forEach { op ->
            when (op) {
                is ChartOp.GridLine -> {
                    drawLine(grid, Offset(layout.plotLeft, op.y), Offset(layout.plotRight, op.y), strokeWidth = 1f)
                    drawContext.canvas.nativeCanvas.drawText(TradingFormat.price(op.price, digits), layout.plotRight + 6f, op.y + 9f, labelPaint)
                }
                is ChartOp.Zone -> drawRect(
                    color = Color(op.kind.argb).copy(alpha = 0.08f),
                    topLeft = Offset(layout.plotLeft, op.yTop),
                    size = Size(layout.plotRight - layout.plotLeft, (op.yBottom - op.yTop).coerceAtLeast(1f)),
                )
                else -> Unit
            }
        }
        scene.ops.filterIsInstance<ChartOp.Candle>().forEach { c ->
            val color = Color(if (c.up) ChartGeometry.UP else ChartGeometry.DOWN)
            drawLine(color, Offset(c.x, c.yHigh), Offset(c.x, c.yLow), strokeWidth = 1.5f)
            val top = minOf(c.yOpen, c.yClose); val bottom = maxOf(c.yOpen, c.yClose)
            drawRect(color, topLeft = Offset(c.x - c.halfWidth, top), size = Size(c.halfWidth * 2, (bottom - top).coerceAtLeast(1.5f)))
        }
        scene.ops.filterIsInstance<ChartOp.HLine>().forEach { l ->
            val color = Color(l.kind.argb)
            val path = Path().apply { moveTo(layout.plotLeft, l.y); lineTo(layout.plotRight, l.y) }
            drawPath(path, color.copy(alpha = 0.9f), style = Stroke(width = 1.5f, pathEffect = androidx.compose.ui.graphics.PathEffect.dashPathEffect(floatArrayOf(10f, 6f))))
            levelPaint.color = l.kind.argb.toInt()
            drawContext.canvas.nativeCanvas.drawText("${l.label} ${TradingFormat.price(l.price, digits)}", layout.plotLeft + 4f, l.y - 5f, levelPaint)
        }
        scene.ops.filterIsInstance<ChartOp.Marker>().forEach { m ->
            val color = Color(if (m.kind == "ENTRY") ChartGeometry.UP else 0xFFFFB300L)
            val path = Path().apply {
                if (m.up) { moveTo(m.x, m.y + 6f); lineTo(m.x - 7f, m.y + 18f); lineTo(m.x + 7f, m.y + 18f) } else { moveTo(m.x, m.y - 6f); lineTo(m.x - 7f, m.y - 18f); lineTo(m.x + 7f, m.y - 18f) }
                close()
            }
            drawPath(path, color)
            drawCircle(color, radius = 3f, center = Offset(m.x, m.y))
        }
        scene.ops.filterIsInstance<ChartOp.TimeTick>().forEach { t ->
            drawContext.canvas.nativeCanvas.drawText(TradingFormat.dateShort(t.t) + " " + TradingFormat.timeHm(t.t), t.x - 30f, size.height - 4f, labelPaint)
        }
    }
}
