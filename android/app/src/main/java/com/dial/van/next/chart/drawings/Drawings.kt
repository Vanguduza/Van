package com.dial.van.next.chart.drawings

import com.dial.van.next.chart.core.PriceScale
import com.dial.van.next.chart.core.RectF
import com.dial.van.next.chart.core.TimeViewport
import kotlin.math.abs
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min

/**
 * Drawings as durable records (§7.8.4). Anchors are (time, price), never pixels, so a
 * drawing survives zoom, rotation, a different phone and a reload months later. Every
 * change produces a new revision; the history makes undo/redo exact and lets a drawing be
 * cited as evidence ("the level the owner drew on 14 Oct at 1.0825") by chart observations.
 */
data class Anchor(val timeMs: Long, val price: Double)

enum class DrawingKind(val anchorCount: Int) {
    HORIZONTAL_LINE(1),
    TREND_LINE(2),
    RAY(2),
    RECTANGLE(2),
    FIB_RETRACEMENT(2),
    /** Anchors: entry, stop, target. A planning aid only — it never sends an order. */
    RISK_REWARD(3),
    NOTE(1),
}

data class Drawing(
    val id: String,
    val kind: DrawingKind,
    val anchors: List<Anchor>,
    val revision: Int = 1,
    val note: String = "",
    val locked: Boolean = false,
) {
    init {
        require(anchors.size == kind.anchorCount) { "$kind needs ${kind.anchorCount} anchors, got ${anchors.size}" }
        require(anchors.all { it.price.isFinite() }) { "anchor price must be finite" }
    }

    fun moved(newAnchors: List<Anchor>): Drawing {
        check(!locked) { "drawing $id is locked" }
        return copy(anchors = newAnchors, revision = revision + 1)
    }

    /** Reward-to-risk ratio for RISK_REWARD drawings; null when risk is zero or the kind differs. */
    fun rewardToRisk(): Double? {
        if (kind != DrawingKind.RISK_REWARD) return null
        val (entry, stop, target) = anchors.map { it.price }
        val risk = abs(entry - stop)
        if (risk == 0.0) return null
        return abs(target - entry) / risk
    }

    companion object {
        val FIB_LEVELS = listOf(0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)
    }
}

/** Maps anchors to screen space. Time→x goes through the series' bar index. */
class DrawingProjector(
    private val viewport: TimeViewport,
    private val scale: PriceScale,
    private val plot: RectF,
    private val indexOfTime: (Long) -> Double,
) {
    fun x(a: Anchor): Float = viewport.indexToX(indexOfTime(a.timeMs), plot)
    fun y(a: Anchor): Float = scale.priceToY(a.price, plot)

    /** Distance in pixels from (px,py) to the drawing; used for selection. */
    fun distance(d: Drawing, px: Float, py: Float): Float {
        val a = d.anchors
        return when (d.kind) {
            DrawingKind.HORIZONTAL_LINE -> abs(py - y(a[0]))
            DrawingKind.NOTE -> hypot(px - x(a[0]), py - y(a[0]))
            DrawingKind.TREND_LINE -> segDist(px, py, x(a[0]), y(a[0]), x(a[1]), y(a[1]), ray = false)
            DrawingKind.RAY -> segDist(px, py, x(a[0]), y(a[0]), x(a[1]), y(a[1]), ray = true)
            DrawingKind.RECTANGLE -> rectEdgeDist(px, py, x(a[0]), y(a[0]), x(a[1]), y(a[1]))
            DrawingKind.FIB_RETRACEMENT -> Drawing.FIB_LEVELS.minOf { lvl ->
                val p = a[1].price + (a[0].price - a[1].price) * lvl
                abs(py - scale.priceToY(p, plot))
            }
            DrawingKind.RISK_REWARD -> a.minOf { abs(py - y(it)) }
        }
    }

    private fun segDist(px: Float, py: Float, x1: Float, y1: Float, x2: Float, y2: Float, ray: Boolean): Float {
        val dx = x2 - x1
        val dy = y2 - y1
        val len2 = dx * dx + dy * dy
        if (len2 == 0f) return hypot(px - x1, py - y1)
        var t = ((px - x1) * dx + (py - y1) * dy) / len2
        t = if (ray) max(0f, t) else t.coerceIn(0f, 1f)
        return hypot(px - (x1 + t * dx), py - (y1 + t * dy))
    }

    private fun rectEdgeDist(px: Float, py: Float, x1: Float, y1: Float, x2: Float, y2: Float): Float {
        val l = min(x1, x2); val r = max(x1, x2); val t = min(y1, y2); val b = max(y1, y2)
        val edges = listOf(
            segDist(px, py, l, t, r, t, false), segDist(px, py, r, t, r, b, false),
            segDist(px, py, r, b, l, b, false), segDist(px, py, l, b, l, t, false),
        )
        return edges.min()
    }
}

/** Exact undo/redo over drawing revisions. */
class DrawingHistory(initial: Map<String, Drawing> = emptyMap()) {
    var current: Map<String, Drawing> = initial
        private set
    private val undo = ArrayDeque<Map<String, Drawing>>()
    private val redo = ArrayDeque<Map<String, Drawing>>()

    private fun commit(next: Map<String, Drawing>) {
        undo.addLast(current); redo.clear(); current = next
        while (undo.size > MAX_HISTORY) undo.removeFirst()
    }

    fun put(d: Drawing) = commit(current + (d.id to d))
    fun remove(id: String) { if (id in current) commit(current - id) }
    fun canUndo() = undo.isNotEmpty()
    fun canRedo() = redo.isNotEmpty()
    fun undo() { if (undo.isNotEmpty()) { redo.addLast(current); current = undo.removeLast() } }
    fun redo() { if (redo.isNotEmpty()) { undo.addLast(current); current = redo.removeLast() } }

    /** Pick the nearest drawing within [tolerancePx]; null if none is close enough. */
    fun hitTest(projector: DrawingProjector, x: Float, y: Float, tolerancePx: Float): Drawing? =
        current.values
            .map { it to projector.distance(it, x, y) }
            .filter { it.second <= tolerancePx }
            .minByOrNull { it.second }?.first

    companion object { const val MAX_HISTORY = 200 }
}
