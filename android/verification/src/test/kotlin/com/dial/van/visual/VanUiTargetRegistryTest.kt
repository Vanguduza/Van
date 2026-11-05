package com.dial.van.visual

import kotlin.math.hypot
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class VanUiTargetRegistryTest {
    private val viewport = VanOwnedRect(0f, 0f, 1_000f, 1_000f)
    private val avatar = VanOwnedLayout("owner-window", VanOwnedRect(100f, 100f, 300f, 300f), viewport, true)
    private fun target(box: VanOwnedRect = VanOwnedRect(500f, 100f, 650f, 150f)) = VanOwnedLayout("owner-window", box, viewport, true)
    private fun prepared(): VanUiTargetRegistry = VanUiTargetRegistry().apply {
        observeAvatar(1, avatar, 1_000)
        observeTarget("result", 2, target(), 1_000)
    }

    @Test fun currentVisibleTargetResolvesToAUnitArmDirection() {
        val actual = assertNotNull(prepared().resolve("result", 1_000))
        assertEquals(1f, hypot(actual.directionX, actual.directionY), 0.00001f)
        assertTrue(actual.directionX > 0f && actual.directionY < 0f)
        assertNotNull(actual.cueTarget.normalizedCenter())
    }
    @Test fun noAvatarOrNoTargetCannotInventGeometry() {
        assertNull(VanUiTargetRegistry().resolve("result", 1_000))
        val registry = prepared(); registry.removeAvatar(1)
        assertNull(registry.resolve("result", 1_000))
        assertNull(prepared().resolve("missing", 1_000))
    }
    @Test fun unrelatedWindowNeverBecomesGuidanceTarget() {
        val r = prepared(); r.observeTarget("result", 2, target().copy(windowId = "other-app"), 1_001)
        assertNull(r.resolve("result", 1_001))
    }
    @Test fun hiddenOrNotLoadedAvatarRefusesPointing() {
        val r = prepared(); r.observeAvatar(1, avatar.copy(visible = false), 1_001)
        assertNull(r.resolve("result", 1_001))
    }
    @Test fun hiddenTargetRefusesPointing() {
        val r = prepared(); r.observeTarget("result", 2, target().copy(visible = false), 1_001)
        assertNull(r.resolve("result", 1_001))
    }
    @Test fun sourceAndAvatarSnapshotsMustBothBeFresh() {
        assertNull(prepared().resolve("result", 2_501))
        val r = prepared(); r.observeTarget("result", 2, target(), 2_501)
        assertNull(r.resolve("result", 2_501))
        r.observeAvatar(1, avatar, 2_501)
        assertNotNull(r.resolve("result", 2_501))
    }
    @Test fun futureOrRewoundTimeDoesNotAdmitPointing() {
        assertNull(prepared().resolve("result", 999))
    }
    @Test fun scrollUpdatesDirectionWithoutReusingOldRectangle() {
        val r = prepared(); val initial = assertNotNull(r.resolve("result", 1_000))
        r.observeTarget("result", 2, target(VanOwnedRect(500f, 700f, 650f, 750f)), 1_100)
        val next = assertNotNull(r.resolve("result", 1_100))
        assertTrue(next.directionY > 0 && initial.directionY < 0)
        assertTrue(next.revision > initial.revision)
    }
    @Test fun avatarMovementRecomputesTheRayFromItsNewShoulder() {
        val r = prepared(); val before = assertNotNull(r.resolve("result", 1_000))
        r.observeAvatar(1, avatar.copy(bounds = VanOwnedRect(700f, 100f, 900f, 300f)), 1_001)
        val after = assertNotNull(r.resolve("result", 1_001))
        assertTrue(before.directionX > 0 && after.directionX < 0)
        assertTrue(after.revision > before.revision)
    }
    @Test fun unchangedMeasurementRefreshesAgeWithoutGeneratingAnotherRevision() {
        val r = prepared(); val a = assertNotNull(r.resolve("result", 1_000))
        r.observeTarget("result", 2, target(), 2_000); r.observeAvatar(1, avatar, 2_000)
        assertEquals(a.revision, assertNotNull(r.resolve("result", 2_000)).revision)
    }
    @Test fun staleDisposalCannotDeleteARecomposedTarget() {
        val r = prepared(); r.observeTarget("result", 3, target(), 1_001); r.removeTarget("result", 2)
        assertEquals(3L, assertNotNull(r.resolve("result", 1_001)).lease)
    }
    @Test fun oldLeaseCannotOverwriteNewerViewInstance() {
        val r = prepared(); r.observeTarget("result", 3, target(), 1_001)
        r.observeTarget("result", 2, target().copy(visible = false), 1_002)
        assertNotNull(r.resolve("result", 1_002))
    }
    @Test fun disposedTargetAndAvatarAreUnavailableImmediately() {
        val r = prepared(); r.removeTarget("result", 2)
        assertNull(r.resolve("result", 1_001))
    }
    @Test fun fullyScrolledAwayTargetIsNotPointedAt() {
        val r = prepared(); r.observeTarget("result", 2, target(VanOwnedRect(500f, 1_010f, 650f, 1_080f)), 1_001)
        assertNull(r.resolve("result", 1_001))
    }
    @Test fun mostlyClippedTargetIsRefusedButVisibleHalfUsesClippedBounds() {
        val r = prepared(); r.observeTarget("result", 2, target(VanOwnedRect(900f, 100f, 1_200f, 200f)), 1_001)
        assertNull(r.resolve("result", 1_001))
        r.observeTarget("result", 2, target(VanOwnedRect(900f, 100f, 1_050f, 200f)), 1_002)
        assertEquals(1_000f, assertNotNull(r.resolve("result", 1_002)).cueTarget.rightPx)
    }
    @Test fun corruptAndEmptyRectanglesCannotReachRive() {
        for (box in listOf(VanOwnedRect(Float.NaN, 10f, 20f, 30f), VanOwnedRect(10f, 10f, 10f, 20f), VanOwnedRect(30f, 10f, 20f, 30f))) {
            val r = prepared(); r.observeTarget("result", 2, target(box), 1_001); assertNull(r.resolve("result", 1_001))
        }
    }
    @Test fun viewportChangesRequireMatchingAvatarAndTargetSnapshots() {
        val r = prepared(); r.observeAvatar(1, avatar.copy(viewport = VanOwnedRect(0f, 0f, 900f, 900f)), 1_001)
        assertNull(r.resolve("result", 1_001))
    }
    @Test fun containFitHandlesNonSquareAvatarWithoutStretchingCoordinates() {
        val r = prepared(); r.observeAvatar(1, avatar.copy(bounds = VanOwnedRect(100f, 0f, 300f, 400f)), 1_001)
        val a = assertNotNull(r.resolve("result", 1_001))
        val original = assertNotNull(prepared().resolve("result", 1_000))
        assertEquals(original.directionX, a.directionX, 0.00001f)
        assertEquals(original.directionY, a.directionY, 0.00001f)
    }
    @Test fun boundedRegistryDoesNotRetainAnUnlimitedHistoryOfUiNodes() {
        val r = VanUiTargetRegistry(capacity = 3); r.observeAvatar(1, avatar, 1_000)
        repeat(20) { r.observeTarget("item-$it", it + 2L, target(), 1_000) }
        assertEquals(3, r.count()); assertNull(r.resolve("item-0", 1_000)); assertNotNull(r.resolve("item-19", 1_000))
    }
    @Test fun clearRemovesAllOwnedGeometry() {
        val r = prepared(); r.clear(); assertEquals(0, r.count()); assertNull(r.resolve("result", 1_000))
    }
}
