package com.dial.van.next.chart

import com.dial.van.next.chart.contract.BridgeEnvelope
import com.dial.van.next.chart.contract.BridgeGate
import com.dial.van.next.chart.contract.BridgeVerdict
import com.dial.van.next.chart.contract.Capability
import com.dial.van.next.chart.contract.ChartCommand
import com.dial.van.next.chart.contract.ChartEvent
import com.dial.van.next.chart.core.Bar
import com.dial.van.next.chart.core.DataQuality
import com.dial.van.next.chart.core.PriceScale
import com.dial.van.next.chart.core.RectF
import com.dial.van.next.chart.core.TimeViewport
import com.dial.van.next.chart.drawings.Anchor
import com.dial.van.next.chart.drawings.Drawing
import com.dial.van.next.chart.drawings.DrawingHistory
import com.dial.van.next.chart.drawings.DrawingKind
import com.dial.van.next.chart.drawings.DrawingProjector
import com.dial.van.next.chart.indicators.IndicatorType
import com.dial.van.next.chart.runtime.FrameScheduler
import com.dial.van.next.chart.scene.ChartLayout
import com.dial.van.next.chart.scene.DrawCmd
import com.dial.van.next.chart.scene.OrderOverlay
import com.dial.van.next.chart.scene.OrderState
import com.dial.van.next.chart.scene.PositionOverlay
import com.dial.van.next.chart.scene.SceneBuilder
import com.dial.van.next.chart.scene.Side
import com.dial.van.next.chart.scene.StyleRole
import com.dial.van.next.chart.scene.TradeOverlays
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

private val LAYOUT = ChartLayout(1080f, 1200f, density = 2.75f)

class SceneTest {
    private fun engine(n: Int = 300, q: DataQuality = DataQuality.LIVE) = ChartEngine(series(n, q), LAYOUT)

    @Test fun `the same state builds the same frame`() {
        val e = engine()
        assertEquals(e.frame().list.commands, e.frame().list.commands)
    }

    @Test fun `data quality is shown in words and live shows nothing`() {
        assertTrue(engine(q = DataQuality.LIVE).frame().list.ofRole(StyleRole.QUALITY_BADGE).isEmpty())
        val badge = engine(q = DataQuality.STALE).frame().list.ofRole(StyleRole.QUALITY_BADGE).single() as DrawCmd.Text
        assertEquals("Stale — not live", badge.text)
    }

    @Test fun `an unconfirmed stop is never drawn as a confirmed one`() {
        val e = engine()
        val px = e.state.series.last!!.close
        e.setOverlays(TradeOverlays(positions = listOf(PositionOverlay("p1", Side.LONG, px, px - 0.002, stopConfirmed = false, target = null, label = "Buy 0.10"))))
        val list = e.frame().list
        assertTrue(list.ofRole(StyleRole.POSITION_STOP_CONFIRMED).isEmpty())
        assertTrue(list.ofRole(StyleRole.POSITION_STOP_UNCONFIRMED).isNotEmpty())
    }

    @Test fun `filled or cancelled orders are not drawn as resting`() {
        val e = engine()
        val px = e.state.series.last!!.close
        e.setOverlays(TradeOverlays(orders = listOf(
            OrderOverlay("o1", Side.LONG, px - 0.001, OrderState.WORKING, "Buy limit"),
            OrderOverlay("o2", Side.LONG, px - 0.002, OrderState.CANCELLED, "Buy limit"),
        )))
        assertEquals(1, e.frame().list.ofRole(StyleRole.PENDING_ORDER).filterIsInstance<DrawCmd.Line>().size)
    }

    @Test fun `separate pane indicators get their own pane and warm-up gaps are not drawn as zero`() {
        val e = engine(60)
        e.apply(ChartCommand.AddIndicator("rsi", IndicatorType.RSI))
        e.apply(ChartCommand.AddIndicator("sma50", IndicatorType.SMA, mapOf("period" to 50.0)))
        val f = e.frame()
        assertNotNull(f.panes["rsi"])
        assertTrue(f.panes.getValue("rsi").top > f.mainPlot.bottom)
        // RSI is indicator #0 (slot 1), the SMA is #1 (slot 2): different colours, different panes.
        val rsi = f.list.ofRole(StyleRole.INDICATOR_1).filterIsInstance<DrawCmd.Polyline>()
        val sma = f.list.ofRole(StyleRole.INDICATOR_2).filterIsInstance<DrawCmd.Polyline>()
        assertTrue(rsi.isNotEmpty() && rsi.all { p -> p.ys.all { it > f.mainPlot.bottom } }, "RSI must be drawn only in its pane")
        assertTrue(sma.isNotEmpty() && sma.all { it.xs.size <= 11 }, "SMA(50) over 60 bars must have at most 11 points")
        assertTrue(sma.all { p -> p.ys.all { it <= f.mainPlot.bottom } }, "SMA must be drawn only in the main plot")
    }

    @Test fun `empty series says so instead of drawing nothing`() {
        val e = ChartEngine(com.dial.van.next.chart.core.BarSeries.of(EURUSD, M1, emptyList(), quality = DataQuality.OFFLINE), LAYOUT)
        val texts = e.frame().list.commands.filterIsInstance<DrawCmd.Text>().map { it.text }
        assertTrue("Offline — no bars cached" in texts)
    }
}

class EngineTest {
    @Test fun `replay hides the future and never trades`() {
        val e = ChartEngine(series(300), LAYOUT)
        e.frame()
        val ev = e.apply(ChartCommand.StartReplay(100))
        assertEquals(ChartEvent.ReplayPosition(100, false), ev.single())
        val f = e.frame()
        val maxX = f.list.ofRole(StyleRole.CANDLE_UP).plus(f.list.ofRole(StyleRole.CANDLE_DOWN)).filterIsInstance<DrawCmd.Rect>().maxOf { it.right }
        val cursorX = e.state.viewport.indexToX(100.0, f.mainPlot)
        assertTrue(maxX <= cursorX + e.state.viewport.barSpacingPx, "a bar after the replay cursor was drawn")
        assertIs<ChartEvent.Rejected>(e.dragTradeHandle(Side.LONG, ChartEngine.Handle.STOP, 500f, null).single())
        assertEquals(ChartEvent.ReplayPosition(105, false), e.apply(ChartCommand.StepReplay(5)).single())
    }

    @Test fun `dragging a stop creates a tick-rounded draft and nothing else`() {
        val e = ChartEngine(series(300), LAYOUT)
        e.frame()
        val ev = e.dragTradeHandle(Side.LONG, ChartEngine.Handle.STOP, 600f, null).single() as ChartEvent.DraftProposed
        val stop = ev.stop!!
        assertEquals(stop, EURUSD.roundToTick(stop))
        assertTrue(e.frame().list.ofRole(StyleRole.DRAFT_PROPOSAL).isNotEmpty())
        assertTrue(e.frame().list.ofRole(StyleRole.POSITION_STOP_CONFIRMED).isEmpty())
    }

    @Test fun `a feed gap marks the chart stale and asks for a snapshot`() {
        val e = ChartEngine(series(10), LAYOUT)
        var asked: String? = null
        e.onResyncNeeded = { asked = it }
        e.onBar(e.state.series.last!!, revision = 5, receivedMs = 0)
        assertNotNull(asked)
        assertEquals(DataQuality.STALE, e.state.series.quality)
    }

    @Test fun `a new bar keeps a chart that follows the latest bar following it`() {
        val e = ChartEngine(series(10), LAYOUT)
        val before = e.state.viewport.rightIndex
        val last = e.state.series.last!!
        e.onBar(Bar(last.timeMs + M1, last.close, last.close + 0.0003, last.close - 0.0001, last.close + 0.0002), 1, 1)
        assertEquals(before + 1, e.state.viewport.rightIndex)
    }

    @Test fun `bad indicator parameters are rejected, not applied`() {
        val e = ChartEngine(series(50), LAYOUT)
        assertIs<ChartEvent.Rejected>(e.apply(ChartCommand.AddIndicator("m", IndicatorType.MACD, mapOf("fast" to 30.0, "slow" to 10.0, "signal" to 9.0))).single())
        assertTrue(e.state.indicators.isEmpty())
    }

    @Test fun `symbol changes are the host's job`() {
        val e = ChartEngine(series(50), LAYOUT)
        assertIs<ChartEvent.Rejected>(e.apply(ChartCommand.SetSymbol("X", "GBPUSD")).single())
    }
}

class DrawingTest {
    private val plot = RectF(0f, 0f, 800f, 400f)
    private val s = series(200)
    private val proj = DrawingProjector(TimeViewport(199.0, 4f), PriceScale(1.07, 1.09), plot) { s.indexAtOrBefore(it).toDouble() }

    @Test fun `anchor counts are enforced`() {
        assertFailsWith<IllegalArgumentException> { Drawing("d", DrawingKind.TREND_LINE, listOf(Anchor(0, 1.0))) }
    }

    @Test fun `undo and redo are exact and locked drawings cannot move`() {
        val h = DrawingHistory()
        val d = Drawing("h1", DrawingKind.HORIZONTAL_LINE, listOf(Anchor(s[10].timeMs, 1.08)))
        h.put(d); h.put(d.moved(listOf(Anchor(s[10].timeMs, 1.081))))
        h.undo(); assertEquals(1.08, h.current.getValue("h1").anchors[0].price)
        h.redo(); assertEquals(2, h.current.getValue("h1").revision)
        assertFailsWith<IllegalStateException> { d.copy(locked = true).moved(d.anchors) }
    }

    @Test fun `hit testing picks the nearest drawing within tolerance`() {
        val h = DrawingHistory()
        h.put(Drawing("a", DrawingKind.HORIZONTAL_LINE, listOf(Anchor(s[50].timeMs, 1.080))))
        h.put(Drawing("b", DrawingKind.HORIZONTAL_LINE, listOf(Anchor(s[50].timeMs, 1.085))))
        val yA = PriceScale(1.07, 1.09).priceToY(1.080, plot)
        assertEquals("a", h.hitTest(proj, 400f, yA + 3f, 12f)?.id)
        assertNull(h.hitTest(proj, 400f, yA + 60f, 12f))
    }

    @Test fun `risk reward ratio`() {
        val d = Drawing("rr", DrawingKind.RISK_REWARD, listOf(Anchor(0, 1.0800), Anchor(0, 1.0780), Anchor(0, 1.0850)))
        assertEquals(2.5, d.rewardToRisk()!!, 1e-9)
    }
}

class BridgeGateTest {
    private fun env(seq: Long, cap: String = "chart.zoom", effect: String = "NONE", id: String = "m$seq", now: Long = 1000) =
        BridgeEnvelope(BridgeGate.SCHEMA, "s1", id, seq, now, now + 4000, "van-native-host", cap, 100, effect)

    private fun gate() = BridgeGate("s1", "van-native-host", setOf(Capability.ZOOM, Capability.PAN))

    @Test fun `accepts a well formed granted message`() {
        assertIs<BridgeVerdict.Accepted>(gate().check(env(1), 1500))
    }

    @Test fun `denies order commands, authority claims, replays, reordering, expiry and ungranted capabilities`() {
        val g = gate()
        assertIs<BridgeVerdict.Rejected>(g.check(env(1, cap = "placeOrder"), 1500))
        assertIs<BridgeVerdict.Rejected>(g.check(env(2, effect = "TRADE"), 1500))
        assertIs<BridgeVerdict.Rejected>(g.check(env(3, cap = "chart.replay"), 1500))
        assertIs<BridgeVerdict.Accepted>(g.check(env(4), 1500))
        assertIs<BridgeVerdict.Rejected>(g.check(env(4, id = "other"), 1500))
        assertIs<BridgeVerdict.Rejected>(g.check(env(5, id = "m4"), 1500))
        assertIs<BridgeVerdict.Rejected>(g.check(env(6), 9000))
        assertIs<BridgeVerdict.Rejected>(g.check(env(7).copy(origin = "https://evil.example"), 1500))
    }
}

class SchedulerTest {
    @Test fun `never draws while hidden or without a surface, and coalesces bursts`() {
        val s = FrameScheduler(16)
        s.invalidate()
        assertTrue(!s.shouldDraw(0))
        s.onSurfaceAvailable(); assertTrue(!s.shouldDraw(0))
        s.onVisibility(true); assertTrue(s.shouldDraw(100)); s.frameDrawn(100)
        repeat(50) { s.invalidate() }
        assertTrue(!s.shouldDraw(105)); assertTrue(s.shouldDraw(117)); s.frameDrawn(117)
        assertTrue(!s.wantsFrames)
        s.invalidate(); s.onVisibility(false); assertTrue(!s.shouldDraw(500))
        s.onVisibility(true); s.onSurfaceLost(); assertTrue(!s.shouldDraw(600))
        s.onSurfaceAvailable(); assertTrue(s.shouldDraw(700))
        assertEquals(2, s.framesDrawn)
    }
}

class BudgetTest {
    @Test fun `frame size stays bounded by screen width however much history is loaded`() {
        val big = ChartEngine(series(100_000), LAYOUT)
        big.apply(ChartCommand.Zoom(0.0001f, 500f)) // fully zoomed out
        big.apply(ChartCommand.Pan(-1e9f))
        val t0 = System.nanoTime()
        val f = big.frame()
        val ms = (System.nanoTime() - t0) / 1e6
        val candles = f.list.ofRole(StyleRole.CANDLE_UP).size + f.list.ofRole(StyleRole.CANDLE_DOWN).size
        // At most one merged candle per 2 px of plot width (Lod.minPxPerGroup).
        assertTrue(candles <= (f.mainPlot.width / 2f).toInt() + 2, "drew $candles candles for ${f.mainPlot.width}px")
        println("BUDGET 100k bars: ${f.list.size} commands, $candles candles, ${"%.1f".format(ms)} ms on the JVM")
    }
}
