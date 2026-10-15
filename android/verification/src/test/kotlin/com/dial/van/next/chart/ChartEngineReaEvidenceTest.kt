package com.dial.van.next.chart

import com.dial.van.next.chart.contract.Capability
import com.dial.van.next.chart.contract.ChartCommand
import com.dial.van.next.chart.contract.ChartEvent
import com.dial.van.next.chart.contract.Layer
import com.dial.van.next.chart.core.Bar
import com.dial.van.next.chart.core.BarSeries
import com.dial.van.next.chart.core.DataQuality
import com.dial.van.next.chart.core.InstrumentSpec
import com.dial.van.next.chart.drawings.Anchor
import com.dial.van.next.chart.drawings.Drawing
import com.dial.van.next.chart.drawings.DrawingKind
import com.dial.van.next.chart.indicators.IndicatorType
import com.dial.van.next.chart.scene.ChartLayout
import com.dial.van.next.chart.scene.DrawCmd
import com.dial.van.next.chart.scene.OrderOverlay
import com.dial.van.next.chart.scene.OrderState
import com.dial.van.next.chart.scene.PositionOverlay
import com.dial.van.next.chart.scene.Side
import com.dial.van.next.chart.scene.StyleRole
import com.dial.van.next.chart.scene.TradeOverlays
import com.dial.van.next.chart.tools.Measure
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Behaviour added from the 39 original REA evidence records on van-trading-core
 * (OPUS55_REA_VM_EVIDENCE_INDEX_20261015.json). Each class names the record it answers.
 * Only class/method/field names were used — no third-party code (DEC-039).
 */
private val L = ChartLayout(1080f, 1200f, density = 2.75f)
private val GBPUSD = InstrumentSpec("TEST", "GBPUSD", 5, 0.00001)

private fun gbp(n: Int) = BarSeries.of(GBPUSD, M1, bars(List(n) { 1.27 + it * 0.00002 }), quality = DataQuality.LIVE)
private fun texts(e: ChartEngine, role: StyleRole) = e.frame().list.ofRole(role).filterIsInstance<DrawCmd.Text>().map { it.text }

/** mt5_class_detail_1: ChartRenderer.CHART_REQUESTING / CHART_READY / CHART_SYMBOL_CHANGED. */
class LoadStateTest {
    @Test fun `while a new symbol loads the old candles are not shown under its name`() {
        val e = ChartEngine(series(200), L)
        e.apply(ChartCommand.SetSymbol("TEST", "GBPUSD"))
        val list = e.frame().list
        assertTrue(list.ofRole(StyleRole.CANDLE_UP).isEmpty() && list.ofRole(StyleRole.CANDLE_DOWN).isEmpty())
        assertEquals(listOf("Loading GBPUSD M1…"), texts(e, StyleRole.NOTICE))
    }

    @Test fun `no trade draft can be made while the chart is loading, and an open draft is cleared`() {
        val e = ChartEngine(series(200), L)
        e.frame()
        assertIs<ChartEvent.DraftProposed>(e.dragTradeHandle(Side.LONG, ChartEngine.Handle.STOP, 500f, null).single())
        e.apply(ChartCommand.SetSymbol("TEST", "GBPUSD"))
        assertNull(e.state.overlays.draft)
        val r = e.dragTradeHandle(Side.LONG, ChartEngine.Handle.STOP, 500f, null).single()
        assertIs<ChartEvent.Rejected>(r)
        assertTrue(r.reason.contains("loading GBPUSD"))
    }

    @Test fun `a late snapshot for the previous symbol is refused`() {
        val e = ChartEngine(series(200), L)
        e.apply(ChartCommand.SetSymbol("TEST", "GBPUSD"))
        assertIs<ChartEvent.Rejected>(e.loadSnapshot(series(250)).single())
        assertEquals("EURUSD", e.state.series.instrument.symbol)
        assertNotNull(e.state.loading)
        assertTrue(e.loadSnapshot(gbp(120)).isEmpty())
        assertEquals("GBPUSD", e.state.series.instrument.symbol)
        assertNull(e.state.loading)
    }

    @Test fun `drawings belong to an instrument and undo cannot bring the old ones back`() {
        val e = ChartEngine(series(200), L)
        val t = e.state.series[150].timeMs
        e.apply(ChartCommand.AddDrawing("eur-level", DrawingKind.HORIZONTAL_LINE, listOf(Anchor(t, 1.08))))
        e.apply(ChartCommand.SetSymbol("TEST", "GBPUSD"))
        val gbpLevel = Drawing("gbp-level", DrawingKind.HORIZONTAL_LINE, listOf(Anchor(t, 1.27)))
        e.loadSnapshot(gbp(200), drawings = listOf(gbpLevel))
        assertEquals(setOf("gbp-level"), e.drawings.keys)
        e.apply(ChartCommand.Undo)
        assertEquals(setOf("gbp-level"), e.drawings.keys)
    }

    @Test fun `a resync must be for the same instrument and interval`() {
        val e = ChartEngine(series(200), L)
        assertIs<ChartEvent.Rejected>(e.loadSnapshot(gbp(200)).single())
        assertIs<ChartEvent.Rejected>(e.loadSnapshot(BarSeries.of(EURUSD, 5 * M1, bars(List(10) { 1.08 }))).single())
        assertTrue(e.loadSnapshot(series(210)).isEmpty())
        assertEquals(210, e.state.series.size)
    }

    @Test fun `streamed bars for the series being replaced are ignored`() {
        val e = ChartEngine(series(200), L)
        e.apply(ChartCommand.SetInterval(5 * M1))
        val last = e.state.series.last!!
        e.onBar(Bar(last.timeMs + M1, 1.0, 1.0, 1.0, 1.0), 1, 0)
        assertEquals(200, e.state.series.size)
    }

    @Test fun `an interval change keeps the chart visible and says what is loading`() {
        val e = ChartEngine(series(200), L)
        assertEquals(ChartEvent.SnapshotRequested("TEST", "EURUSD", 5 * M1), e.apply(ChartCommand.SetInterval(5 * M1)).single())
        assertTrue(e.frame().list.ofRole(StyleRole.CANDLE_UP).isNotEmpty())
        assertEquals(listOf("Loading EURUSD M5…"), texts(e, StyleRole.NOTICE))
    }
}

/** mt5_class_detail_1: ChartRenderer.CA_RULER_START / CA_RULER_MOVE / CA_RULER_STOP. */
class RulerTest {
    @Test fun `a measurement is in instrument units`() {
        val s = series(50)
        val m = Measure.of(s, Anchor(s[10].timeMs, 1.08), Anchor(s[20].timeMs, 1.0825))
        assertEquals(10, m.bars)
        assertEquals(250, m.ticks)
        assertTrue(abs(m.percent - 0.23148) < 1e-4, "percent ${m.percent}")
        assertEquals("+0.00250 (+0.23%) · 250 ticks · 10 bars", m.label(5))
    }

    @Test fun `start, move and stop report the measurement and leave nothing behind`() {
        val e = ChartEngine(series(200), L)
        e.frame()
        assertIs<ChartEvent.Measured>(e.apply(ChartCommand.RulerStart(300f, 400f)).single())
        val moved = e.apply(ChartCommand.RulerMove(700f, 200f)).single() as ChartEvent.Measured
        assertFalse(moved.final)
        assertTrue(moved.measurement.bars > 0 && moved.measurement.priceDelta > 0)
        assertTrue(e.frame().list.ofRole(StyleRole.MEASURE).isNotEmpty())
        val done = e.apply(ChartCommand.RulerStop).single() as ChartEvent.Measured
        assertTrue(done.final)
        assertEquals(moved.measurement, done.measurement)
        assertNull(e.state.ruler)
        assertTrue(e.frame().list.ofRole(StyleRole.MEASURE).isEmpty())
    }

    @Test fun `moving a ruler that was never started is refused`() {
        val e = ChartEngine(series(200), L)
        assertIs<ChartEvent.Rejected>(e.apply(ChartCommand.RulerMove(1f, 1f)).single())
    }
}

/** tv_rea_class_chartbridge: ChartBridge.magnetMode / magnetEnabled / magnetDisabled. */
class MagnetTest {
    @Test fun `with the magnet on a point near the high snaps to the exact high`() {
        val e = ChartEngine(series(200), L)
        val f = e.frame()
        val idx = 190
        val x = e.state.viewport.indexToX(idx.toDouble(), f.mainPlot)
        val high = e.state.series[idx].high
        val y = f.scale!!.priceToY(high, f.mainPlot) + 6f // a few pixels off
        val off = e.anchorAt(x, y)!!
        assertNotEquals(high, off.price)
        e.apply(ChartCommand.SetMagnet(true))
        val on = e.anchorAt(x, y)!!
        assertEquals(high, on.price)
        assertEquals(e.state.series[idx].timeMs, on.timeMs)
    }

    @Test fun `the magnet does not pull a point that is far from every price of the bar`() {
        val e = ChartEngine(series(200), L)
        e.apply(ChartCommand.SetMagnet(true))
        val f = e.frame()
        val x = e.state.viewport.indexToX(190.0, f.mainPlot)
        val b = e.state.series[190]
        val a = e.anchorAt(x, f.mainPlot.top + 2f)!!
        assertTrue(a.price !in listOf(b.open, b.high, b.low, b.close))
    }
}

/** mt5_extra_3: IndicatorCollection.getPreviousSettings / resetSettingsToDefault / resetLevelsToDefault. */
class IndicatorSettingsTest {
    @Test fun `a re-added indicator comes back with the settings last used`() {
        val e = ChartEngine(series(200), L)
        e.apply(ChartCommand.AddIndicator("rsi", IndicatorType.RSI, mapOf("period" to 21.0)))
        e.apply(ChartCommand.SetIndicatorLevels("rsi", listOf(80.0, 20.0)))
        e.apply(ChartCommand.RemoveIndicator("rsi"))
        e.apply(ChartCommand.AddIndicator("rsi2", IndicatorType.RSI))
        val again = e.state.indicators.single()
        assertEquals(21.0, again.param("period"))
        assertEquals(listOf(20.0, 80.0), again.levels)
    }

    @Test fun `reset restores default parameters and levels`() {
        val e = ChartEngine(series(200), L)
        e.apply(ChartCommand.AddIndicator("rsi", IndicatorType.RSI, mapOf("period" to 21.0)))
        e.apply(ChartCommand.SetIndicatorLevels("rsi", listOf(25.0)))
        val v = e.state.indicators.single().version
        e.apply(ChartCommand.ResetIndicator("rsi"))
        val r = e.state.indicators.single()
        assertEquals(14.0, r.param("period")); assertEquals(listOf(30.0, 70.0), r.levels); assertTrue(r.version > v)
    }

    @Test fun `levels are drawn where they are set, and bad levels are refused`() {
        val e = ChartEngine(series(200), L)
        e.apply(ChartCommand.AddIndicator("rsi", IndicatorType.RSI))
        fun dashedInPane() = e.frame().let { f -> val pane = f.panes.getValue("rsi")
            f.list.ofRole(StyleRole.GRID).filterIsInstance<DrawCmd.Line>().count { it.dashed && it.y1 > pane.top && it.y1 < pane.bottom } }
        assertEquals(2, dashedInPane())
        e.apply(ChartCommand.SetIndicatorLevels("rsi", listOf(20.0, 50.0, 80.0)))
        assertEquals(3, dashedInPane())
        assertIs<ChartEvent.Rejected>(e.apply(ChartCommand.SetIndicatorLevels("rsi", listOf(Double.NaN))).single())
    }
}

/** tv_rea_class_chartbridge: hideDrawingsShowOthers / hideIndicatorsShowOthers / hidePositionsAndOrdersShowOthers / lockAllDrawingTools. */
class LayersTest {
    private fun withTrades(): ChartEngine {
        val e = ChartEngine(series(200), L)
        val px = e.state.series.last!!.close
        e.setOverlays(TradeOverlays(
            positions = listOf(
                PositionOverlay("a", Side.LONG, px, px - 0.002, stopConfirmed = true, target = px + 0.004, label = "Buy"),
                PositionOverlay("b", Side.LONG, px, px - 0.001, stopConfirmed = false, target = null, label = "Buy"),
            ),
            orders = listOf(OrderOverlay("o", Side.LONG, px - 0.003, OrderState.WORKING, "Buy limit")),
        ))
        return e
    }

    @Test fun `hiding trades never hides a stop the broker has not confirmed`() {
        val e = withTrades()
        e.apply(ChartCommand.SetLayerVisible(Layer.TRADES, false))
        val list = e.frame().list
        assertTrue(list.ofRole(StyleRole.POSITION_ENTRY).isEmpty())
        assertTrue(list.ofRole(StyleRole.POSITION_STOP_CONFIRMED).isEmpty())
        assertTrue(list.ofRole(StyleRole.PENDING_ORDER).isEmpty())
        assertTrue(list.ofRole(StyleRole.POSITION_STOP_UNCONFIRMED).isNotEmpty())
        assertEquals(listOf("Trades hidden"), texts(e, StyleRole.NOTICE))
        e.apply(ChartCommand.SetLayerVisible(Layer.TRADES, true))
        assertTrue(e.frame().list.ofRole(StyleRole.POSITION_ENTRY).isNotEmpty())
        assertTrue(texts(e, StyleRole.NOTICE).isEmpty())
    }

    @Test fun `hiding indicators removes their panes and gives the main plot the room`() {
        val e = ChartEngine(series(200), L)
        e.apply(ChartCommand.AddIndicator("rsi", IndicatorType.RSI))
        val withPane = e.frame().mainPlot.bottom
        e.apply(ChartCommand.SetLayerVisible(Layer.INDICATORS, false))
        val f = e.frame()
        assertTrue(f.panes.isEmpty())
        assertTrue(f.mainPlot.bottom > withPane)
    }

    @Test fun `locked drawings cannot be moved, removed or undone, but new ones can be added`() {
        val e = ChartEngine(series(200), L)
        val t = e.state.series[150].timeMs
        e.apply(ChartCommand.AddDrawing("h", DrawingKind.HORIZONTAL_LINE, listOf(Anchor(t, 1.08))))
        e.apply(ChartCommand.LockAllDrawings(true))
        assertIs<ChartEvent.Rejected>(e.apply(ChartCommand.MoveDrawing("h", listOf(Anchor(t, 1.09)))).single())
        assertIs<ChartEvent.Rejected>(e.apply(ChartCommand.RemoveDrawing("h")).single())
        assertIs<ChartEvent.Rejected>(e.apply(ChartCommand.Undo).single())
        assertIs<ChartEvent.DrawingChanged>(e.apply(ChartCommand.AddDrawing("h2", DrawingKind.HORIZONTAL_LINE, listOf(Anchor(t, 1.07)))).single())
        assertEquals(1.08, e.drawings.getValue("h").anchors.single().price)
    }
}

/** tv_rea_class_chartbridge: ChartBridge.goToTime. */
class GoToTimeTest {
    @Test fun `going to a time centres that bar`() {
        val e = ChartEngine(series(2000), L)
        e.frame()
        val target = e.state.series[400].timeMs + 30_000 // mid-bar resolves to the bar at or before
        val ev = e.apply(ChartCommand.GoToTime(target)).single() as ChartEvent.ViewportChanged
        assertTrue(400 in ev.firstIndex..ev.lastIndex)
        val mid = (ev.firstIndex + ev.lastIndex) / 2
        assertTrue(abs(mid - 400) <= 2, "centre $mid")
    }
}

/** mt5_class_detail_3: TradeOrder.ORDER_STATE_REQUEST_MODIFY / ORDER_STATE_REQUEST_CANCEL. */
class OrderLifecycleTest {
    @Test fun `an order being modified or cancelled is still drawn until the broker confirms`() {
        val e = ChartEngine(series(200), L)
        val px = e.state.series.last!!.close
        e.setOverlays(TradeOverlays(orders = listOf(
            OrderOverlay("m", Side.LONG, px - 0.001, OrderState.MODIFY_REQUESTED, "Buy limit"),
            OrderOverlay("c", Side.LONG, px - 0.002, OrderState.CANCEL_REQUESTED, "Buy limit"),
            OrderOverlay("f", Side.LONG, px - 0.003, OrderState.FILLED, "Buy limit"),
        )))
        val labels = texts(e, StyleRole.PENDING_ORDER)
        assertEquals(2, labels.size)
        assertTrue(labels.any { it.startsWith("Buy limit modify requested") })
        assertTrue(labels.any { it.startsWith("Buy limit cancel requested") })
    }
}

/** tv_rea_class_chartbridge: ChartBridge.hasChartChanges / getAutosave. */
class UnsavedChangesTest {
    @Test fun `workspace changes are tracked and viewing is not a change`() {
        val e = ChartEngine(series(200), L)
        assertFalse(e.hasUnsavedChanges)
        e.apply(ChartCommand.Pan(40f)); e.apply(ChartCommand.Zoom(1.5f, 300f))
        assertFalse(e.hasUnsavedChanges)
        e.apply(ChartCommand.AddIndicator("ema", IndicatorType.EMA))
        assertTrue(e.hasUnsavedChanges)
        e.markSaved()
        assertFalse(e.hasUnsavedChanges)
        e.apply(ChartCommand.AddDrawing("h", DrawingKind.HORIZONTAL_LINE, listOf(Anchor(e.state.series[100].timeMs, 1.08))))
        assertTrue(e.hasUnsavedChanges)
    }
}

class ContractGrowthTest {
    @Test fun `new capabilities are chart-only and the forbidden list is untouched`() {
        val added = listOf(Capability.MEASURE, Capability.MAGNET, Capability.LAYERS, Capability.DRAWING_LOCK, Capability.GOTO, Capability.INDICATOR_LEVELS)
        assertTrue(added.all { it.id.startsWith("chart.") })
        assertTrue(Capability.entries.none { it.id in Capability.FORBIDDEN })
    }
}
