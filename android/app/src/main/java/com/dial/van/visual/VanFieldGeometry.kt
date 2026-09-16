package com.dial.van.visual

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.sin

/** Renderer-neutral output consumed by Compose and JVM evidence rendering. */
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

/** Short-lived electrical event travelling on the windy field. */
data class VanElectricalBranch(
    val trunk: List<VanFieldPoint>,
    val children: List<List<VanFieldPoint>>,
    val ink: VanFieldInk,
    val alpha: Float,
    val width: Float,
    val glowWidth: Float,
    val life: Float,
)

data class VanFieldGeometry(
    val strokes: List<VanFieldStroke>,
    val dots: List<VanFieldDot>,
    val electricalBranches: List<VanElectricalBranch> = emptyList(),
)

/**
 * Canonical Rev 3 field geometry.
 *
 * Zone B follows local activity, Zone C follows semantic truth. Both are clipped against an
 * inflated approximation of VAN's actual head/shoulder/torso silhouette rather than a tiny center
 * ellipse. Filaments are long advecting S-curves with state-dependent local wind; electrical
 * branches are finite events and can never become a persistent body outline.
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
        semanticSpec: VanAuraSpec = spec,
    ): VanFieldGeometry {
        if (bodyEdge <= 1f || (spec.intensity <= 0.01f && semanticSpec.intensity <= 0.01f)) {
            return VanFieldGeometry(emptyList(), emptyList())
        }

        val activityMotion = VanWindFieldMotion.sample(spec, phase, budget)
        val semanticMotion = VanWindFieldMotion.sample(semanticSpec, phase, budget)
        val profile = VanBodyExclusionProfile.compact(bodyEdge, centerX, centerY)
        val midRadius = bodyEdge * 0.60f * VanAuraSpec.MID_RADIUS_SCALE * activityMotion.fieldScale
        val strokes = mutableListOf<VanFieldStroke>()
        val dots = mutableListOf<VanFieldDot>()
        val electrical = mutableListOf<VanElectricalBranch>()

        val baseWind = direction(activityMotion.windAngleRad)
        val baseNormal = VanFieldPoint(-baseWind.y, baseWind.x)

        if (spec.filamentCount > 0 && spec.arcActivity > 0.01f) {
            repeat(spec.filamentCount.coerceIn(1, 5)) { index ->
                val seed = seed01(index, spec.intensity + spec.deformation)
                val side = if (index % 2 == 0) -1f else 1f
                val tier = 0.40f + (index / 2) * 0.24f
                val lateral = side * midRadius * tier
                val longitudinal = (seed - 0.5f) * midRadius * 0.45f
                val length = midRadius * (1.80f + 0.56f * activityMotion.windStrength + seed * 0.24f)
                val amplitude = midRadius * (0.16f + 0.24f * activityMotion.waveAmplitude) *
                    (0.80f + seed * 0.34f)
                val alpha = (0.30f + spec.arcActivity * 0.40f).coerceIn(0.28f, 0.74f)
                ribbonSegments(
                    centerX = centerX,
                    centerY = centerY,
                    wind = baseWind,
                    normal = baseNormal,
                    length = length,
                    lateral = lateral,
                    longitudinal = longitudinal,
                    amplitude = amplitude,
                    phase = activityMotion.phase,
                    seed = seed,
                    turbulence = activityMotion.turbulence,
                    profile = profile,
                    allowMotion = budget.allowMotion,
                ).forEach { points ->
                    strokes += VanFieldStroke(
                        points = points,
                        ink = VanFieldInk.IDENTITY,
                        alpha = alpha,
                        width = (bodyEdge * 0.011f).coerceAtLeast(1.15f),
                        glowWidth = (bodyEdge * 0.040f).coerceAtLeast(2.8f),
                    )
                }
            }
        }

        addAdvectedParticles(
            spec = spec,
            motion = activityMotion,
            budget = budget,
            profile = profile,
            centerX = centerX,
            centerY = centerY,
            radius = midRadius,
            wind = baseWind,
            normal = baseNormal,
            bodyEdge = bodyEdge,
            out = dots,
        )

        val segments = semanticSpec.segmentsForBudget(budget)
        if (segments.isNotEmpty()) {
            val semanticMidRadius = bodyEdge * 0.60f * VanAuraSpec.MID_RADIUS_SCALE * semanticMotion.fieldScale
            val outerRadius = semanticMidRadius * semanticSpec.envelopeRadiusScale.coerceIn(
                VanAuraSpec.MIN_ENVELOPE_SCALE,
                VanAuraSpec.MAX_ENVELOPE_SCALE,
            )
            val baseAlpha = semanticSpec.envelopeAlpha.coerceIn(0.06f, 0.24f)
            val semanticBoost = if (semanticSpec.semanticColor != null) 1f else 0.72f

            segments.forEachIndexed { index, segment ->
                val absolute = Math.toRadians(segment.startDeg.toDouble()).toFloat()
                val topologyTurn = wrapPi(absolute) * 0.48f
                val localWind = direction(semanticMotion.windAngleRad + topologyTurn)
                val localNormal = VanFieldPoint(-localWind.y, localWind.x)
                val seed = seed01(
                    index + 11,
                    segment.startDeg * 0.017f + segment.sweepDeg * 0.011f + semanticSpec.deformation,
                )
                val side = if (sin(absolute) >= 0f) 1f else -1f
                val lateral = side * outerRadius * (0.52f + 0.20f * abs(sin(absolute)))
                val longitudinal = cos(absolute) * outerRadius * 0.34f
                val sweepFactor = segment.sweepDeg.coerceIn(20f, 110f) / 110f
                val length = outerRadius * (0.92f + 0.64f * sweepFactor)
                val amplitude = outerRadius *
                    (0.09f + 0.16f * semanticMotion.waveAmplitude + 0.03f * sweepFactor)

                ribbonSegments(
                    centerX,
                    centerY,
                    localWind,
                    localNormal,
                    length,
                    lateral,
                    longitudinal,
                    amplitude,
                    semanticMotion.phase,
                    seed,
                    semanticMotion.turbulence * 0.88f,
                    profile,
                    budget.allowMotion,
                ).forEach { points ->
                    strokes += VanFieldStroke(
                        points = points,
                        ink = VanFieldInk.SEMANTIC,
                        alpha = baseAlpha * semanticBoost,
                        width = (bodyEdge * 0.0085f).coerceAtLeast(1f),
                        glowWidth = (bodyEdge * 0.030f).coerceAtLeast(2.2f),
                    )
                }

                if (segment.node || segments.size == 1) {
                    val nodeProgress = (
                        0.18f + seed * 0.64f +
                            (if (budget.allowMotion) semanticMotion.particleAdvection else 0.37f) * 0.18f
                        ) % 1f
                    val node = flowPoint(
                        centerX,
                        centerY,
                        localWind,
                        localNormal,
                        length,
                        lateral,
                        longitudinal,
                        amplitude,
                        nodeProgress,
                        semanticMotion.phase,
                        seed,
                        semanticMotion.turbulence,
                        budget.allowMotion,
                    )
                    if (!profile.contains(node)) {
                        dots += VanFieldDot(
                            point = node,
                            ink = VanFieldInk.SEMANTIC,
                            alpha = (baseAlpha + 0.14f).coerceAtMost(0.38f),
                            radius = (bodyEdge * (0.011f + 0.006f * semanticMotion.electricPulse))
                                .coerceAtLeast(1.2f),
                        )
                    }
                }
            }
        }

        // Electrical life is activity-driven in cyan. Critical semantic states receive sparse
        // semantic branches too, so error/approval topology changes rather than only recolouring.
        val activityElectrical = (spec.sparkRate * 0.65f + spec.arcActivity * 0.35f).coerceIn(0f, 1f)
        if (activityElectrical > 0.08f && budget.filamentScale > 0f) {
            electrical += electricalBranches(
                centerX = centerX,
                centerY = centerY,
                radius = midRadius,
                wind = baseWind,
                normal = baseNormal,
                profile = profile,
                motion = activityMotion,
                energy = activityElectrical,
                bodyEdge = bodyEdge,
                ink = VanFieldInk.IDENTITY,
                budget = budget,
                salt = spec.intensity + spec.sparkRate,
            )
        }

        val semanticElectrical = if (semanticSpec.semanticColor != null) {
            (semanticSpec.sparkRate * 0.55f + semanticSpec.arcActivity * 0.35f + semanticSpec.envelopeAlpha * 0.45f)
                .coerceIn(0f, 1f)
        } else {
            0f
        }
        if (semanticElectrical > 0.10f && budget.filamentScale > 0f) {
            electrical += electricalBranches(
                centerX = centerX,
                centerY = centerY,
                radius = midRadius * semanticSpec.envelopeRadiusScale.coerceIn(1.25f, 1.75f),
                wind = direction(semanticMotion.windAngleRad + 0.72f),
                normal = direction(semanticMotion.windAngleRad + 0.72f + PI.toFloat() / 2f),
                profile = profile,
                motion = semanticMotion,
                energy = semanticElectrical,
                bodyEdge = bodyEdge,
                ink = VanFieldInk.SEMANTIC,
                budget = budget,
                salt = semanticSpec.envelopeAlpha + semanticSpec.deformation + 2.1f,
            )
        }

        return VanFieldGeometry(
            strokes = strokes,
            dots = dots,
            electricalBranches = electrical,
        )
    }

    private fun addAdvectedParticles(
        spec: VanAuraSpec,
        motion: VanWindFieldFrame,
        budget: VanEffectBudget,
        profile: VanBodyExclusionProfile,
        centerX: Float,
        centerY: Float,
        radius: Float,
        wind: VanFieldPoint,
        normal: VanFieldPoint,
        bodyEdge: Float,
        out: MutableList<VanFieldDot>,
    ) {
        if (spec.sparkRate <= 0.015f) return
        val count = (3 + spec.sparkRate * 12f * budget.filamentScale).toInt().coerceIn(3, 12)
        repeat(count) { index ->
            val seed = seed01(index + 31, spec.sparkRate + spec.intensity)
            val progress = if (budget.allowMotion) {
                (motion.particleAdvection * (0.70f + seed * 0.86f) + seed) % 1f
            } else {
                seed
            }
            val side = if (index % 2 == 0) -1f else 1f
            val lateral = side * radius * (0.36f + 0.62f * seed)
            val point = flowPoint(
                centerX,
                centerY,
                wind,
                normal,
                radius * (1.70f + motion.windStrength * 0.42f),
                lateral,
                0f,
                radius * (0.08f + motion.waveAmplitude * 0.12f),
                progress,
                motion.phase,
                seed,
                motion.turbulence,
                budget.allowMotion,
            )
            if (!profile.contains(point)) {
                // Lifetime envelope: each deterministic particle fades near the ends of its path.
                val life = sin(PI.toFloat() * progress).coerceAtLeast(0f)
                val alpha = ((0.20f + 0.58f * motion.electricPulse) *
                    (0.42f + 0.58f * spec.sparkRate) * life).coerceIn(0.06f, 0.82f)
                out += VanFieldDot(
                    point = point,
                    ink = VanFieldInk.IDENTITY,
                    alpha = alpha,
                    radius = (bodyEdge * (0.0055f + 0.003f * seed)).coerceAtLeast(0.8f),
                )
            }
        }
    }

    private fun electricalBranches(
        centerX: Float,
        centerY: Float,
        radius: Float,
        wind: VanFieldPoint,
        normal: VanFieldPoint,
        profile: VanBodyExclusionProfile,
        motion: VanWindFieldFrame,
        energy: Float,
        bodyEdge: Float,
        ink: VanFieldInk,
        budget: VanEffectBudget,
        salt: Float,
    ): List<VanElectricalBranch> {
        val count = (1 + energy * 3f * budget.filamentScale).toInt().coerceIn(1, 4)
        val result = mutableListOf<VanElectricalBranch>()
        val phase = if (budget.allowMotion) motion.phase else 0.37f

        repeat(count) { branchIndex ->
            val seed = seed01(branchIndex + 83, salt)
            // Branch lifecycle is sparse. Outside the active window no branch is emitted, which
            // avoids a permanently electrified outline and gives the field visible moments of rest.
            val cycle = (phase * (1.55f + seed * 0.75f) + seed) % 1f
            val activeWindow = 0.54f + energy * 0.22f
            if (cycle > activeWindow && budget.allowMotion) return@repeat
            val life = if (budget.allowMotion) {
                sin(PI.toFloat() * (cycle / activeWindow.coerceAtLeast(0.01f)).coerceIn(0f, 1f))
                    .coerceAtLeast(0f)
            } else {
                0.42f
            }

            val side = if (branchIndex % 2 == 0) -1f else 1f
            val lateral = side * radius * (0.66f + seed * 0.34f)
            val startAlong = radius * (-0.55f + seed * 0.40f)
            val trunk = mutableListOf<VanFieldPoint>()
            val steps = 8
            repeat(steps) { i ->
                val u = i / (steps - 1f)
                val jitter = sin(TAU * (u * 3.2f + seed * 1.7f + phase * 2.1f)) * radius * 0.045f
                val along = startAlong + u * radius * (0.58f + 0.28f * energy)
                val across = lateral + jitter
                val point = point(centerX, centerY, wind, normal, along, across)
                if (!profile.contains(point)) trunk += point
            }
            if (trunk.size < 4) return@repeat

            val children = mutableListOf<List<VanFieldPoint>>()
            if (energy > 0.24f) {
                val forkStart = trunk[(trunk.size * 2 / 3).coerceAtMost(trunk.lastIndex)]
                val forkDirection = direction(
                    motion.windAngleRad + (if (side > 0f) 0.78f else -0.84f) + seed * 0.28f,
                )
                val fork = mutableListOf<VanFieldPoint>()
                repeat(4) { i ->
                    val u = i / 3f
                    val candidate = VanFieldPoint(
                        x = forkStart.x + forkDirection.x * radius * 0.24f * u +
                            normal.x * sin((u + seed) * TAU) * radius * 0.025f,
                        y = forkStart.y + forkDirection.y * radius * 0.24f * u +
                            normal.y * sin((u + seed) * TAU) * radius * 0.025f,
                    )
                    if (!profile.contains(candidate)) fork += candidate
                }
                if (fork.size >= 2) children += fork
            }

            result += VanElectricalBranch(
                trunk = trunk,
                children = children,
                ink = ink,
                alpha = (0.34f + energy * 0.58f) * life.coerceAtLeast(0.22f),
                width = (bodyEdge * 0.0065f).coerceAtLeast(0.9f),
                glowWidth = (bodyEdge * 0.030f).coerceAtLeast(2.4f),
                life = life,
            )
        }
        return result
    }

    private fun ribbonSegments(
        centerX: Float,
        centerY: Float,
        wind: VanFieldPoint,
        normal: VanFieldPoint,
        length: Float,
        lateral: Float,
        longitudinal: Float,
        amplitude: Float,
        phase: Float,
        seed: Float,
        turbulence: Float,
        profile: VanBodyExclusionProfile,
        allowMotion: Boolean,
    ): List<List<VanFieldPoint>> {
        val segments = mutableListOf<MutableList<VanFieldPoint>>()
        var current: MutableList<VanFieldPoint>? = null
        val steps = 34
        repeat(steps + 1) { index ->
            val point = flowPoint(
                centerX,
                centerY,
                wind,
                normal,
                length,
                lateral,
                longitudinal,
                amplitude,
                index / steps.toFloat(),
                phase,
                seed,
                turbulence,
                allowMotion,
            )
            if (profile.contains(point)) {
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
        val advectedPhase = phase * moving
        val envelope = sin(PI.toFloat() * u).coerceAtLeast(0f)
        // Low-frequency S curve carries the visual read; higher harmonics create windy detail.
        val wave1 = sin(TAU * (1.35f * u - 1.35f * advectedPhase + seed))
        val wave2 = sin(TAU * (2.80f * u + 2.10f * advectedPhase + seed * 1.71f))
        val wave3 = sin(TAU * (5.20f * u - 0.75f * advectedPhase + seed * 0.47f))
        val wave = (wave1 + wave2 * 0.30f + wave3 * 0.10f) * amplitude *
            (0.62f + 0.38f * envelope)
        val curl = sin(TAU * (u * 1.12f + advectedPhase * 0.72f + seed * 0.31f)) *
            amplitude * turbulence * 0.42f
        // A small longitudinal phase term makes the stream visibly advect instead of only wobble.
        val advection = if (allowMotion) {
            sin(TAU * (advectedPhase + seed)) * length * 0.055f
        } else {
            0f
        }
        return point(
            cx,
            cy,
            wind,
            normal,
            (u - 0.5f) * length + longitudinal + curl + advection,
            lateral + wave,
        )
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
