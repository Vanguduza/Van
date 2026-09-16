package com.dial.van.visual

import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.hypot

class VanFieldRev3Test {
    @Test
    fun workingFieldChangesAcrossMotionPhases() {
        val spec = VanAuraSpecs.forState(VanDurableState.WORKING)
        val a = VanFieldGeometryEngine.build(spec, 0.08f, VanEffectBudget.FULL, 200f, 160f, 160f)
        val b = VanFieldGeometryEngine.build(spec, 0.43f, VanEffectBudget.FULL, 200f, 160f, 160f)

        val signatureA = a.strokes.flatMap { it.points }.take(24).joinToString { "${it.x.toInt()}:${it.y.toInt()}" }
        val signatureB = b.strokes.flatMap { it.points }.take(24).joinToString { "${it.x.toInt()}:${it.y.toInt()}" }
        assertNotEquals(signatureA, signatureB)
    }

    @Test
    fun fieldAndElectricalBranchesRespectInflatedBodySilhouette() {
        val spec = VanAuraSpecs.forState(VanDurableState.WORKING)
        val centerX = 160f
        val centerY = 160f
        val body = 200f
        val profile = VanBodyExclusionProfile.compact(body, centerX, centerY)

        val geometries = listOf(0.08f, 0.26f, 0.51f, 0.78f).map { phase ->
            VanFieldGeometryEngine.build(spec, phase, VanEffectBudget.FULL, body, centerX, centerY)
        }

        geometries.forEach { geometry ->
            geometry.strokes.flatMap { it.points }.forEach { point ->
                assertTrue("main field entered inflated VAN silhouette: $point", !profile.contains(point))
            }
            geometry.electricalBranches.forEach { branch ->
                (branch.trunk + branch.children.flatten()).forEach { point ->
                    assertTrue("electrical branch entered inflated VAN silhouette: $point", !profile.contains(point))
                }
            }
        }
    }

    @Test
    fun workingFieldProducesFiniteElectricalLifeAcrossCycle() {
        val spec = VanAuraSpecs.forState(VanDurableState.WORKING)
        val samples = listOf(0.05f, 0.18f, 0.33f, 0.48f, 0.66f, 0.82f).map { phase ->
            VanFieldGeometryEngine.build(spec, phase, VanEffectBudget.FULL, 200f, 160f, 160f)
        }
        assertTrue("working field never produced an electrical event", samples.any { it.electricalBranches.isNotEmpty() })
        assertTrue(
            "electrical life never changed across phase",
            samples.map { it.electricalBranches.size to it.electricalBranches.sumOf { b -> b.trunk.size } }.toSet().size > 1,
        )
    }

    @Test
    fun frozenFrameDoesNotCollapseToCommonRadiusHalo() {
        val spec = VanAuraSpecs.forState(VanDurableState.WORKING)
        val geometry = VanFieldGeometryEngine.build(spec, 0.31f, VanEffectBudget.FULL, 200f, 160f, 160f)
        val radii = geometry.strokes.flatMap { it.points }.map { point ->
            hypot((point.x - 160f).toDouble(), (point.y - 160f).toDouble())
        }
        val mean = radii.average()
        val variance = radii.sumOf { value ->
            val d = value - mean
            d * d
        } / radii.size.coerceAtLeast(1)
        val coefficient = kotlin.math.sqrt(variance) / mean.coerceAtLeast(1.0)
        assertTrue("field still reads like a common-radius halo: cv=$coefficient", coefficient > 0.16)
    }
}
