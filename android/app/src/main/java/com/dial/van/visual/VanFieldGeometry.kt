package com.dial.van.visual

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.sin

/** Renderer-neutral output consumed by Compose and Java2D evidence rendering. */
data class VanFieldPoint(val x: Float, val y: Float)

enum class VanFieldInk { IDENTITY, SEMANTIC }

data class VanFieldStroke(
    val points: List<VanFieldPoint>,
    val ink: VanFieldInk,
    val alpha: Float,
    val width: Float,
    val glowWidth: Float,
)

data class VanFieldDot(
    val point: VanFieldPoint,
    val ink: VanFieldInk,
    val alpha: Float,
    val radius: Float,
)

data class VanFieldGeometry(
    val strokes: List<VanFieldStroke>,
    val dots: List<VanFieldDot>,
)

/**
 * Canonical Zone B/C geometry. No Android, Compose or AWT types are used here, so preview boards
 * and the shipping overlay cannot silently evolve different aura topologies.
 */
object VanFieldGeometryEngine {
    private const val TAU = (2.0 * PI).toFloat()

    fun build(
        spec: VanAuraSpec,
        phase: Float,
        budget: VanEffectBudget,
        bodyEdge: Float,
        centerX: Float,
        centerY: Float,
    ): VanFieldGeometry {
        if (bodyEdge <= 1f || spec.intensity <= 0.01f) return VanFieldGeometry(emptyList(), emptyList())
        val motion = VanWindFieldMotion.sample(spec, phase, budget)
        val midRadius = bodyEdge * 0.42f * VanAuraSpec.MID_RADIUS_SCALE * motion.fieldScale
        val strokes = mutableListOf<VanFieldStroke>()
        val dots = mutableListOf<VanFieldDot>()

        val baseWind = direction(motion.windAngleRad)
        val baseNormal = VanFieldPoint(-baseWind.y, baseWind.x)
        val safeRxB = bodyEdge * 0.34f * 1.08f
        val safeRyB = bodyEdge * 0.43f

        if (spec.filamentCount > 0 && spec.arcActivity > 0.01f) {
            repeat(spec.filamentCount.coerceIn(1, 5)) { index ->
                val seed = seed01(index, spec.intensity + spec.deformation)
                val side = if (index % 2 == 0) -1f else 1f
                val tier = 0.34f + (index / 2) * 0.19f
                val lateral = side * midRadius * tier
                val longitudinal = (seed - 0.5f) * midRadius * 0.32f
                val length = midRadius * (1.75f + 0.48f * motion.windStrength + seed * 0.18f)
                val amplitude = midRadius * (0.10f + 0.17f * motion.waveAmplitude) * (0.82f + seed * 0.28f)
                val alpha = (0.25f + spec.arcActivity * 0.34f).coerceIn(0.24f, 0.66f)
                ribbonSegments(
                    centerX, centerY, baseWind, baseNormal, length, lateral, longitudinal,
                    amplitude, motion.phase, seed, motion.turbulence, safeRxB, safeRyB,
                    budget.allowMotion,
                ).forEach { points ->
                    strokes += VanFieldStroke(
                        points = points,
                        ink = VanFieldInk.IDENTITY,
                        alpha = alpha,
                        width = (bodyEdge * 0.0105f).coerceAtLeast(1.1f),
                        glowWidth = (bodyEdge * 0.032f).coerceAtLeast(2.4f),
                    )
                }
            }
        }

        if (spec.sparkRate > 0.015f) {
            val count = (2 + spec.sparkRate * 8f * budget.filamentScale).toInt().coerceIn(2, 8)
            repeat(count) { index ->
                val seed = seed01(index + 31, spec.sparkRate + spec.intensity)
                val progress = if (budget.allowMotion) {
                    (motion.particleAdvection * (0.65f + seed * 0.70f) + seed) % 1f
                } else seed
                val side = if (index % 2 == 0) -1f else 1f
                val lateral = side * midRadius * (0.30f + 0.46f * seed)
                val point = flowPoint(
                    centerX, centerY, baseWind, baseNormal,
                    midRadius * (1.55f + motion.windStrength * 0.35f), lateral, 0f,
                    midRadius * (0.06f + motion.waveAmplitude * 0.08f), progress,
                    motion.phase, seed, motion.turbulence, budget.allowMotion,
                )
                if (!insideEllipse(point, centerX, centerY, safeRxB, safeRyB)) {
                    val alpha = ((0.28f + 0.52f * motion.electricPulse) *
                        (0.45f + 0.55f * spec.sparkRate)).coerceIn(0.12f, 0.78f)
                    dots += VanFieldDot(
                        point = point,
                        ink = VanFieldInk.IDENTITY,
                        alpha = alpha,
                        radius = (bodyEdge * 0.006f).coerceAtLeast(0.8f),
                    )
                }
            }
        }

        val segments = spec.segmentsForBudget(budget)
        if (segments.isNotEmpty()) {
            val outerRadius = midRadius * spec.envelopeRadiusScale.coerceIn(
                VanAuraSpec.MIN_ENVELOPE_SCALE,
                VanAuraSpec.MAX_ENVELOPE_SCALE,
            )
            val safeRxC = bodyEdge * 0.52f
            val safeRyC = bodyEdge * 0.56f
            val baseAlpha = spec.envelopeAlpha.coerceIn(0.05f, 0.22f)
            val semanticBoost = if (spec.semanticColor != null) 1f else 0.68f

            segments.forEachIndexed { index, segment ->
                val absolute = Math.toRadians(segment.startDeg.toDouble()).toFloat()
                // Preserve state topology: each authored segment bends the prevailing wind into a
                // distinct local direction instead of collapsing every semantic state to one axis.
                val topologyTurn = wrapPi(absolute) * 0.44f
                val localWind = direction(motion.windAngleRad + topologyTurn)
                val localNormal = VanFieldPoint(-localWind.y, localWind.x)
                val seed = seed01(index + 11, segment.startDeg * 0.017f + segment.sweepDeg * 0.011f)
                val side = if (sin(absolute) >= 0f) 1f else -1f
                val lateral = side * outerRadius * (0.50f + 0.18f * abs(sin(absolute)))
                val longitudinal = cos(absolute) * outerRadius * 0.30f
                val sweepFactor = segment.sweepDeg.coerceIn(20f, 110f) / 110f
                val length = outerRadius * (0.88f + 0.56f * sweepFactor)
                val amplitude = outerRadius * (0.065f + 0.13f * motion.waveAmplitude + 0.025f * sweepFactor)

                ribbonSegments(
                    centerX, centerY, localWind, localNormal, length, lateral, longitudinal,
                    amplitude, motion.phase, seed, motion.turbulence * 0.85f, safeRxC, safeRyC,
                    budget.allowMotion,
                ).forEach { points ->
                    strokes += VanFieldStroke(
                        points = points,
                        ink = VanFieldInk.SEMANTIC,
                        alpha = baseAlpha * semanticBoost,
                        width = (bodyEdge * 0.008f).coerceAtLeast(1f),
                        glowWidth = (bodyEdge * 0.026f).coerceAtLeast(2f),
                    )
                }

                if (segment.node || segments.size == 1) {
                    val nodeProgress = (0.20f + seed * 0.62f + motion.particleAdvection * 0.18f) % 1f
                    val node = flowPoint(
                        centerX, centerY, localWind, localNormal, length, lateral, longitudinal,
                        amplitude, nodeProgress, motion.phase, seed, motion.turbulence,
                        budget.allowMotion,
                    )
                    if (!insideEllipse(node, centerX, centerY, safeRxC, safeRyC)) {
                        dots += VanFieldDot(
                            point = node,
                            ink = VanFieldInk.SEMANTIC,
                            alpha = (baseAlpha + 0.12f).coerceAtMost(0.34f),
                            radius = (bodyEdge * (0.010f + 0.006f * motion.electricPulse)).coerceAtLeast(1.2f),
                        )
                    }
                }
            }
        }

        return VanFieldGeometry(strokes = strokes, dots = dots)
    }

    private fun ribbonSegments(
        cx: Float,
        cy: Float,
        wind: VanFieldPoint,
        normal: VanFieldPoint,
        length: Float,
        lateral: Float,
        longitudinal: Float,
        amplitude: Float,
        phase: Float,
        seed: Float,
        turbulence: Float,
        safeRx: Float,
        safeRy: Float,
        allowMotion: Boolean,
    ): List<List<VanFieldPoint>> {
        val segments = mutableListOf<MutableList<VanFieldPoint>>()
        var current: MutableList<VanFieldPoint>? = null
        val steps = 28
        repeat(steps + 1) { index ->
            val point = flowPoint(
                cx, cy, wind, normal, length, lateral, longitudinal, amplitude,
                index / steps.toFloat(), phase, seed, turbulence, allowMotion,
            )
            if (insideEllipse(point, cx, cy, safeRx, safeRy)) {
                current = null
            } else {
                if (current == null) {
                    current = mutableListOf()
                    segments += current!!
                }
                current!!.add(point)
            }
        }
        return segments.filter { it.size >= 2 }
    }

    private fun flowPoint(
        cx: Float,
        cy: Float,
        wind: VanFieldPoint,
        normal: VanFieldPoint,
        length: Float,
        lateral: Float,
        longitudinal: Float,
        amplitude: Float,
        progress: Float,
        phase: Float,
        seed: Float,
        turbulence: Float,
        allowMotion: Boolean,
    ): VanFieldPoint {
        val u = progress.coerceIn(0f, 1f)
        val moving = if (allowMotion) 1f else 0f
        val envelope = sin(PI.toFloat() * u).coerceAtLeast(0f)
        val wave1 = sin(TAU * (2f * u - 2f * phase * moving + seed))
        val wave2 = sin(TAU * (3f * u + 3f * phase * moving + seed * 1.71f))
        val wave3 = sin(TAU * (5f * u - phase * moving + seed * 0.47f))
        val wave = (wave1 + wave2 * 0.38f + wave3 * 0.14f) * amplitude * (0.58f + 0.42f * envelope)
        val curl = sin(TAU * (u + phase * moving + seed * 0.31f)) * amplitude * turbulence * 0.34f
        return point(cx, cy, wind, normal, (u - 0.5f) * length + longitudinal + curl, lateral + wave)
    }

    private fun point(
        cx: Float,
        cy: Float,
        wind: VanFieldPoint,
        normal: VanFieldPoint,
        along: Float,
        across: Float,
    ) = VanFieldPoint(
        x = cx + wind.x * along + normal.x * across,
        y = cy + wind.y * along + normal.y * across,
    )

    private fun direction(angle: Float) = VanFieldPoint(cos(angle), sin(angle))

    private fun insideEllipse(point: VanFieldPoint, cx: Float, cy: Float, rx: Float, ry: Float): Boolean {
        if (rx <= 0f || ry <= 0f) return false
        val nx = (point.x - cx) / rx
        val ny = (point.y - cy) / ry
        return nx * nx + ny * ny < 1f
    }

    private fun seed01(index: Int, salt: Float): Float {
        val x = sin(index * 12.9898f + salt * 78.233f) * 43758.5453f
        return abs(x - floor(x)).coerceIn(0f, 1f)
    }

    private fun wrapPi(value: Float): Float {
        var v = value
        while (v > PI) v -= TAU
        while (v < -PI) v += TAU
        return v
    }
}
