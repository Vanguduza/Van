package com.dial.van.trading.ui

import android.graphics.Paint
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
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
import com.dial.van.trading.ChartTextScale
import com.dial.van.trading.ChartViewport
import com.dial.van.trading.ChartViewports
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
    // P4-AND-012 — these were `textSize = 26f` and `24f`, raw pixels, so the owner's font
    // scale did nothing to them. An owner who has enlarged their system font has done so
    // because they need it, and a chart that ignores that is a chart they cannot read.
    val density = LocalDensity.current
    val labelPx = ChartTextScale.pixels(ChartTextScale.AXIS_SP, density.density, density.fontScale)
    val levelPx = ChartTextScale.pixels(ChartTextScale.LEVEL_SP, density.density, density.fontScale)
    val crosshairPx = ChartTextScale.pixels(ChartTextScale.CROSSHAIR_SP, density.density, density.fontScale)
    val labelPaint = remember(labelPx) {
        Paint().apply { color = 0xFF9AA7B6.toInt(); textSize = labelPx; isAntiAlias = true }
    }
    val levelPaint = remember(levelPx) { Paint().apply { textSize = levelPx; isAntiAlias = true } }
    val crosshairPaint = remember(crosshairPx) {
        Paint().apply { color = 0xFFE6F6FB.toInt(); textSize = crosshairPx; isAntiAlias = true }
    }

    // P4-AND-013 — the chart rendered a fixed window of the most recent bars with no
    // interaction, so an owner looking at a trade could not see what happened before it.
    // Saved, because rotating the phone mid-inspection and losing your place is the same
    // defect from the owner's side (P3-AND-007).
    var offsetFromEnd by rememberSaveable(bars.size) { mutableStateOf(0) }
    var visibleBars by rememberSaveable { mutableStateOf(maxVisible) }
    var crosshairAt by remember { mutableStateOf<Offset?>(null) }
    val viewport = ChartViewports.clamp(ChartViewport(offsetFromEnd, visibleBars), bars.size)
    val window = ChartViewports.window(viewport, bars.size)
    val shown = if (bars.isEmpty()) bars else bars.subList(window.first, window.last + 1)

    Canvas(
        modifier = modifier
            .fillMaxWidth()
            .height(heightDp.dp)
            .pointerInput(bars.size) {
                detectTransformGestures { _, pan, zoom, _ ->
                    if (zoom != 1f) {
                        val next = ChartViewports.zoom(
                            ChartViewport(offsetFromEnd, visibleBars), zoom, bars.size,
                        )
                        offsetFromEnd = next.offsetFromEnd
                        visibleBars = next.visibleBars
                    }
                    if (pan.x != 0f) {
                        val next = ChartViewports.pan(
                            ChartViewport(offsetFromEnd, visibleBars), pan.x, size.width.toFloat(), bars.size,
                        )
                        offsetFromEnd = next.offsetFromEnd
                        visibleBars = next.visibleBars
                    }
                }
            }
            .pointerInput(bars.size) {
                detectTapGestures(
                    onPress = { at ->
                        crosshairAt = at
                        // Held for as long as the finger is down: a crosshair that stays
                        // after the owner lifts is a crosshair they have to dismiss.
                        tryAwaitRelease()
                        crosshairAt = null
                    },
                    onDoubleTap = {
                        offsetFromEnd = 0
                        visibleBars = maxVisible
                    },
                )
            },
    ) {
        val layout = ChartLayout(width = size.width, height = size.height)
        val scene = ChartGeometry.build(shown, layout, levels, markers, visibleBars)
        if (scene.visible == 0) {
            // P3-AND-011 — was "No bars available", which tells the owner nothing about
            // whose absence this is.
            drawContext.canvas.nativeCanvas.drawText(
                "No price history yet", 16f, size.height / 2f, labelPaint,
            )
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

        crosshairAt?.let { at ->
            val hit = ChartViewports.crosshair(
                pointerX = at.x, pointerY = at.y,
                plotLeft = layout.plotLeft, plotRight = layout.plotRight,
                plotTop = layout.plotTop, plotBottom = layout.plotBottom,
                viewport = ChartViewport(0, shown.size), barCount = shown.size,
                highPrice = scene.priceMax, lowPrice = scene.priceMin,
            ) ?: return@let
            val ink = Color(0xFF8FA6B4)
            drawLine(ink, Offset(hit.x, layout.plotTop), Offset(hit.x, layout.plotBottom), strokeWidth = 1f)
            drawLine(ink, Offset(layout.plotLeft, hit.y), Offset(layout.plotRight, hit.y), strokeWidth = 1f)
            val bar = shown.getOrNull(hit.barIndex)
            val readout = buildString {
                append(TradingFormat.price(hit.price, digits))
                bar?.let {
                    append("  ")
                    append(TradingFormat.dateShort(it.t))
                    append(' ')
                    append(TradingFormat.timeHm(it.t))
                }
            }
            drawContext.canvas.nativeCanvas.drawText(
                readout, layout.plotLeft + 6f, layout.plotTop + crosshairPx + 2f, crosshairPaint,
            )
        }
    }
}
