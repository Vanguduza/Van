package com.dial.van.visual

import com.dial.van.overlay.OverlayTheme
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * P2-AURA-001 and P2-PERF-001 — the air gap is a dp contract, and the silhouette is not
 * rebuilt sixty times a second for a value that never changes.
 */
class VanAuraGeometryTest {

    @BeforeTest
    fun reset() = VanBodyExclusionProfile.resetCache()

    @AfterTest
    fun clear() = VanBodyExclusionProfile.resetCache()

    @Test
    fun `at the shipping avatar size the gap is inside the 10 to 14 dp band`() {
        val avatarDp = OverlayTheme.RESTING_AVATAR_DP.toFloat()
        val gap = VanBodyExclusionProfile.gapDp(avatarDp)
        assertNotNull(gap)
        assertTrue(
            gap >= VanBodyExclusionProfile.MIN_BODY_GAP_DP &&
                gap <= VanBodyExclusionProfile.MAX_BODY_GAP_DP,
            "the gap at ${avatarDp}dp is ${gap}dp, outside the 10-14 dp requirement",
        )
    }

    @Test
    fun `the old proportional gap is the 5 point 3 dp the audit measured`() {
        // Stated rather than assumed: the fraction that shipped, at the size that shipped
        // then (96 dp, before floating VAN became full body at the owner's direction).
        val avatarDp = 96f
        val legacy = avatarDp * VanBodyExclusionProfile.LEGACY_GAP_FRACTION
        assertEquals(5.28f, legacy, 0.01f)
        assertTrue(legacy < VanBodyExclusionProfile.MIN_BODY_GAP_DP)
    }

    @Test
    fun `the gap stays in band at every size VAN is drawn at`() {
        // The reason a proportion cannot be right: the same fraction is too tight on the
        // 96 dp avatar and too loose on a 400 dp evidence board.
        for (dp in listOf(64f, 96f, 120f, 184f, 300f, 400f)) {
            val gap = VanBodyExclusionProfile.gapDp(dp)
            assertNotNull(gap, "no gap for ${dp}dp")
            assertTrue(
                gap in VanBodyExclusionProfile.MIN_BODY_GAP_DP..VanBodyExclusionProfile.MAX_BODY_GAP_DP,
                "at ${dp}dp the gap is ${gap}dp",
            )
        }
    }

    @Test
    fun `a caller that cannot say what a dp is gets no dp claim`() {
        // The JVM evidence renderer works in raw pixels with no density. "Out of band" and
        // "nobody said what a dp is here" are different facts.
        assertNull(VanBodyExclusionProfile.gapDp(null))
        assertNull(VanBodyExclusionProfile.gapDp(0f))
    }

    @Test
    fun `the dp gap actually reaches the geometry`() {
        val bodyEdge = 480f
        val withDp = VanBodyExclusionProfile.compact(
            bodyEdge = bodyEdge, centerX = 240f, centerY = 240f, bodyEdgeDp = 96f,
        )
        val legacy = VanBodyExclusionProfile.compact(
            bodyEdge = bodyEdge, centerX = 240f, centerY = 240f,
        )
        // 12/96 = 0.125 against the legacy 0.055: the silhouette is materially wider.
        val dpHead = withDp.primitives.first() as VanExclusionPrimitive.Ellipse
        val legacyHead = legacy.primitives.first() as VanExclusionPrimitive.Ellipse
        assertTrue(
            dpHead.rx > legacyHead.rx,
            "the dp gap did not widen the exclusion: ${dpHead.rx} vs ${legacyHead.rx}",
        )
    }

    // ------------------------------------------------------------- P2-PERF-001

    @Test
    fun `the silhouette is built once and reused across frames`() {
        repeat(120) { index ->
            VanFieldGeometryEngine.build(
                spec = VanAuraSpecs.forState(VanDurableState.LISTENING),
                phase = index / 120f,
                budget = VanEffectBudget.FULL,
                bodyEdge = 480f, centerX = 240f, centerY = 240f, bodyEdgeDp = 96f,
            )
        }
        assertEquals(
            1L, VanBodyExclusionProfile.rebuilds,
            "the silhouette was rebuilt ${VanBodyExclusionProfile.rebuilds} times over 120 frames",
        )
    }

    @Test
    fun `resizing the body does rebuild it`() {
        VanBodyExclusionProfile.compactCached(480f, 240f, 240f, bodyEdgeDp = 96f)
        VanBodyExclusionProfile.compactCached(480f, 240f, 240f, bodyEdgeDp = 96f)
        assertEquals(1L, VanBodyExclusionProfile.rebuilds)
        VanBodyExclusionProfile.compactCached(720f, 360f, 360f, bodyEdgeDp = 144f)
        assertEquals(2L, VanBodyExclusionProfile.rebuilds)
    }

    @Test
    fun `sub-pixel float wobble does not defeat the cache`() {
        // Layout floats move in the last bits between frames; an exact-equality key would
        // miss on a body that has not moved, which is a cache that never hits.
        VanBodyExclusionProfile.compactCached(480.0f, 240.0f, 240.0f, bodyEdgeDp = 96f)
        VanBodyExclusionProfile.compactCached(480.0001f, 240.00002f, 240.0f, bodyEdgeDp = 96f)
        assertEquals(1L, VanBodyExclusionProfile.rebuilds)
    }

    @Test
    fun `the field still animates while the silhouette is cached`() {
        // Caching the wrong thing would freeze the aura. The strands must still move.
        val spec = VanAuraSpecs.forState(VanDurableState.LISTENING)
        fun frame(phase: Float) = VanFieldGeometryEngine.build(
            spec = spec, phase = phase, budget = VanEffectBudget.FULL,
            bodyEdge = 480f, centerX = 240f, centerY = 240f, bodyEdgeDp = 96f,
        )
        val first = frame(0.10f)
        val second = frame(0.35f)
        assertTrue(first.strokes.isNotEmpty(), "no strokes at all")
        assertTrue(
            first.strokes.first().points != second.strokes.first().points,
            "the field stopped moving when the silhouette was cached",
        )
    }
}
